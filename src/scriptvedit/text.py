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


# --- テキスト/字幕（drawtext・subtitles）ヘルパー ---

# 日本語表示用フォントの既定候補（Windows）。先頭から存在するものを採用。
_DEFAULT_FONT_CANDIDATES = [
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/msmincho.ttc",
]


def _resolve_font(font):
    """フォントパスを解決。font省略時は既定候補から存在するものを返す。
    見つからない場合は日本語エラーで案内する。"""
    if font is not None:
        path = font.replace("\\", "/")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"指定フォントが見つかりません: {font}\n"
                f"日本語表示には .ttc/.ttf の実在パスを指定してください "
                f"(例: C:/Windows/Fonts/meiryo.ttc)")
        return path
    for cand in _DEFAULT_FONT_CANDIDATES:
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError(
        "既定の日本語フォントが見つかりませんでした。\n"
        "font= に実在するフォントパスを明示してください "
        "(例: font='C:/Windows/Fonts/meiryo.ttc')。\n"
        f"探索した候補: {', '.join(_DEFAULT_FONT_CANDIDATES)}")


def _escape_ffpath(path):
    """フィルタグラフのファイルパスをエスケープ（\\→/、:→\\:）してクォート。
    fontfile / subtitles=filename 用。"""
    p = path.replace("\\", "/").replace(":", "\\:")
    return f"'{p}'"


def _escape_textfile_content(s):
    """drawtext textfile の中身用エスケープ。ファイル内容には filtergraph の
    引用符/区切りは作用せず、drawtext のテキスト展開(% と \\)のみ効くため、
    \\→\\\\ と %→\\% だけをエスケープすればよい（:や'はそのまま literal 表示）。
    実測で確認済み（単一引用符 inline は ' の literal 化が描画されず不可）。"""
    return s.replace("\\", "\\\\").replace("%", "\\%")


def _ensure_textfile(content):
    """テキスト内容を content-addressed なキャッシュファイルに書き出しパスを返す。
    drawtext の textfile= で参照する。任意の文字（'、:、% 等）を確実に表示できる。"""
    body = _escape_textfile_content(content)
    key = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    path = os.path.join(_ARTIFACT_DIR, "text", f"{key}.txt")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    return path


def _escape_counter_literal(s):
    """counter の format 前後リテラル（inline text= 内）用エスケープ。
    inline 値は単一引用符で包むが、FFmpeg 8.0 では引用符内でも : , が区切り
    扱いになるためエスケープする。' は inline では確実に描画できないため拒否。"""
    if "'" in s:
        raise ValueError(
            "counter: format のリテラル部分にアポストロフィ(')は使用できません。"
            "アポストロフィを含む固定文字は text() を併用してください。")
    return (s.replace("\\", "\\\\").replace("%", "\\%")
             .replace(":", "\\:").replace(",", "\\,"))


def _validate_text_size(func, size_expr):
    """size は定数のみ許可。FFmpeg 8.0 の drawtext は fontsize を式にすると
    SEGV(0xC0000005)する（copy/setsar バリアでも回避不可・実測）。
    x/y/alpha のアニメーションは安全に利用できる。"""
    if not isinstance(size_expr, Const):
        raise ValueError(
            f"{func}: size は定数のみ対応です（アニメーション不可）。\n"
            f"FFmpeg 8.0 の drawtext は fontsize を式にすると SEGV するため、"
            f"サイズ変化は非対応です。x/y/alpha はアニメーション可能です。")
    return size_expr


def _text_size_opt(size_expr, u_expr):
    """fontsize オプション文字列を返す（size は定数のみ・_validate_text_size で担保）"""
    return f"fontsize={int(size_expr.value)}"


def _text_anchor_xy(x_expr, y_expr, u_expr, anchor):
    """テキスト配置の x/y drawtext 式を返す。
    anchor='center': (frac*W - text_w/2, frac*H - text_h/2)
    anchor='left'  : (frac*W, frac*H)   ※左上基準
    x/y は 0..1 のキャンバス比率。"""
    xf = x_expr.to_ffmpeg(u_expr)
    yf = y_expr.to_ffmpeg(u_expr)
    if anchor == "left":
        return f"x='({xf})*W'", f"y='({yf})*H'"
    return f"x='({xf})*W-text_w/2'", f"y='({yf})*H-text_h/2'"


