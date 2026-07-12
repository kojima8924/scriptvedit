# -*- coding: utf-8 -*-

import subprocess
import os
import re
import sys
import json
import hashlib
import math as _math
import warnings
import builtins as _builtins
import time as _time
import difflib as _difflib
import shutil as _shutil
import concurrent.futures as _futures
import inspect as _inspect


# --- オーディオ系ファクトリ ---

def duck_under(other, *, ratio=8, threshold=0.05, attack=20, release=250):
    """sidechaincompress で other（ナレーション等）再生中に自音量を下げるAudioEffect。
    other は同じProjectに存在する音声Objectを指定する。"""
    if not isinstance(other, Object):
        raise TypeError(f"duck_under: other は音声Objectを指定してください: {type(other)}")
    return AudioEffect("duck_under", other=other, ratio=ratio,
                       threshold=threshold, attack=attack, release=release)


def loop(until=None):
    """aloop で音声を until 時刻までループさせるAudioEffect。
    until 省略時は Project.duration までループする。"""
    return AudioEffect("loop", until=until)


def _probe_audio_length(path):
    """音声/動画の長さを取得（取得不能時はNone）"""
    proj = Project._current
    if proj is not None:
        info = proj._probe_media(path)
        if info and info.get("duration"):
            return info["duration"]
    return None


def _validate_audio_source(func, path):
    if not isinstance(path, str):
        raise TypeError(f"{func}: ソースはパス文字列で指定してください: {path!r}")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{func}: 音声ファイルが見つかりません: {path}")
    if _detect_media_type(path) not in ("audio", "video"):
        raise ValueError(f"{func}: 音声(または動画音声)のみ指定できます: {path}")


def audio_sequence(*objs, crossfade=1.0):
    """複数の音声を acrossfade で連結した1つの音声Objectを生成（キャッシュ生成物）。
    objs は音声Object または音声パス文字列（2つ以上）。"""
    if len(objs) < 2:
        raise ValueError("audio_sequence: 2つ以上の音声を指定してください")
    _require_number("audio_sequence", "crossfade", crossfade, 0.01, None)
    proj = Project._current
    sources = []
    for o in objs:
        if isinstance(o, Object):
            if o.media_type != "audio":
                raise ValueError(
                    f"audio_sequence: 音声Objectのみ連結できます: {o.source}")
            sources.append(o.source)
            if proj is not None and o in proj.objects:
                proj.objects.remove(o)  # 合成に消費（タイムラインから除外）
        elif isinstance(o, str):
            _validate_audio_source("audio_sequence", o)
            sources.append(o)
        else:
            raise TypeError(f"audio_sequence: 音声Objectかパス文字列のみ: {type(o)}")
    n = len(sources)
    lengths = [_probe_audio_length(s) or 5.0 for s in sources]
    # acrossfade は各入力が crossfade 以上の長さを要する。
    # 素材長 < crossfade だと total が 0/負値になり後続配置が破綻するため拒否。
    for s, ln in zip(sources, lengths):
        if ln < crossfade:
            raise ValueError(
                f"audio_sequence: 素材長({ln:.3f}s)が crossfade({crossfade}s)未満です: {s}\n"
                f"crossfade を短くするか、より長い素材を指定してください。")
    total = sum(lengths) - crossfade * (n - 1)

    sigs = ["audio_sequence"]
    sigs.extend(_source_signature(s) for s in sources)
    sigs.extend([f"cf={crossfade}", f"ev={_ENGINE_VER}"])
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    cache_path = os.path.join(_ARTIFACT_DIR, "aseq", f"{key}.m4a")

    cmd = ["ffmpeg", "-y"]
    for s in sources:
        cmd.extend(["-i", s])
    parts = []
    cur = "[0:a]"
    for i in range(1, n):
        out = f"[axf{i}]"
        parts.append(f"{cur}[{i}:a]acrossfade=d={crossfade}{out}")
        cur = out
    cmd.extend(["-filter_complex", ";".join(parts), "-map", cur,
                "-c:a", "aac", "-b:a", "192k", cache_path])
    return _finalize_generated_object(cache_path, cmd, list(sources), total)


