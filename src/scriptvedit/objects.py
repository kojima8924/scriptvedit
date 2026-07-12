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


class TransformChain:
    """複数のTransformをまとめたチェーン"""
    def __init__(self, transforms):
        self.transforms = list(transforms)

    def __or__(self, other):
        """TransformChain | Transform/TransformChain → TransformChain"""
        if isinstance(other, Transform):
            return TransformChain(self.transforms + [other])
        if isinstance(other, TransformChain):
            return TransformChain(self.transforms + other.transforms)
        return NotImplemented

    def __invert__(self):
        """~(tf1 | tf2 | tf3) → chain内全opに quality='fast' 付与"""
        new_list = [t._copy(quality="fast") for t in self.transforms]
        return TransformChain(new_list)

    def __pos__(self):
        """+(tf1 | tf2 | tf3) → 末尾opに policy='force'"""
        new_list = list(self.transforms)
        new_list[-1] = new_list[-1]._copy(policy="force")
        return TransformChain(new_list)

    def __neg__(self):
        """-(tf1 | tf2 | tf3) → 末尾opに policy='off'"""
        new_list = list(self.transforms)
        new_list[-1] = new_list[-1]._copy(policy="off")
        return TransformChain(new_list)

    def __repr__(self):
        return f"TransformChain({self.transforms})"


class EffectChain:
    """複数のEffectをまとめたチェーン"""
    def __init__(self, effects):
        self.effects = list(effects)

    def __and__(self, other):
        """EffectChain & Effect/EffectChain → EffectChain"""
        if isinstance(other, Effect):
            return EffectChain(self.effects + [other])
        if isinstance(other, EffectChain):
            return EffectChain(self.effects + other.effects)
        return NotImplemented

    def __invert__(self):
        """~(eff1 & eff2) → chain内全opに quality='fast' 付与"""
        new_list = [e._copy(quality="fast") for e in self.effects]
        return EffectChain(new_list)

    def __pos__(self):
        """+(eff1 & eff2) → 末尾opに policy='force'"""
        new_list = list(self.effects)
        new_list[-1] = new_list[-1]._copy(policy="force")
        return EffectChain(new_list)

    def __neg__(self):
        """-(eff1 & eff2) → 末尾opに policy='off'"""
        new_list = list(self.effects)
        new_list[-1] = new_list[-1]._copy(policy="off")
        return EffectChain(new_list)

    def __repr__(self):
        return f"EffectChain({self.effects})"


class AudioEffect:
    """音声エフェクト（again, afade, adelete, atrim, atempo等）"""
    def __init__(self, name, **params):
        self.name = name
        self.params = params

    def __and__(self, other):
        if isinstance(other, AudioEffect):
            return AudioEffectChain([self, other])
        if isinstance(other, AudioEffectChain):
            return AudioEffectChain([self] + other.effects)
        if isinstance(other, _DisabledAudioEffect):
            return AudioEffectChain([self, other])
        return NotImplemented

    def __invert__(self):
        return _DisabledAudioEffect(self)

    def __repr__(self):
        return f"AudioEffect({self.name}, {self.params})"


class AudioEffectChain:
    """複数のAudioEffectをまとめたチェーン"""
    def __init__(self, effects):
        self.effects = list(effects)

    def __and__(self, other):
        if isinstance(other, AudioEffect):
            return AudioEffectChain(self.effects + [other])
        if isinstance(other, AudioEffectChain):
            return AudioEffectChain(self.effects + other.effects)
        if isinstance(other, _DisabledAudioEffect):
            return AudioEffectChain(self.effects + [other])
        return NotImplemented

    def __invert__(self):
        return _DisabledAudioEffect(self)

    def __repr__(self):
        return f"AudioEffectChain({self.effects})"


class _DisabledAudioEffect:
    """無効化AudioEffect"""
    def __init__(self, original):
        self.original = original

    def __and__(self, other):
        if isinstance(other, (AudioEffect, _DisabledAudioEffect)):
            return AudioEffectChain([self, other])
        if isinstance(other, AudioEffectChain):
            return AudioEffectChain([self] + other.effects)
        return NotImplemented

    def __rand__(self, other):
        if isinstance(other, AudioEffect):
            return AudioEffectChain([other, self])
        if isinstance(other, AudioEffectChain):
            return AudioEffectChain(other.effects + [self])
        return NotImplemented

    def __invert__(self):
        return self.original