def _build_drawtext_filter(spec, text_opt, start, dur, *, enable=None):
    """1個の drawtext フィルタ文字列を構築（text/typewriter/counter 共通）。
    text_opt: 完成済みの "textfile=..." または "text=..." オプション文字列。"""
    u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
    font = _escape_ffpath(spec["font"])
    x_opt, y_opt = _text_anchor_xy(spec["x"], spec["y"], u_expr, spec["anchor"])
    opts = [f"fontfile={font}"]
    opts.append(text_opt)
    opts.append(_text_size_opt(spec["size"], u_expr))
    opts.append(f"fontcolor={spec['color']}")
    opts.append(x_opt)
    opts.append(y_opt)
    alpha_expr = spec["alpha"]
    if not (isinstance(alpha_expr, Const) and alpha_expr.value == 1.0):
        opts.append(f"alpha='clip({alpha_expr.to_ffmpeg(u_expr)}\\,0\\,1)'")
    if spec.get("box"):
        opts.append("box=1")
        opts.append(f"boxcolor={spec['box_color']}")
        opts.append(f"boxborderw={spec['box_border']}")
    if enable is not None:
        opts.append(f"enable='{enable}'")
    return "drawtext=" + ":".join(opts)


def _build_text_filters(obj, start, dur):
    """media_type=='text' Object の映像フィルタ（drawtext/subtitles）を返す。
    start/dur はタイムライン上の表示開始時刻/尺（u 正規化に使用）。"""
    spec = obj._text_spec
    kind = spec["kind"]

    if kind == "progress_bar":
        # 動画全体の進行バー: 透明キャンバスに geq で帯を描画。
        # 進行は t/総尺（clip(T/total, 0, 1)）で毎フレーム更新する。
        proj = Project._current
        total = proj.duration if proj and proj.duration else dur
        h = spec["height"]
        yfrac = spec["y"]
        br, bgc, bb, ba = spec["bar_rgba"]
        tr, tg, tb, ta = spec["track_rgba"]
        top = f"({yfrac}*(H-{h}))"
        prog = f"clip(T/{total}\\,0\\,1)"
        bar = f"lte(X\\,W*{prog})"
        band = f"gte(Y\\,{top})*lt(Y\\,{top}+{h})"
        return [
            "format=rgba",
            f"geq=r='if({bar}\\,{br}\\,{tr})'"
            f":g='if({bar}\\,{bgc}\\,{tg})'"
            f":b='if({bar}\\,{bb}\\,{tb})'"
            f":a='({band})*if({bar}\\,{ba}\\,{ta})'",
        ]

    if kind == "subtitles":
        parts = [f"subtitles=filename={_escape_ffpath(spec['srt'])}"]
        if spec.get("style"):
            raw = spec["style"]
            # force_style は単一引用符で囲むため、'→\' ではクォートが閉じて
            # filtergraph が壊れる。アポストロフィを含む style は早期に拒否する。
            if "'" in raw:
                raise ValueError(
                    "subtitles: style にアポストロフィ(')は使用できません "
                    f"(force_style のクォートが壊れます): {raw!r}")
            style = raw.replace("\\", "\\\\")
            parts[0] += f":force_style='{style}'"
        return parts

    if kind == "text":
        text_opt = f"textfile={_escape_ffpath(_ensure_textfile(spec['content']))}"
        return [_build_drawtext_filter(spec, text_opt, start, dur)]

    if kind == "typewriter":
        content = spec["content"]
        n = len(content)
        if n == 0:
            return []
        cps = spec["cps"]
        filters = []
        for i in range(n):
            prefix = content[:i + 1]
            t_on = start + i / cps
            if i < n - 1:
                # 右端 exclusive の半開区間（隣接窓の境界フレーム二重描画を防ぐ）
                t_off = start + (i + 1) / cps
                enable = f"gte(t\\,{t_on:.4f})*lt(t\\,{t_off:.4f})"
            else:
                # 最後の全文は終了まで保持（上限はオーバーレイ側のenableで制御）
                enable = f"gte(t\\,{t_on:.4f})"
            text_opt = f"textfile={_escape_ffpath(_ensure_textfile(prefix))}"
            filters.append(
                _build_drawtext_filter(spec, text_opt, start, dur, enable=enable))
        return filters

    if kind == "counter":
        # value = from_ + (to-from_)*u を drawtext の %{eif} で整数表示（inline展開）
        # %{eif} は切り捨てのため、四捨五入相当に +0.5*sign(to-from_) を加えて
        # 目標値 to に到達させる（u<1 でも to まで表示されるように）。
        u_expr = f"clip((t-{start})/{dur}\\,0\\,1)"
        val_expr = (spec["from_"] + (spec["to"] - spec["from_"]) * Var("u")
                    + 0.5 * sign(spec["to"] - spec["from_"]))
        val_ff = val_expr.to_ffmpeg(u_expr)
        eif = f"%{{eif\\:{val_ff}\\:d"
        if spec["width"] is not None:
            eif += f"\\:{spec['width']}"
        eif += "}"
        prefix = _escape_counter_literal(spec["prefix"])
        suffix = _escape_counter_literal(spec["suffix"])
        text_opt = "text='" + prefix + eif + suffix + "'"
        return [_build_drawtext_filter(spec, text_opt, start, dur)]

    raise ValueError(f"未知のテキスト種別: {kind}")