def sfx(source, at, *, volume=1.0):
    """同一音源を複数時刻(at)に配置した1つの音声Objectを生成（adelay+amix合成）。
    at は秒のリスト。生成Objectは開始0でタイムラインに配置する想定。"""
    _validate_audio_source("sfx", source)
    if not isinstance(at, (list, tuple)) or len(at) == 0:
        raise ValueError("sfx: at には配置時刻(秒)のリストを指定してください")
    for t in at:
        _require_number("sfx", "at要素", t, 0, None)
    _require_number("sfx", "volume", volume, 0, None)
    srclen = _probe_audio_length(source) or 5.0
    times = list(at)
    n = len(times)
    total = _builtins.max(times) + srclen

    sigs = ["sfx", _source_signature(source),
            "at=" + ",".join(str(t) for t in times),
            f"vol={volume}", f"ev={_ENGINE_VER}"]
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    cache_path = os.path.join(_ARTIFACT_DIR, "sfx", f"{key}.m4a")

    parts = ["[0:a]asplit=" + str(n) + "".join(f"[s{i}]" for i in range(n))]
    delayed = []
    for i, t in enumerate(times):
        ms = int(t * 1000)
        if ms > 0:
            parts.append(f"[s{i}]adelay={ms}:all=1[d{i}]")
        else:
            parts.append(f"[s{i}]anull[d{i}]")
        delayed.append(f"[d{i}]")
    mix_in = "".join(delayed)
    tail = f",volume={volume}" if volume != 1.0 else ""
    if n == 1:
        parts.append(f"{mix_in}anull{tail}[a]")
    else:
        parts.append(f"{mix_in}amix=inputs={n}:normalize=0{tail}[a]")
    cmd = ["ffmpeg", "-y", "-i", source,
           "-filter_complex", ";".join(parts), "-map", "[a]",
           "-c:a", "aac", "-b:a", "192k", "-t", str(total), cache_path]
    return _finalize_generated_object(cache_path, cmd, [source], total)


def voice(text, *, speaker=1, speed=1.0, pitch=0.0, volume=1.0, **tts_kwargs):
    """svtts(VOICEVOX)で text を音声合成し、その wav を素材とする音声Objectを返す。

    duration は tts_duration による実長を自動設定するため、字幕・タイムラインと
    自然に同期する。svtts.py が無い/VOICEVOX 未起動なら親切なエラーを投げる。

    使用例:
        v = voice("こんにちは、世界", speaker=3)
        v.show(v.duration)
    """
    try:
        import svtts as _svtts
    except ImportError as e:
        raise ImportError(
            "voice() には svtts.py が必要です。"
            "scriptvedit.py と同じディレクトリに配置してください。") from e
    wav = _svtts.tts(text, speaker=speaker, speed=speed, pitch=pitch, **tts_kwargs)
    dur = _svtts.tts_duration(wav)
    obj = Object(wav)
    obj.duration = dur
    if volume != 1.0:
        _require_number("voice", "volume", volume, 0, None)
        obj.audio_effects.append(again(volume))
    return obj


class Narration:
    """narrate() の返値。(audio, subtitle) としてタプルアンパック可能な軽量ラッパー。

    audio:    音声Object（voice()相当。durationはTTS実長）
    subtitle: 字幕Object（subtitle=False指定時はNone）
    duration: 音声の実長（秒）のショートカットプロパティ
    """
    __slots__ = ("audio", "subtitle")

    def __init__(self, audio, subtitle):
        self.audio = audio
        self.subtitle = subtitle

    def __iter__(self):
        yield self.audio
        yield self.subtitle

    def __repr__(self):
        return f"Narration(audio={self.audio!r}, subtitle={self.subtitle!r})"

    @property
    def duration(self):
        return self.audio.duration