class Transform:
    def __init__(self, name, *, policy="auto", quality="final", **params):
        self.name = name
        self.params = params
        self.policy = policy
        self.quality = quality

    def _copy(self, **overrides):
        """属性をコピーした新Transformを返す"""
        kw = dict(policy=self.policy, quality=self.quality, **self.params)
        kw.update(overrides)
        return Transform(self.name, **kw)

    def __or__(self, other):
        """Transform | Transform/TransformChain → TransformChain"""
        if isinstance(other, Transform):
            return TransformChain([self, other])
        if isinstance(other, TransformChain):
            return TransformChain([self] + other.transforms)
        return NotImplemented

    def __invert__(self):
        """~op → quality='fast'"""
        return self._copy(quality="fast")

    def __pos__(self):
        """+op → policy='force'"""
        return self._copy(policy="force")

    def __neg__(self):
        """-op → policy='off'"""
        return self._copy(policy="off")

    def __repr__(self):
        return f"Transform({self.name}, {self.params})"


class Effect:
    def __init__(self, name, *, policy="auto", quality="final", **params):
        self.name = name
        self.params = params
        self.policy = policy
        self.quality = quality

    def _copy(self, **overrides):
        """属性をコピーした新Effectを返す"""
        kw = dict(policy=self.policy, quality=self.quality, **self.params)
        kw.update(overrides)
        new = Effect(self.name, **kw)
        if hasattr(self, '_morph_target'):
            new._morph_target = self._morph_target
        return new

    def __and__(self, other):
        """Effect & Effect/EffectChain → EffectChain"""
        if isinstance(other, Effect):
            return EffectChain([self, other])
        if isinstance(other, EffectChain):
            return EffectChain([self] + other.effects)
        return NotImplemented

    def __invert__(self):
        """~op → quality='fast'"""
        return self._copy(quality="fast")

    def __pos__(self):
        """+op → policy='force'"""
        return self._copy(policy="force")

    def __neg__(self):
        """-op → policy='off'"""
        return self._copy(policy="off")

    def __repr__(self):
        return f"Effect({self.name}, {self.params})"


_WEB_KWARGS = {"duration", "size", "fps", "data", "name", "debug_frames", "deps"}

# slide(): web Objectの_web_dataに埋め込むページ切替キー（内部規約・非公開API）
_SLIDE_PAGE_KEY = "__svt_slide_page__"