def _new_text_object(spec):
    """media_type=='text' の Object を生成して現在のProjectに登録する。
    実体ファイルを持たず、レンダ時に透明lavfi + drawtext/subtitles で描画する。"""
    obj = Object.__new__(Object)
    obj.source = spec["synthetic_source"]
    obj.transforms = []
    obj.effects = []
    obj.audio_effects = []
    obj.duration = None
    obj._duration_auto = False
    obj.start_time = 0
    obj.priority = 0
    obj.media_type = "text"
    obj._until_anchor = None
    obj._until_offset = 0.0
    obj._anchor_name = None
    obj._advance = True
    obj._priority_override = None
    obj._video_deleted = False
    obj._audio_deleted = False
    obj._web_source = None
    obj._web_size = None
    obj._web_fps = None
    obj._web_data = {}
    obj._web_name = None
    obj._web_debug_frames = False
    obj._web_deps = []
    obj._has_video = True
    obj._has_audio = False
    obj._text_spec = spec
    if Project._current is not None:
        Project._current.objects.append(obj)
    return obj


# --- テキスト系ファクトリ（映像Object, drawtext/subtitlesベース） ---

_TEXT_ANCHORS = ("center", "left")


def _text_synthetic_source(spec_key):
    """テキストObject用の合成ソースパス（実体なし・署名/一意化用）"""
    h = hashlib.sha256(spec_key.encode("utf-8")).hexdigest()[:12]
    return f"text://{h}.txt"


def text(content, *, x=0.5, y=0.5, size=48, color="white", font=None,
         box=False, box_color="black@0.5", box_border=10,
         alpha=1.0, anchor="center"):
    """drawtextでテキストを直接描画する映像Object（透明キャンバス全面）。

    x/y/alpha は 0..1 のキャンバス比率で Expr/lambda 可（liveアニメ）。
    size は定数のみ（FFmpeg 8.0 drawtext の fontsize 式は SEGV のため）。
    日本語表示にはfont指定を推奨（未指定はmeiryo等の既定候補を自動探索）。
    タイムラインには image と同様 .time(秒) で配置する。
    """
    if anchor not in _TEXT_ANCHORS:
        raise ValueError(f"text: anchor は {_TEXT_ANCHORS} のいずれか: {anchor!r}")
    spec = {
        "kind": "text",
        "content": str(content),
        "x": _resolve_param(x), "y": _resolve_param(y),
        "size": _validate_text_size("text", _resolve_param(size)),
        "alpha": _resolve_param(alpha),
        "color": color, "font": _resolve_font(font),
        "box": bool(box), "box_color": box_color, "box_border": box_border,
        "anchor": anchor,
    }
    spec["synthetic_source"] = _text_synthetic_source(
        f"text|{content}|{x}|{y}|{size}|{color}|{anchor}")
    return _new_text_object(spec)