def narrate(text_content, *, speaker=1, speed=1.0, pitch=0.0, volume=1.0,
            subtitle=True, subtitle_style=None,
            x=0.5, y=0.9, size=36, color="white", font=None,
            box=True, box_color="black@0.6", box_border=10, alpha=1.0,
            anchor="center", **tts_kwargs):
    """TTSナレーション音声 + 同期字幕を1回の呼び出しで生成・配置する。

    voice()(svtts)でtext_contentを音声合成し、subtitle=Trueなら同じ内容の
    text()字幕Objectも生成する。字幕の表示窓は音声の実長(tts_duration)に
    一致させ、両者は同じ開始時刻からタイムラインに配置される。
    複数回呼べば、音声の実長ぶんタイムラインが進むため順次配置される
    （字幕は各回の音声窓にだけ表示される）。

    x/y/size/color/font/box/box_color/box_border/alpha/anchor は text() と同じ
    意味の字幕スタイル引数（既定はナレーション向けに下部中央+半透明ボックス）。
    subtitle_style を渡すと、これらの既定値を辞書キー（同名）で個別に上書きできる
    （例: subtitle_style={"size": 44, "y": 0.85}）。
    volume/pitch/**tts_kwargs は voice() と同じ意味で音声側にのみ作用する。

    戻り値: Narration(audio, subtitle) （タプルとして (a, t) = narrate(...) も可）。
    svtts.py が無い/VOICEVOX未起動時のエラーはvoice()同様に透過する。

    使用例:
        n = narrate("こんにちは、世界", speaker=3)
        # n.audio / n.subtitle、または audio, sub = narrate(...)
    """
    try:
        import svtts as _svtts
    except ImportError as e:
        raise ImportError(
            "narrate() には svtts.py が必要です。"
            "scriptvedit.py と同じディレクトリに配置してください。") from e
    wav = _svtts.tts(text_content, speaker=speaker, speed=speed, pitch=pitch,
                     **tts_kwargs)
    dur = _svtts.tts_duration(wav)
    # dur<=0（空テキスト等）だと show(0) で current_time が進まず
    # 連続 narrate が同じ開始点に重なるため明示エラーにする。
    if dur <= 0:
        raise ValueError(
            f"narrate: 合成音声の長さが0以下でした（dur={dur}）。"
            f"text_content が空でないか確認してください: {text_content!r}")

    text_obj = None
    if subtitle:
        st = dict(subtitle_style or {})
        text_obj = text(
            text_content,
            x=st.get("x", x), y=st.get("y", y), size=st.get("size", size),
            color=st.get("color", color), font=st.get("font", font),
            box=st.get("box", box), box_color=st.get("box_color", box_color),
            box_border=st.get("box_border", box_border),
            alpha=st.get("alpha", alpha), anchor=st.get("anchor", anchor))
        # current_timeを進めず音声と同じ開始点に配置（音声側で進行させる）
        text_obj.show(dur)

    # text_objより後にaudio_objをobjects列へ追加することで、
    # 「同じ開始時刻→音声側だけがタイムラインを進める」順序を保証する
    audio_obj = Object(wav)
    audio_obj.duration = dur
    if volume != 1.0:
        _require_number("narrate", "volume", volume, 0, None)
        audio_obj.audio_effects.append(again(volume))

    return Narration(audio_obj, text_obj)