class Object:
    def __init__(self, source, **kwargs):
        self.source = source
        self.transforms = []
        self.effects = []
        self.audio_effects = []
        self.duration = None
        self._duration_auto = False
        self.start_time = 0
        self.priority = 0
        self.media_type = _detect_media_type(source)
        self._until_anchor = None
        self._until_offset = 0.0
        self._anchor_name = None
        self._advance = True
        self._priority_override = None
        self._video_deleted = False
        self._audio_deleted = False
        # web専用属性（常に初期化）
        self._web_source = None
        self._web_size = None
        self._web_fps = None
        self._web_data = {}
        self._web_name = None
        self._web_debug_frames = False
        self._web_deps = []

        # web Object のバリデーションと属性設定
        if self.media_type == "web":
            unknown = set(kwargs.keys()) - _WEB_KWARGS
            if unknown:
                hint = _suggest_hint(sorted(unknown)[0], _WEB_KWARGS)
                raise TypeError(
                    f"不明なキーワード引数: {', '.join(sorted(unknown))}。"
                    f"使用可能: {', '.join(sorted(_WEB_KWARGS))}{hint}")
            if "duration" not in kwargs:
                raise ValueError("web Object には duration が必須です")
            if "size" not in kwargs:
                raise ValueError("web Object には size が必須です")
            self._web_source = source
            self.duration = kwargs["duration"]
            self._web_size = kwargs["size"]
            self._web_fps = kwargs.get("fps")
            self._web_data = kwargs.get("data", {})
            self._web_name = kwargs.get("name") or os.path.splitext(os.path.basename(source))[0]
            self._web_debug_frames = kwargs.get("debug_frames", False)
            self._web_deps = kwargs.get("deps", [])
        elif kwargs:
            raise TypeError(
                f"キーワード引数は web Object (.html/.htm) 専用です: "
                f"{', '.join(sorted(kwargs.keys()))}")

        # has_video / has_audio のデフォルト
        if self.media_type == "image":
            self._has_video = True
            self._has_audio = False
        elif self.media_type == "audio":
            self._has_video = False
            self._has_audio = True
        elif self.media_type == "web":
            self._has_video = True
            self._has_audio = False
        else:  # video
            self._has_video = True
            self._has_audio = None  # 未判定→ffprobeで解決
        # 現在のProjectに自動登録
        if Project._current is not None:
            Project._current.objects.append(self)

    @property
    def has_video(self):
        if self._video_deleted:
            return False
        return self._has_video if self._has_video is not None else True

    @property
    def has_audio(self):
        if self._audio_deleted:
            return False
        if self._has_audio is None:
            proj = Project._current
            if proj:
                info = proj._probe_media(self.source)
                if info:
                    self._has_audio = info.get("has_audio", False)
                    return self._has_audio
            return False  # probe不可→音声なしと推定（安全側）
        return self._has_audio

    def time(self, duration=None, *, name=None):
        """表示時間を設定。省略時は加工後長(length())で自動決定（layer exec後に確定）"""
        if duration is None:
            if self.media_type in ("image", "text"):
                raise TypeError(
                    "画像/テキストには time() 省略は使えません。time(seconds) を指定してください。")
            self.duration = None
            self._duration_auto = True
        else:
            self.duration = duration
            self._duration_auto = False
        if name is not None:
            self._anchor_name = name
        return self

    def until(self, name, offset=0.0):
        """durationをアンカー時刻まで伸長"""
        self._until_anchor = name
        self._until_offset = offset
        return self

    def show(self, duration, *, priority=None):
        """current_timeを進めずに表示。start=current_time, duration=指定値"""
        self.duration = duration
        self._advance = False
        if priority is not None:
            self._priority_override = priority
        return self

    def show_until(self, name, offset=0.0, *, priority=None):
        """current_timeを進めずにアンカーまで表示"""
        self._until_anchor = name
        self._until_offset = offset
        self._advance = False
        if priority is not None:
            self._priority_override = priority
        return self

    def _append_effect(self, e):
        """Effect追加の共通経路（delete処理・時間系の検証・speedの音声追従）"""
        if e.name == "delete":
            self._video_deleted = True
            return
        if e.name in _TIME_LIVE_EFFECTS and self.media_type in ("image", "text", "web"):
            raise ValueError(
                f"{e.name}: 時間操作Effectは動画素材にのみ適用できます"
                f"（{self.media_type} には適用不可）: {self.source}")
        self.effects.append(e)
        if e.name == "speed" and not self._audio_deleted:
            # 音声付き動画のテンポを自動追従させる（atempo）。
            # length()での二重計上を防ぐためフラグを付ける
            ae = AudioEffect("atempo", rate=e.params.get("factor", 1.0))
            ae._auto_from_speed = True
            self.audio_effects.append(ae)

    def __le__(self, rhs):
        """<= 演算子: Transform/Effect/AudioEffect等を適用"""
        if isinstance(rhs, _DisabledAudioEffect):
            return self  # AudioのDisableだけ残す
        if isinstance(rhs, Transform):
            self.transforms.append(rhs)
        elif isinstance(rhs, TransformChain):
            self.transforms.extend(rhs.transforms)
        elif isinstance(rhs, Effect):
            self._append_effect(rhs)
        elif isinstance(rhs, EffectChain):
            for e in rhs.effects:
                self._append_effect(e)
        elif isinstance(rhs, AudioEffect):
            if rhs.name == "adelete":
                self._audio_deleted = True
            else:
                self.audio_effects.append(rhs)
        elif isinstance(rhs, AudioEffectChain):
            for e in rhs.effects:
                if isinstance(e, _DisabledAudioEffect):
                    continue
                if e.name == "adelete":
                    self._audio_deleted = True
                else:
                    self.audio_effects.append(e)
        else:
            raise TypeError(f"Object <= に渡せるのは Transform/Effect/AudioEffect 等のみ: {type(rhs)}")
        return self

    def compute(self, duration=None):
        """タイムライン外で素材を生成。PNG(静止) or WebM(動画)を返す"""
        # live effects チェック（時間系 speed/reverse/freeze_frame は
        # _build_compute_video_cmd の前処理フィルタでベイクできるため許可）
        for e in self.effects:
            if e.name in ("move", "delete", "shake", "blend_mode"):
                raise ValueError(
                    f"compute() では live Effect '{e.name}' は使用できません。"
                    f"bakeable Effect のみ使用可能です。")
        # Project.objects から除外
        proj = Project._current
        if proj is not None and self in proj.objects:
            proj.objects.remove(self)
        # キャッシュパス計算
        cache_path = self._compute_cache_path(duration)
        # 差し替え前の元素材パスを保持（レイヤーキャッシュの依存記録で
        # 導出キャッシュパスではなく元素材の変更を検知できるようにする）
        self._origin_sources = (getattr(self, '_origin_sources', None) or []) + [self.source]
        # ベイク尺を保持（差し替え後の未生成予定パスへのprobe fallback防止）
        if duration:
            self._resolved_length = duration
        # plan pass: source差し替えのみ
        if proj is not None and proj._mode == "plan":
            self.source = cache_path
            self.media_type = _detect_media_type(cache_path)
            self.transforms = []
            self.effects = []
            return self
        # キャッシュ存在チェック
        if os.path.exists(cache_path):
            self.source = cache_path
            self.media_type = _detect_media_type(cache_path)
            self.transforms = []
            self.effects = []
            return self
        # 生成コマンド構築
        if duration is None:
            cmd = self._build_compute_image_cmd(cache_path)
        else:
            cmd = self._build_compute_video_cmd(cache_path, duration)
        # dry_run: コマンドを記録して生成スキップ
        if proj is not None and getattr(proj, '_dry_run', False):
            proj._pending_compute_cmds[cache_path] = cmd
            self.source = cache_path
            self.media_type = _detect_media_type(cache_path)
            self.transforms = []
            self.effects = []
            return self
        # 実生成
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        _run_ffmpeg_to_cache(cmd, cache_path, timeout=600)
        self.source = cache_path
        self.media_type = _detect_media_type(cache_path)
        self.transforms = []
        self.effects = []
        return self

    @staticmethod
    def from_project(sub_project, *, cache="auto"):
        """ネストコンポジション（プリコンポーズ）: サブProjectを透過webm素材化して
        1つのObjectとして親タイムラインに配置する。

        sub_project: layer() 登録済みの Project。render(alpha=True) 機構で
        透過webmキャッシュ生成物を作り、そのwebmをsourceとするObjectを返す。
        キャッシュ鍵は configure + レイヤーファイルFFP群 + レイヤーが参照する
        素材FFP群から導出する（素材更新で自動再生成）。dry_run 対応。
        cache: 'auto'（キャッシュがあれば再利用）/ 'force'（常に再生成）。
        """
        if not isinstance(sub_project, Project):
            raise TypeError(
                f"from_project: sub_project には Project を指定してください: "
                f"{type(sub_project)}")
        if cache not in ("auto", "force"):
            hint = _suggest_hint(cache, ("auto", "force"))
            raise ValueError(
                f"from_project: cache は 'auto' か 'force' のいずれか: {cache!r}{hint}")
        # 親 = 現在レイヤーを実行中のProject（sub = Project() が _current を
        # 奪うため、_exec_stack から特定する）。レイヤー外では復元先のみ保持
        parent = Project._exec_stack[-1] if Project._exec_stack else None
        if sub_project is parent:
            raise ValueError("from_project: 親Project自身は指定できません")
        if not sub_project._layer_specs:
            raise ValueError(
                "from_project: sub_project に layer() が登録されていません。"
                "sub.layer('xxx.py') でレイヤーを登録してから渡してください。")
        # サブProjectをdry_runで解決し、総尺・依存素材を確定する
        # （Project._current が切り替わるため必ず親へ復元する）
        try:
            sub_project.render("__from_project_probe__.webm",
                               dry_run=True, alpha=True)
        finally:
            Project._current = parent
        total = sub_project.duration

        # 署名: configure + レイヤーファイルFFP群 + レイヤー参照素材FFP群
        sigs = ["from_project",
                f"cfg={sub_project.width}x{sub_project.height}"
                f"@{sub_project.fps}|bg={sub_project.background_color}"
                f"|dur={total}"]
        layer_files = []
        for spec in sub_project._layer_specs:
            sigs.append(
                f"layer={_source_signature(spec['filename'])}|p={spec['priority']}")
            layer_files.append(spec["filename"])
        dep_sources = []
        for srcs in sub_project._layer_sources.values():
            dep_sources.extend(srcs)
        dep_sources = sorted(set(dep_sources))
        for src in dep_sources:
            sigs.append(f"dep={_source_signature(src)}")
        sigs.append(f"ev={_ENGINE_VER}")
        key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
        cache_path = os.path.join(_ARTIFACT_DIR, "subproject", f"{key}.webm")

        parent_mode = getattr(parent, "_mode", None) if parent else None
        parent_dry = bool(getattr(parent, "_dry_run", False)) if parent else False
        if parent is not None and parent_mode == "plan":
            pass  # plan pass: 生成スキップ（尺解決のみ）
        elif cache == "auto" and os.path.exists(cache_path):
            pass  # キャッシュ命中
        elif parent_dry:
            # dry_run: サブProjectの生成コマンド（dict/list）をpendingに記録
            try:
                sub_cmd = sub_project.render(cache_path, dry_run=True, alpha=True)
            finally:
                Project._current = parent
            parent._pending_compute_cmds[cache_path] = sub_cmd
        else:
            # 実生成: 一時パスへレンダし成功時のみ確定（アトミック書き込み）
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            base, ext = os.path.splitext(cache_path)
            tmp_path = f"{base}.tmp{ext}"
            print(f"サブプロジェクト生成: {cache_path}")
            try:
                sub_project.render(tmp_path, alpha=True)
                os.replace(tmp_path, cache_path)
                with _GEN_COUNTER_LOCK:
                    _GEN_COUNTER[0] += 1
            finally:
                Project._current = parent
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        # 親レイヤーの依存として登録（レイヤーキャッシュの鮮度検証に載せる）
        if parent is not None and parent._current_layer_file:
            parent._extra_layer_deps.setdefault(
                parent._current_layer_file, []).extend(layer_files + dep_sources)
        obj = Object(cache_path)
        obj._origin_sources = list(layer_files) + list(dep_sources)
        obj._resolved_length = total
        # 音声有無: dry_run解決済みのサブオブジェクトから確定（未生成キャッシュの
        # probe不能でFalse固定になるのを防ぐ）
        obj._has_audio = any(
            isinstance(o, Object) and o.has_audio for o in sub_project.objects)
        return obj

    def _compute_cache_path(self, duration=None):
        """compute用キャッシュパスを計算"""
        ops = _build_unified_ops(self)
        sigs = []
        try:
            sigs.append(f"ffp={_file_fingerprint(self.source)}")
        except OSError:
            sigs.append(f"src={self.source.replace(chr(92), '/')}")
        sigs.append(_op_prefix_fingerprint(ops))
        quality = "final"
        for _, op in ops:
            if getattr(op, 'quality', 'final') == "fast":
                quality = "fast"
        sigs.append(f"q={quality}")
        sigs.append(f"ev={_ENGINE_VER}")
        if duration is not None:
            proj = Project._current
            fps = proj.fps if proj else 30
            sigs.append(f"dur={duration}")
            sigs.append(f"fps={fps}")
        key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
        src_hash = hashlib.sha256(
            self.source.replace("\\", "/").encode()).hexdigest()[:8]
        ext = ".mkv" if duration is not None else ".png"
        return os.path.join(_ARTIFACT_DIR, "compute", src_hash, f"{key}{ext}")

    def _build_compute_image_cmd(self, cache_path):
        """compute静止画: Transform適用→PNG"""
        temp = Object.__new__(Object)
        temp.source = self.source
        temp.transforms = list(self.transforms)
        temp.effects = []
        filters = _build_transform_filters(temp)
        cmd = ["ffmpeg", "-y", "-i", self.source]
        if filters:
            cmd.extend(["-vf", ",".join(filters)])
        cmd.extend(["-frames:v", "1", "-pix_fmt", "rgba", cache_path])
        return cmd

    def _build_compute_video_cmd(self, cache_path, duration):
        """compute動画: Transform+Effect適用→WebM VP9 alpha"""
        proj = Project._current
        fps = proj.fps if proj else 30
        temp = Object.__new__(Object)
        temp.source = self.source
        temp.transforms = list(self.transforms)
        temp.effects = list(self.effects)
        temp.media_type = self.media_type
        base_dims = _get_base_dimensions(temp)
        filters = _build_transform_filters(temp)
        pre_filters = _build_video_pre_filters(temp)
        filters = pre_filters + filters
        eff_filters, _ = _build_effect_filters(temp, 0, duration, base_dims=base_dims)
        filters.extend(eff_filters)
        cmd = ["ffmpeg", "-y"]
        cmd.extend(_decoder_input_args(self.source, self.media_type, fps))
        if filters:
            cmd.extend(["-vf", ",".join(filters)])
        cmd.extend([
            "-c:v", "ffv1", "-level", "3",
            "-pix_fmt", "yuva444p",
            "-t", str(duration), cache_path,
        ])
        return cmd

    def length(self):
        """加工後の再生時間を返す（ffprobe + 時間影響エフェクト反映）"""
        if self.media_type in ("image", "text"):
            raise TypeError("画像/テキストにはlength()を使えません。動画/音声のみ対応です。")
        if self.media_type == "web":
            if self.duration is None:
                raise TypeError("web Objectにはduration引数が必須です")
            return self.duration
        proj = Project._current
        if proj is None:
            raise RuntimeError("length()にはアクティブなProjectが必要です")
        info = proj._probe_media(self.source)
        if info is None or info.get("duration") is None:
            raise FileNotFoundError(
                f"メディアの長さを取得できません: {self.source}")
        base_dur = info["duration"]
        result = base_dur
        # 映像 時間系（trim/speed/freeze_frame）を並び順に反映
        for e in self.effects:
            if e.name == "trim":
                d = e.params.get("duration")
                if d is not None:
                    result = min(result, d)
            elif e.name == "speed":
                factor = e.params.get("factor", 1.0)
                if factor > 0:
                    result = result / factor
            elif e.name == "freeze_frame":
                # at がその時点の実効尺以上なら静止区間は成立しないため加算しない
                # （_build_video_pre_filters 側では ValueError になるが、length()は
                #   実尺との整合を保つため at>=尺 では +duration を計上しない）
                at = e.params.get("at", 0.0)
                if at < result:
                    result = result + e.params.get("duration", 0.0)
        # 音声atrim/atempo
        for e in self.audio_effects:
            if e.name == "atrim":
                d = e.params.get("duration")
                if d is not None:
                    result = min(result, d)
            elif e.name == "atempo":
                if getattr(e, "_auto_from_speed", False):
                    continue  # speed()由来の自動atempoは映像側で反映済み（二重計上防止）
                rate = e.params.get("rate", 1.0)
                if rate > 0:
                    result = result / rate
        return result

    def _build_web_cmd(self, project, webm_path=None):
        """webクリップ用ffmpegコマンド"""
        cache_dir = os.path.join(_CACHE_DIR, "webclip")
        name = self._web_name
        if webm_path is None:
            webm_path = _web_cache_path(self, project)
        frames_dir = os.path.join(cache_dir, f"{name}_frames")
        frames_pattern = os.path.join(frames_dir, "frame_%05d.png")
        fps = self._web_fps or project.fps
        dur = self.duration
        return [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", frames_pattern,
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-b:v", "0", "-crf", "30",
            "-auto-alt-ref", "0",
            "-t", str(dur),
            webm_path,
        ]

    def _render_web_frames(self, project):
        """Playwrightで HTML を連番PNGにキャプチャ"""
        from playwright.sync_api import sync_playwright
        name = self._web_name
        cache_dir = os.path.join(_CACHE_DIR, "webclip")
        frames_dir = os.path.join(cache_dir, f"{name}_frames")
        os.makedirs(frames_dir, exist_ok=True)
        w, h = self._web_size
        fps = self._web_fps or project.fps
        dur = self.duration
        N = int(dur * fps)
        html_path = os.path.abspath(self._web_source)
        url = f"file:///{html_path.replace(os.sep, '/')}"

        # slide(): ページ切替規約（_SLIDE_PAGE_KEY）が指定されていれば、
        # renderFrame待機の前にページ切替JSフックを実行する
        slide_page = self._web_data.get(_SLIDE_PAGE_KEY)

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(url)
                if slide_page is not None:
                    # window.showSlide(n) があれば呼び出し、無ければ
                    # id="page-N" 要素のみ表示（他のid^="page-"要素は非表示）。
                    # renderFrame未定義ならno-opを注入し、静止スライドとして
                    # 通常のWeb Objectキャプチャ経路をそのまま利用できるようにする。
                    page.evaluate(
                        "(n) => {"
                        "  if (typeof window.showSlide === 'function') {"
                        "    window.showSlide(n);"
                        "  } else {"
                        "    var els = document.querySelectorAll('[id^=\"page-\"]');"
                        "    var target = document.getElementById('page-' + n);"
                        "    if (!target) {"
                        # ゼロ埋めid(page-01等)対応: 数値正規化で一致を探す
                        "      els.forEach(function(el) {"
                        "        var m = el.id.match(/^page-(\\d+)$/);"
                        "        if (m && parseInt(m[1], 10) === parseInt(n, 10)) target = el;"
                        "      });"
                        "    }"
                        "    var shown = 0;"
                        "    els.forEach(function(el) {"
                        "      var vis = (el === target);"
                        "      el.style.display = vis ? '' : 'none';"
                        "      if (vis) shown++;"
                        "    });"
                        # 1つも表示されなければサイレント失敗を防ぐため例外にする
                        "    if (shown === 0) {"
                        "      throw new Error('slide: page-' + n + ' に一致する要素が見つかりません');"
                        "    }"
                        "  }"
                        "  if (typeof window.renderFrame !== 'function') {"
                        "    window.renderFrame = function(state) {};"
                        "  }"
                        "}", slide_page)
                page.wait_for_function("typeof globalThis.renderFrame === 'function'", timeout=5000)
                for i in range(N):
                    t = i / fps
                    u = 1.0 if N <= 1 else i / (N - 1)
                    state = {
                        "frame": i, "t": t, "u": u,
                        "fps": fps, "duration": dur,
                        "width": w, "height": h,
                        "data": self._web_data, "seed": 0,
                    }
                    page.evaluate("state => globalThis.renderFrame(state)", state)
                    page.screenshot(
                        path=os.path.join(frames_dir, f"frame_{i:05d}.png"),
                        omit_background=True)
            finally:
                # 失敗時もブラウザプロセスを残さない
                browser.close()

    def grid(self, cols, rows, *, gap=0):
        """このObjectを cols×rows のグリッドに複製配置する Transform を追加。

        出力サイズは (cols*iw + gap*(cols-1)) × (rows*ih + gap*(rows-1))。
        背景パターン生成向け。静止画（-loop 1）を tile フィルタで並べる。
        """
        if self.media_type not in ("image",):
            raise TypeError("grid() は画像素材にのみ使用できます")
        if cols < 1 or rows < 1:
            raise ValueError("grid: cols/rows は1以上が必要です")
        self.transforms.append(
            Transform("grid", cols=int(cols), rows=int(rows), gap=int(gap)))
        return self

    def split(self):
        """(VideoView or None, AudioView or None) を返す"""
        v = VideoView(self) if self.has_video else None
        a = AudioView(self) if self.has_audio else None
        return v, a

    def __repr__(self):
        return f"Object({self.source}, transforms={self.transforms}, effects={self.effects}, audio_effects={self.audio_effects})"