def typewriter(content, *, cps=10, x=0.5, y=0.5, size=48, color="white",
               font=None, box=False, box_color="black@0.5", box_border=10,
               alpha=1.0, anchor="left"):
    """textの派生。1文字ずつ表示（n個のdrawtextを各文字の表示時刻でenable）。
    cps: 1秒あたりの表示文字数。既定anchorは左上（左揃えで打ち出す）。"""
    if anchor not in _TEXT_ANCHORS:
        raise ValueError(f"typewriter: anchor は {_TEXT_ANCHORS} のいずれか: {anchor!r}")
    if cps <= 0:
        raise ValueError(f"typewriter: cps は正の数を指定してください: {cps}")
    spec = {
        "kind": "typewriter",
        "content": str(content), "cps": float(cps),
        "x": _resolve_param(x), "y": _resolve_param(y),
        "size": _validate_text_size("typewriter", _resolve_param(size)),
        "alpha": _resolve_param(alpha),
        "color": color, "font": _resolve_font(font),
        "box": bool(box), "box_color": box_color, "box_border": box_border,
        "anchor": anchor,
    }
    spec["synthetic_source"] = _text_synthetic_source(
        f"tw|{content}|{cps}|{x}|{y}|{size}|{color}|{anchor}")
    return _new_text_object(spec)


def _parse_counter_format(fmt):
    """counterのformatを (prefix, suffix, width) に分解。整数指定のみ対応。"""
    i = fmt.find("%")
    if i < 0:
        raise ValueError(
            f"counter: format に数値プレースホルダ(%d 等)が必要です: {fmt!r}")
    j = i + 1
    zero = False
    if j < len(fmt) and fmt[j] == "0":
        zero = True
        j += 1
    digits = ""
    while j < len(fmt) and fmt[j].isdigit():
        digits += fmt[j]
        j += 1
    if j >= len(fmt):
        raise ValueError(f"counter: format の変換指定が不完全です: {fmt!r}")
    conv = fmt[j]
    if conv not in ("d", "i"):
        raise ValueError(
            f"counter: format は整数指定(%d, %03d 等)のみ対応です: {fmt!r}\n"
            f"小数表示は未対応です。")
    width = int(digits) if (zero and digits) else None
    return fmt[:i], fmt[j + 1:], width


def counter(from_, to, *, format="%d", x=0.5, y=0.5, size=48, color="white",
            font=None, box=False, box_color="black@0.5", box_border=10,
            alpha=1.0, anchor="center"):
    """数値カウントアップ映像Object。drawtextの%{eif}式で from_→to を補間表示。
    format は整数指定(%d, %03d 等)。前後のリテラル文字も表示可能。"""
    if anchor not in _TEXT_ANCHORS:
        raise ValueError(f"counter: anchor は {_TEXT_ANCHORS} のいずれか: {anchor!r}")
    prefix, suffix, width = _parse_counter_format(format)
    _escape_counter_literal(prefix)  # アポストロフィ等の早期検証（inline不可文字）
    _escape_counter_literal(suffix)
    spec = {
        "kind": "counter",
        "from_": _resolve_param(from_), "to": _resolve_param(to),
        "prefix": prefix, "suffix": suffix, "width": width,
        "x": _resolve_param(x), "y": _resolve_param(y),
        "size": _validate_text_size("counter", _resolve_param(size)),
        "alpha": _resolve_param(alpha),
        "color": color, "font": _resolve_font(font),
        "box": bool(box), "box_color": box_color, "box_border": box_border,
        "anchor": anchor,
    }
    spec["synthetic_source"] = _text_synthetic_source(
        f"counter|{from_}|{to}|{format}|{x}|{y}|{size}|{color}|{anchor}")
    return _new_text_object(spec)


def subtitles(srt_file, *, style=None):
    """SRT字幕ファイルをsubtitlesフィルタで合成する映像Object。
    style: ASSのforce_styleスタイル文字列（例 "FontName=Meiryo,FontSize=28"）。
    SRTは自身のタイムコードで表示されるため .time(全体尺) で開始0に配置する想定。"""
    if not isinstance(srt_file, str):
        raise TypeError(f"subtitles: srt_file はパス文字列で指定してください: {srt_file!r}")
    if not os.path.exists(srt_file):
        raise FileNotFoundError(f"subtitles: 字幕ファイルが見つかりません: {srt_file}")
    ext = os.path.splitext(srt_file)[1].lower()
    if ext not in (".srt", ".ass", ".vtt"):
        raise ValueError(
            f"subtitles: 対応拡張子は .srt/.ass/.vtt です: {srt_file}")
    spec = {
        "kind": "subtitles",
        "srt": srt_file,
        "style": style,
        # drawtext系オプションは未使用だが _new_text_object の一貫性のため保持
        "x": Const(0.5), "y": Const(0.5), "size": Const(48), "alpha": Const(1.0),
        "color": "white", "font": None, "box": False,
        "box_color": "black@0.5", "box_border": 10, "anchor": "center",
    }
    try:
        ffp = _file_fingerprint(srt_file)
        spec["synthetic_source"] = _text_synthetic_source(
            f"subs|{ffp[0]}|{ffp[1]}|{ffp[2]}|{style}")
    except OSError:
        spec["synthetic_source"] = _text_synthetic_source(f"subs|{srt_file}|{style}")
    obj = _new_text_object(spec)
    # SRTをレイヤー依存として登録（cache鮮度検証で字幕変更を検知）
    proj = Project._current
    if proj is not None and proj._current_layer_file:
        proj._extra_layer_deps.setdefault(
            proj._current_layer_file, []).append(srt_file)
    return obj