def audio_viz(source, *, kind="waves", color="white", size=None, duration=None):
    """音声を showwaves/showspectrum/showcqt で可視化した映像Objectを生成（キャッシュ生成物）。
    kind: 'waves' | 'spectrum' | 'cqt'。"""
    _validate_audio_source("audio_viz", source)
    if kind not in ("waves", "spectrum", "cqt"):
        hint = _suggest_hint(str(kind), ("waves", "spectrum", "cqt"))
        raise ValueError(
            f"audio_viz: kind は 'waves'/'spectrum'/'cqt': {kind!r}{hint}")
    proj = Project._current
    fps = proj.fps if proj else 30
    dur = duration or _probe_audio_length(source) or 5.0
    if size is not None:
        if not isinstance(size, (tuple, list)) or len(size) != 2:
            raise ValueError(f"audio_viz: size は (w, h) タプル: {size!r}")
        w, h = int(size[0]), int(size[1])
    elif kind == "waves":
        w, h = (proj.width if proj else 1280), 240
    else:
        w, h = (proj.width if proj else 1280), (proj.height if proj else 720)

    if kind == "waves":
        viz = f"showwaves=s={w}x{h}:mode=cline:rate={fps}:colors={color}"
    elif kind == "spectrum":
        viz = f"showspectrum=s={w}x{h}:slide=scroll:fps={fps}"
    else:
        viz = f"showcqt=s={w}x{h}:fps={fps}"

    sigs = ["audio_viz", _source_signature(source),
            f"kind={kind}", f"color={color}", f"size={w}x{h}",
            f"fps={fps}", f"dur={dur}", f"ev={_ENGINE_VER}"]
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    cache_path = os.path.join(_ARTIFACT_DIR, "aviz", f"{key}.mkv")

    cmd = ["ffmpeg", "-y", "-i", source,
           "-filter_complex", f"[0:a]{viz}[v]", "-map", "[v]",
           "-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuv420p",
           "-t", str(dur), cache_path]
    return _finalize_generated_object(cache_path, cmd, [source], dur)


def beat_sync(audio_source, *, min_bpm=60, max_bpm=200):
    """svbeat(numpy/scipyのみのビート検出)をDSLに統合し、拍時刻を返す。

    audio_source: 音声/動画ファイルパス（svbeatがffmpegでデコードする）
    min_bpm/max_bpm: svbeat.detect_beatsに渡すテンポ探索範囲

    戻り値: {"bpm": float, "beats": [秒,...], "onsets": [秒,...], "duration": float}
    （svbeat.detect_beats() と同じ形式。そのまま snap_times()/beats_to_keyframes()
    に渡せる）

    解析結果は audio_source のFFP + min_bpm/max_bpm をキーに
    __cache__/artifacts/beats/ へJSONキャッシュし、同じ入力の再解析を避ける。
    svbeat.py または numpy/scipy が無い場合は導入方法を含む日本語エラーにする。
    """
    if not isinstance(audio_source, str):
        raise TypeError(
            f"beat_sync: audio_source はパス文字列で指定してください: {audio_source!r}")
    if not os.path.exists(audio_source):
        raise FileNotFoundError(
            f"beat_sync: 音声/動画ファイルが見つかりません: {audio_source}")
    try:
        import svbeat as _svbeat
    except ImportError as e:
        raise ImportError(
            "beat_sync() には svbeat.py と numpy/scipy が必要です。\n"
            "scriptvedit.py と同じディレクトリに svbeat.py を配置し、"
            "`pip install numpy scipy` を実行してください。"
            f"(元エラー: {e})") from e

    sig = _source_signature(audio_source)
    key_str = (f"{sig}||min_bpm={min_bpm}||max_bpm={max_bpm}||ev={_ENGINE_VER}")
    key = hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:16]
    cache_path = os.path.join(_ARTIFACT_DIR, "beats", f"{key}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # 破損キャッシュは無視して再解析（self-heal）
            pass

    try:
        result = _svbeat.detect_beats(
            audio_source, min_bpm=min_bpm, max_bpm=max_bpm)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"beat_sync: ビート検出に失敗しました: {e}") from e

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    tmp_path = cache_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    os.replace(tmp_path, cache_path)
    return result


# --- 遅延解決の相互参照（関数本体からのみ使用: 循環importを避けるため末尾で束縛）---
from scriptvedit.effects.basic import again
from scriptvedit.effects.time import speed
from scriptvedit.media import _finalize_generated_object, _source_signature
from scriptvedit.objects import AudioEffect, Object
from scriptvedit.project import Project
from scriptvedit.state import _ARTIFACT_DIR, _ENGINE_VER, _detect_media_type, _suggest_hint
from scriptvedit.text import text
from scriptvedit.timeline import anchor
from scriptvedit.validate import _require_number
from scriptvedit.web import subtitle