class VideoView:
    """映像ビュー（split()で生成、参照専用）"""
    def __init__(self, clip):
        self._clip = clip

    def __le__(self, rhs):
        """映像系のみ受け入れ"""
        if isinstance(rhs, (Transform, TransformChain, Effect, EffectChain)):
            self._clip.__le__(rhs)
            return self
        raise TypeError(f"VideoView <= には映像系のみ: {type(rhs)}")

    def time(self, *args, **kwargs):
        raise TypeError("VideoView.time() は禁止です。clip.time() を使ってください。")

    def until(self, *args, **kwargs):
        raise TypeError("VideoView.until() は禁止です。clip.until() を使ってください。")


class AudioView:
    """音声ビュー（split()で生成、参照専用）"""
    def __init__(self, clip):
        self._clip = clip

    def __le__(self, rhs):
        """音声系のみ受け入れ"""
        if isinstance(rhs, (AudioEffect, AudioEffectChain, _DisabledAudioEffect)):
            self._clip.__le__(rhs)
            return self
        raise TypeError(f"AudioView <= には音声系のみ: {type(rhs)}")

    def time(self, *args, **kwargs):
        raise TypeError("AudioView.time() は禁止です。clip.time() を使ってください。")

    def until(self, *args, **kwargs):
        raise TypeError("AudioView.until() は禁止です。clip.until() を使ってください。")