# --- karaoke（ASS \k タグによるカラオケ風ハイライト字幕） ---

# 既知の色名 -> #RRGGBB（karaoke styleの簡易色指定用）
_ASS_NAMED_COLORS = {
    "white": "FFFFFF", "black": "000000", "red": "FF0000", "green": "00FF00",
    "blue": "0000FF", "yellow": "FFFF00", "cyan": "00FFFF", "magenta": "FF00FF",
    "orange": "FFA500", "gray": "808080", "grey": "808080", "pink": "FFC0CB",
}


def _color_to_ass(color, alpha=0):
    """色指定をASSの &HAABBGGRR 16進文字列に変換する。
    'white'等の既知色名 / '#RRGGBB' / 既にASS形式('&H..'始まり)のいずれかを受け付ける。"""
    if isinstance(color, str) and color.upper().startswith("&H"):
        return color
    if not isinstance(color, str):
        raise ValueError(f"karaoke: 色指定は文字列で指定してください: {color!r}")
    name = color.lower()
    hexrgb = _ASS_NAMED_COLORS.get(name, color.lstrip("#"))
    if len(hexrgb) != 6 or any(c not in "0123456789abcdefABCDEF" for c in hexrgb):
        raise ValueError(
            f"karaoke: 未対応の色指定です: {color!r}"
            f"（既知色名 {sorted(_ASS_NAMED_COLORS)} か #RRGGBB を指定してください）")
    rr, gg, bb = hexrgb[0:2], hexrgb[2:4], hexrgb[4:6]
    return f"&H{alpha:02X}{bb}{gg}{rr}".upper()