def tile(obj, cols, rows, gap=0):
    """obj を cols×rows のグリッドに複製配置（Object.grid の関数版）。obj を返す。"""
    if not isinstance(obj, Object):
        raise TypeError("tile: 第1引数は Object が必要です")
    return obj.grid(cols, rows, gap=gap)


class Group:
    """複数Objectをまとめて同一Transform/Effectを一括適用するプロキシ。

    使用例:
        group(a, b, c) <= move(x=0.5, y=0.5)   # 各Objectへ委譲
        group(a, b).time(3)                     # time/until も委譲
    各適用は個々のObjectの __le__ / time / until へ転送する。
    """
    def __init__(self, *objects):
        flat = []
        for o in objects:
            if isinstance(o, Group):
                flat.extend(o.objects)
            elif isinstance(o, Object):
                flat.append(o)
            else:
                raise TypeError(f"group: Object のみ渡せます: {type(o)}")
        if not flat:
            raise ValueError("group: 最低1つのObjectが必要です")
        self.objects = flat

    def __le__(self, rhs):
        for o in self.objects:
            o.__le__(rhs)
        return self

    def time(self, duration=None, *, name=None):
        """各メンバーを time() で「順次配置」する（メンバーが順番に並ぶ）。

        注意: time() は各メンバーを直列に配置するため、グループ全体の尺は
        メンバー数 N 倍（N*duration）になる。全メンバーを同一開始時刻に
        「同時に重ねて」配置したい場合は stack() または show() を使うこと。
        """
        # name は先頭Objectにのみ付与（アンカー重複を避ける）
        for i, o in enumerate(self.objects):
            o.time(duration, name=name if i == 0 else None)
        return self

    def until(self, name, offset=0.0):
        for o in self.objects:
            o.until(name, offset=offset)
        return self

    def show(self, duration, *, priority=None):
        for o in self.objects:
            o.show(duration, priority=priority)
        return self

    def stack(self, duration, *, priority=None):
        """全メンバーを同一開始時刻に重ねて配置し、タイムラインを duration だけ進める。

        time() が各メンバーを順次配置（グループ尺 N 倍）するのに対し、stack() は
        全メンバーを同時表示する。各メンバーは show() で配置（advance しない）し、
        タイムライン全体は末尾に一度だけ pause を挟んで duration 進める。
        """
        for o in self.objects:
            o.show(duration, priority=priority)
        # メンバーは advance しないため、タイムラインを一度だけ duration 進める
        if self.objects and Project._current is not None:
            pause.time(duration)
        return self


def group(*objects):
    """複数ObjectをまとめるGroupプロキシを返す（group(a,b,c) <= move(...)）。"""
    return Group(*objects)


# --- 遅延解決の相互参照（関数本体からのみ使用: 循環importを避けるため末尾で束縛）---
from scriptvedit.cache import _build_unified_ops, _file_fingerprint, _op_prefix_fingerprint, _web_cache_path
from scriptvedit.expr import clip, min
from scriptvedit.ffmpeg import _decoder_input_args, _run_ffmpeg_to_cache
from scriptvedit.filters.video import _build_effect_filters, _build_transform_filters, _build_video_pre_filters, _get_base_dimensions
from scriptvedit.media import _source_signature
from scriptvedit.project import Project
from scriptvedit.state import _ARTIFACT_DIR, _CACHE_DIR, _ENGINE_VER, _GEN_COUNTER, _GEN_COUNTER_LOCK, _TIME_LIVE_EFFECTS, _detect_media_type, _suggest_hint
from scriptvedit.timeline import pause