def _fmt_ass_time(t):
    """秒 -> ASSタイムコード（H:MM:SS.cc、センチ秒単位）"""
    cs_total = int(round(float(t) * 100))
    h, rem = divmod(cs_total, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass_text(s):
    """ASSダイアログテキスト用エスケープ（\\、{}、改行）"""
    return (s.replace("\\", "\\\\").replace("{", "\\{")
             .replace("}", "\\}").replace("\r\n", "\\N").replace("\n", "\\N"))


def _karaoke_tokenize(text):
    """カラオケ行を\\kタグの単位（語）に分割する。
    空白を含む場合は空白区切り（末尾の空白を保持）、無ければ1文字ずつに分割
    （日本語歌詞のように分かち書きが無い場合の既定挙動）。"""
    if any(c.isspace() for c in text):
        toks = re.findall(r"\S+\s*", text)
        return toks if toks else [text]
    return list(text)


def karaoke(lines, *, style=None):
    """カラオケ風ハイライト字幕（ASSの\\kタグ）を生成する映像Object。

    lines: [(start, end, "歌詞"), ...] または
           [(start, end, "歌詞", [word_durations...]), ...] のリスト。
    - word_durations省略時: 行内の語（分割規約は_karaoke_tokenize参照）に
      (end-start)を均等割りして\\kタグを割り当てる。
    - word_durations指定時: 分割された語の数と同じ長さの秒数リストを指定する
      （語ごとのハイライト時間、\\kタグの単位はセンチ秒に変換）。
    style: {"font", "size", "primary"（既に発音済みの色）, "secondary"（未発音の色）,
            "outline_color", "back_color", "alignment", "margin_v", "outline",
            "shadow", "bold"} を上書きする辞書（省略キーは既定値）。

    生成したASSは歌詞+タイミング+styleのSHA256でcontent-addressedキャッシュに
    書き出し、subtitles()経由でsubtitlesフィルタとして合成する。
    SRT/ASSと同様に .time(全体尺) で開始0に配置する想定。
    """
    if not isinstance(lines, (list, tuple)) or len(lines) == 0:
        raise ValueError("karaoke: lines には1行以上指定してください")
    st = dict(style or {})
    font = st.get("font", "Meiryo")
    size = int(st.get("size", 48))
    primary = _color_to_ass(st.get("primary", "yellow"))
    secondary = _color_to_ass(st.get("secondary", "white"))
    outline_color = _color_to_ass(st.get("outline_color", "black"))
    back_color = _color_to_ass(st.get("back_color", "black"), alpha=0x80)
    alignment = int(st.get("alignment", 2))
    margin_v = int(st.get("margin_v", 60))
    outline_w = st.get("outline", 2)
    shadow = st.get("shadow", 0)
    bold = -1 if st.get("bold", True) else 0

    body_lines = []
    for idx, line in enumerate(lines):
        if not isinstance(line, (list, tuple)) or len(line) not in (3, 4):
            raise ValueError(
                f"karaoke: lines[{idx}] は (start,end,text) または "
                f"(start,end,text,word_durations) を指定してください: {line!r}")
        if len(line) == 3:
            t0, t1, txt = line
            word_durs = None
        else:
            t0, t1, txt, word_durs = line
        t0 = float(t0)
        t1 = float(t1)
        if t1 <= t0:
            raise ValueError(
                f"karaoke: lines[{idx}] の end は start より後が必要です: {line!r}")
        tokens = _karaoke_tokenize(str(txt))
        if not tokens:
            continue
        if word_durs is not None:
            word_durs = list(word_durs)
            if len(word_durs) != len(tokens):
                raise ValueError(
                    f"karaoke: lines[{idx}] の word_durations 数({len(word_durs)})が"
                    f"分割語数({len(tokens)})と一致しません。分割結果: {tokens}\n"
                    f"（分割規約: 空白を含む行は空白区切り、無ければ1文字ずつ）")
            for d in word_durs:
                _require_number("karaoke", "word_durations要素", d, 0.001, None)
        else:
            each = (t1 - t0) / len(tokens)
            word_durs = [each] * len(tokens)
        # \k はセンチ秒単位。各語独立に round(d*100) すると丸め誤差が累積して
        # 総和が行尺とずれる。累積器方式で
        # \k_i = round(cumsum_i*100) - round(cumsum_{i-1}*100) とし、
        # 総和を round(cumsum_n*100) に一致させる。
        k_parts = []
        cum = 0.0
        prev_cs = 0
        for tok, d in zip(tokens, word_durs):
            cum += float(d)
            cs = round(cum * 100)
            k = cs - prev_cs
            prev_cs = cs
            k_parts.append(f"{{\\k{k}}}{_escape_ass_text(tok)}")
        k_text = "".join(k_parts)
        body_lines.append(
            f"Dialogue: 0,{_fmt_ass_time(t0)},{_fmt_ass_time(t1)},Karaoke,,0,0,0,,{k_text}")

    if not body_lines:
        raise ValueError("karaoke: 有効な行がありません（全行が空テキストでした）")

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Karaoke,{font},{size},{primary},{secondary},{outline_color},"
        f"{back_color},{bold},0,0,0,100,100,0,0,1,{outline_w},{shadow},"
        f"{alignment},20,20,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    content = header + "\n".join(body_lines) + "\n"

    key = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    ass_path = os.path.join(_ARTIFACT_DIR, "karaoke", f"{key}.ass")
    if not os.path.exists(ass_path):
        os.makedirs(os.path.dirname(ass_path), exist_ok=True)
        tmp_path = ass_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, ass_path)

    return subtitles(ass_path)


# --- 遅延解決の相互参照（関数本体からのみ使用: 循環importを避けるため末尾で束縛）---
from scriptvedit.cache import _file_fingerprint
from scriptvedit.expr import Const, Var, _resolve_param, round, sign
from scriptvedit.objects import Object
from scriptvedit.project import Project
from scriptvedit.state import _ARTIFACT_DIR
from scriptvedit.timeline import anchor
from scriptvedit.validate import _require_number
