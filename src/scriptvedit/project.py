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


class Project:
    _current = None
    # レイヤー実行中のProjectスタック（from_projectでの親特定用。
    # レイヤー内で sub = Project() すると _current が奪われるため別管理）
    _exec_stack = []

    def __init__(self):
        self.width = 1920
        self.height = 1080
        self.fps = 30
        self.duration = None
        self._configured_duration = None
        self.background_color = "black"
        self.objects = []
        self._layers = []  # [(start_idx, end_idx, priority)]
        self._anchors = {}  # anchor name → time
        self._anchor_defined_in = {}  # anchor name → filename（診断用）
        self._layer_specs = []  # [{"filename": str, "priority": int, "cache": str}]
        self._mode = "render"  # "plan" or "render"
        self._current_layer_file = None  # 現在実行中のレイヤーファイル
        self._probe_cache = {}  # (path, size, mtime_ns) → {"duration": float, ...}
        self._layer_sources = {}  # layer filename → [参照ソースパス]（キャッシュ鮮度検証用）
        self._layer_audio_sources = {}  # layer filename → [音声ソース]（再生時の脱落警告用）
        self._layer_unknown_audio_sources = {}  # ffprobe失敗で音声有無が不明な動画
        self._extra_layer_deps = {}  # layer filename → [追加依存パス]（morph_toターゲット等）
        self._layer_meta_cache = {}  # anchors.jsonパス → パース済みメタ（二重読み防止）
        self._loudnorm_target = None  # normalize_audio() 設定時のLUFS目標
        self._markers = []  # [(time, label)] チャプターマーカー
        self._param_overrides = None  # p.param() 用の遅延パース済み上書き値
        self._render_window = None  # 部分レンダの (start, end)
        self.encoder = "libx264"    # 映像エンコーダ（configure(encoder=...)で変更）
        self._encoder_cv = "libx264"  # 解決済み -c:v の値（フォールバック反映後）
        self._encoder_args = list(_ENCODER_MAP["libx264"]["args"])       # []
        self._encoder_draft_args = list(_ENCODER_MAP["libx264"]["draft"])
        self._parallel = None       # キャッシュ並列生成のワーカ数（None=自動）
        self._draft = False         # ドラフトレンダ中フラグ
        self._render_quality = "final"
        self._thumbnail_at = None   # thumbnail()実行中のみ非None
        Project._current = self

    def configure(self, **kwargs):
        unknown = set(kwargs.keys()) - _CONFIGURE_KEYS
        if unknown:
            hint = _suggest_hint(sorted(unknown)[0], _CONFIGURE_KEYS)
            raise ValueError(
                f"不明な設定キー: {', '.join(sorted(unknown))}。"
                f"使用可能: {', '.join(sorted(_CONFIGURE_KEYS))}{hint}"
            )
        if "background_color" in kwargs:
            kwargs["background_color"] = _validate_ffmpeg_color(
                "configure", kwargs["background_color"])
        # width/height: 正の整数（0や負はFFmpegの s=0x720 等で失敗するため構築時に弾く）
        for key in ("width", "height"):
            if key in kwargs:
                v = kwargs[key]
                if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
                    raise ValueError(
                        f"configure: {key} は正の整数で指定してください: {v!r}")
        # fps: 正の有限数（NaN/Infinityはフィルタ式やタイムベースを壊す）
        if "fps" in kwargs:
            v = kwargs["fps"]
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or not _math.isfinite(v) or v <= 0):
                raise ValueError(
                    f"configure: fps は正の有限数で指定してください: {v!r}")
        # duration: None（自動）または正の有限数
        if "duration" in kwargs and kwargs["duration"] is not None:
            v = kwargs["duration"]
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or not _math.isfinite(v) or v <= 0):
                raise ValueError(
                    f"configure: duration は正の有限数で指定してください: {v!r}")
        # preset: width/height/fps をまとめて設定（個別指定で上書き可能なので先に適用）
        if "preset" in kwargs:
            name = kwargs.pop("preset")
            if name not in _PRESETS:
                hint = _suggest_hint(str(name), _PRESETS.keys())
                raise ValueError(
                    f"不明なプリセット: {name}。"
                    f"使用可能: {', '.join(sorted(_PRESETS))}{hint}")
            pw, ph, pfps = _PRESETS[name]
            self.width, self.height, self.fps = pw, ph, pfps
        # encoder: 利用可能性を検出し、不可なら libx264 にフォールバック
        if "encoder" in kwargs:
            self._set_encoder(kwargs.pop("encoder"))
        # parallel: キャッシュ並列生成のワーカ数
        if "parallel" in kwargs:
            pval = kwargs.pop("parallel")
            if pval is not None:
                pval = int(pval)
                if pval < 1:
                    raise ValueError(f"parallel は1以上が必要です: {pval}")
            self._parallel = pval
        for key, value in kwargs.items():
            setattr(self, key, value)
        if "duration" in kwargs:
            self._configured_duration = kwargs["duration"]

    def _set_encoder(self, encoder):
        """エンコーダを設定。ffmpegで利用不可なら libx264 へフォールバック（警告）。"""
        if encoder not in _ENCODER_MAP:
            hint = _suggest_hint(str(encoder), _ENCODER_MAP.keys())
            raise ValueError(
                f"不明なエンコーダ: {encoder}。"
                f"使用可能: {', '.join(sorted(_ENCODER_MAP))}{hint}")
        info = _ENCODER_MAP[encoder]
        cv = info["cv"]
        available = _ffmpeg_available_encoders()
        # available が空（検出失敗）の場合は指定を尊重（検出不能≠利用不可）
        if available and cv not in available and encoder != "libx264":
            warnings.warn(
                f"エンコーダ '{encoder}' ({cv}) はこのffmpegで利用できません。"
                f"libx264 にフォールバックします。")
            encoder = "libx264"
            info = _ENCODER_MAP["libx264"]
            cv = info["cv"]
        self.encoder = encoder
        self._encoder_cv = cv
        self._encoder_args = list(info["args"])
        self._encoder_draft_args = list(info["draft"])

    def normalize_audio(self, target=-14):
        """最終音声にloudnorm(EBU R128)を適用しラウドネスを正規化する。
        target: 目標ラウドネス(LUFS)。既定 -14（配信向け）。"""
        _require_number("normalize_audio", "target", target, -70, 0)
        self._loudnorm_target = target

    # --- テンプレート変数 ---

    def _parse_param_sources(self):
        """CLI(--param name=value)と環境変数(SCRIPTVEDIT_PARAM_<name>)を収集"""
        overrides = {}
        argv = sys.argv[1:]
        i = 0
        while i < len(argv):
            tok = argv[i]
            if tok == "--param" and i + 1 < len(argv):
                kv = argv[i + 1]
                i += 2
            elif tok.startswith("--param="):
                kv = tok[len("--param="):]
                i += 1
            else:
                i += 1
                continue
            if "=" in kv:
                k, v = kv.split("=", 1)
                overrides[k] = v
        # 環境変数は CLI を上書きしない（CLI 優先）
        for key, val in os.environ.items():
            if key.startswith("SCRIPTVEDIT_PARAM_"):
                name = key[len("SCRIPTVEDIT_PARAM_"):]
                overrides.setdefault(name, val)
        return overrides

    def param(self, name, default=None):
        """CLI/環境変数から差し替え可能なテンプレート変数を返す。

        `--param name=値` または環境変数 SCRIPTVEDIT_PARAM_<name> で上書きできる。
        default の型（int/float/bool）に合わせて文字列値を変換する。バッチ生成用。
        """
        if self._param_overrides is None:
            self._param_overrides = self._parse_param_sources()
        if name in self._param_overrides:
            raw = self._param_overrides[name]
        else:
            # 大文字小文字を無視して再検索（Windowsの環境変数は大文字化されるため）
            raw = next((v for k, v in self._param_overrides.items()
                        if k.lower() == name.lower()), None)
            if raw is None:
                return default
        if isinstance(default, bool):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(default, int):
            try:
                return int(raw)
            except ValueError:
                return default
        if isinstance(default, float):
            try:
                return float(raw)
            except ValueError:
                return default
        return raw

    # --- チャプターマーカー ---

    def marker(self, time, label):
        """タイムライン上のマーカーを記録（mp4チャプター/YouTube目次用）"""
        _require_number("marker", "time", time, 0)
        self._markers.append((float(time), str(label)))
        return self

    def _sorted_markers(self):
        """重複除去 + 時刻昇順のマーカー列を返す"""
        seen = set()
        uniq = []
        for t, label in self._markers:
            key = (t, label)
            if key in seen:
                continue
            seen.add(key)
            uniq.append((t, label))
        uniq.sort(key=lambda m: m[0])
        return uniq

    @staticmethod
    def _fmt_timestamp(sec):
        """秒 → H:MM:SS または M:SS（YouTube目次形式）"""
        sec = int(sec)
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def export_chapters(self, path):
        """YouTube用のチャプター目次テキスト（0:00 ラベル形式）を出力する"""
        markers = self._sorted_markers()
        lines = []
        # YouTube仕様上、先頭は 0:00 が必要。無ければ補う
        if not markers or markers[0][0] > 0.001:
            lines.append("0:00 イントロ")
        for t, label in markers:
            lines.append(f"{self._fmt_timestamp(t)} {label}")
        parent_dir = os.path.dirname(path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        tmp_path = _unique_tmp_path(path)
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            os.replace(tmp_path, path)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return path

    def export_metadata(self, path=None, *, title=None, description=None, tags=None):
        """YouTube投稿用メタデータ（チャプター+タイトル+説明+タグ）を1ファイルに出力する。

        title省略時は self.param("title") があればそれを使う（無ければNone）。
        path省略時は "metadata.json"（カレントディレクトリ）に書き出す。
        拡張子で出力形式を切替: .json ならJSON（構造化データ）、
        .txt ならYouTube概要欄にそのまま貼れるプレーンテキスト
        （タイトル→説明→チャプター目次→#タグ の順）。

        戻り値: 書き出したパス。
        """
        if title is None:
            title = self.param("title", None)
        markers = self._sorted_markers()
        chapter_lines = []
        if not markers or markers[0][0] > 0.001:
            chapter_lines.append("0:00 イントロ")
        for t, label in markers:
            chapter_lines.append(f"{self._fmt_timestamp(t)} {label}")
        # json の chapters も chapter_lines と同一ソースから生成する
        # （先頭0:00章の欠落を防ぐ）
        chapters = [{"time": t, "label": label} for t, label in markers]
        if not markers or markers[0][0] > 0.001:
            chapters.insert(0, {"time": 0.0, "label": "イントロ"})
        if isinstance(tags, str):
            tag_list = [tags] if tags else []
        else:
            tag_list = [str(t) for t in tags] if tags else []

        if path is None:
            path = "metadata.json"
        ext = os.path.splitext(path)[1].lower()
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp_path = _unique_tmp_path(path)
        try:
            if ext == ".txt":
                lines = []
                if title:
                    lines.append(title)
                    lines.append("")
                if description:
                    lines.append(description)
                    lines.append("")
                if chapter_lines:
                    lines.extend(chapter_lines)
                    lines.append("")
                if tag_list:
                    lines.append(" ".join(f"#{t}" for t in tag_list))
                content = "\n".join(lines).rstrip("\n") + "\n"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(content)
            else:
                data = {
                    "title": title,
                    "description": description,
                    "tags": tag_list,
                    "chapters": chapters,
                    "chapters_text": "\n".join(chapter_lines),
                }
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return path

    def _chapters_metadata_path(self):
        """FFMETADATAチャプターファイルのキャッシュパス（内容由来の鍵）"""
        total = self.duration if self.duration is not None else 0
        sig = "||".join(f"{t}:{label}" for t, label in self._sorted_markers())
        sig += f"||dur={total}||ev={_ENGINE_VER}"
        key = hashlib.sha256(sig.encode()).hexdigest()[:16]
        return os.path.join(_ARTIFACT_DIR, "chapters", f"{key}.txt")

    def _write_chapters_metadata(self, path):
        """FFMETADATA1形式のチャプターファイルを書き出す（絶対時刻）。

        部分レンダ(render(start,end))では出力側 -ss/-t により FFmpeg が
        チャプター時刻を自動でシフト/クランプするため（実測: ffmpeg 8.0）、
        ここでは常に絶対時刻で書き出す。手動で window 減算すると二重シフトになり、
        窓開始時にアクティブなチャプターも失われるため行わない。"""
        markers = self._sorted_markers()
        total = self.duration if self.duration is not None else (
            markers[-1][0] + 1 if markers else 1)
        lines = [";FFMETADATA1"]
        for i, (t, label) in enumerate(markers):
            start_ms = int(t * 1000)
            end_ms = int((markers[i + 1][0] if i + 1 < len(markers) else total) * 1000)
            if end_ms <= start_ms:
                end_ms = start_ms + 1
            safe = label.replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\r", " ").replace("\n", " ")
            lines.append("[CHAPTER]")
            lines.append("TIMEBASE=1/1000")
            lines.append(f"START={start_ms}")
            lines.append(f"END={end_ms}")
            lines.append(f"title={safe}")
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    # --- シーン ---

    def scene(self, name, duration):
        """シーンのコンテキストマネージャを返す（with p.scene("intro", 5): ...）。

        with 内で定義したObjectはシーン相対の時刻になり、シーンは時間軸上に
        順次配置される（既存の time anchor / pause 機構を土台に、シーン末尾を
        duration までパディングする）。
        """
        return Scene(self, name, duration)

    # --- デバッグ ---

    def explain(self, obj):
        """objに最終適用されるフィルタチェーンと u 正規化の分母(dur)を表示する。

        「dur がどこ由来か」を明示し、u=(t-start)/dur の分母の出所を一目で
        分かるようにする（デバッグ用）。表示文字列を返す。
        """
        if not isinstance(obj, Object):
            raise TypeError("explain: 対象は Object が必要です")
        start = getattr(obj, "start_time", 0)
        # dur の出所を判定
        if obj.duration:
            dur = obj.duration
            dur_src = "obj.duration（time()で明示指定）"
        elif getattr(obj, "_resolved_length", None):
            dur = obj._resolved_length
            dur_src = "obj._resolved_length（ベイク時に確定）"
        else:
            try:
                dur = self._resolve_obj_duration(obj)
                dur_src = "length()/フォールバック（time()未指定）"
            except Exception:
                dur = None
                dur_src = "未解決"
        lines = []
        lines.append(f"=== explain: {obj.source} ===")
        lines.append(f"  media_type : {obj.media_type}")
        lines.append(f"  start_time : {start}")
        lines.append(f"  duration   : {obj.duration}")
        lines.append(f"  u 正規化分母 dur = {dur}  ← {dur_src}")
        lines.append(f"  u = clip((t-{start})/{dur}, 0, 1)")
        # transform / effect フィルタ
        try:
            tfs = _build_transform_filters(obj)
        except Exception as e:
            tfs = [f"<transform構築エラー: {e}>"]
        lines.append("  Transforms:")
        if obj.transforms:
            for t in obj.transforms:
                lines.append(f"    - {t.name}: {t.params}")
        else:
            lines.append("    (なし)")
        lines.append("  Effects:")
        if obj.effects:
            for e in obj.effects:
                pd = {}
                for k, v in e.params.items():
                    pd[k] = (v.to_ffmpeg("u")[:40] + "…") if isinstance(v, Expr) else v
                lines.append(f"    - {e.name}: {pd}")
        else:
            lines.append("    (なし)")
        lines.append("  映像フィルタチェーン:")
        try:
            base_dims = _get_base_dimensions(obj)
            eff_filters, pad_size = _build_effect_filters(
                obj, start, dur or 5, base_dims=base_dims)
            chain = _optimize_filter_chain(list(tfs) + list(eff_filters))
            for f in chain:
                lines.append(f"    {f}")
            x_expr, y_expr = _build_move_exprs(obj, start, dur or 5, pad_size=pad_size)
            lines.append(f"  overlay位置: x={x_expr}")
            lines.append(f"               y={y_expr}")
        except Exception as e:
            lines.append(f"    <フィルタ構築エラー: {e}>")
        out = "\n".join(lines)
        print(out)
        return out

    def _reset_runtime_state(self):
        """render()用の実行時状態をリセット"""
        self.duration = self._configured_duration
        self.objects = []
        self._layers = []
        self._anchors = {}
        self._anchor_defined_in = {}
        # probe失敗(None)エントリのみ破棄（renderをまたいだ再試行を許す）
        self._probe_cache = {k: v for k, v in self._probe_cache.items()
                             if v is not None}
        self._layer_meta_cache = {}
        self._layer_audio_sources = {}
        self._layer_unknown_audio_sources = {}

    def _probe_media(self, path):
        """ffprobeでメディア情報を取得（キャッシュあり）"""
        # メモ化キーに stat 署名（サイズ+mtime）を含める。パスのみをキーにすると
        # 同一パスへ素材を差し替えたとき旧情報を返し続ける（issue #13 P2-9）。
        # プロセス内メモ化のみでディスクへは永続化しない（CLAUDE.md の
        # ffp.json 撤廃と同じ理由で、stat ベースの永続キャッシュは禁止）。
        try:
            st = os.stat(path)
            cache_key = (path, st.st_size, st.st_mtime_ns)
        except OSError:
            cache_key = (path, None, None)
        if cache_key in self._probe_cache:
            return self._probe_cache[cache_key]
        if _is_pending_cache_path(path):
            # dry_run中の未生成キャッシュ予定パス。probeせず警告なしでNoneを返す
            # （キャッシュはしない: 実レンダで生成された後は通常probeに進む）
            return None
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-show_format", path],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                # ffprobe失敗（ファイル欠損等）。空JSONを成功扱いしない
                raise ValueError(f"ffprobe exit code {result.returncode}")
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            duration_str = data.get("format", {}).get("duration")
            duration = float(duration_str) if duration_str else None
            # 音声ストリームのサンプルレート（aloop の size 算出に使用）
            sample_rate = None
            for s in streams:
                if s.get("codec_type") == "audio" and s.get("sample_rate"):
                    try:
                        sample_rate = int(s["sample_rate"])
                    except (ValueError, TypeError):
                        sample_rate = None
                    break
            # ストリーム個別の尺（映像/音声でコンテナ尺と食い違う素材向け）。
            # video_sequence 等が A/V ドリフトを避けるために使う。
            def _stream_dur(s):
                sd = s.get("duration")
                try:
                    return float(sd) if sd else None
                except (ValueError, TypeError):
                    return None
            video_duration = None
            audio_duration = None
            for s in streams:
                ct = s.get("codec_type")
                if ct == "video" and video_duration is None:
                    video_duration = _stream_dur(s)
                elif ct == "audio" and audio_duration is None:
                    audio_duration = _stream_dur(s)
            info = {"has_audio": has_audio, "duration": duration,
                    "sample_rate": sample_rate,
                    "video_duration": video_duration,
                    "audio_duration": audio_duration}
            self._probe_cache[cache_key] = info
            return info
        except FileNotFoundError:
            # 失敗もrender内ではキャッシュ（_reset_runtime_stateでNoneのみ破棄され、
            # renderをまたげば再試行される）
            warnings.warn(
                f"ffprobeが見つかりません ({path})。PATHを確認してください。")
            self._probe_cache[cache_key] = None
            return None
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError,
                json.JSONDecodeError, ValueError) as e:
            warnings.warn(f"メディア情報の取得に失敗 ({path}): {e}")
            self._probe_cache[cache_key] = None
            return None

    def layer(self, filename, priority=0, cache="off"):
        """レイヤーファイルを登録（実行はrender時に遅延）

        filename は cwd 相対でも、呼び出し元スクリプト/実行中レイヤーからの
        相対でも解決される（どのディレクトリから実行しても動く）。
        """
        if cache not in ("off", "auto", "use", "make"):
            raise ValueError(f"cache引数は 'off','auto','use','make' のいずれか: {cache!r}")
        filename = resolve_layer_path(filename, self)
        self._layer_specs.append({"filename": filename, "priority": priority, "cache": cache})

    def _exec_layer(self, filename, priority):
        """レイヤーファイルを実行してobjectsに登録"""
        start_idx = len(self.objects)
        self._current_layer_file = filename
        # exec中にmorph_to等が積む追加依存をリセット（plan/renderの再実行で重複させない）
        self._extra_layer_deps[filename] = []
        Project._current = self
        Project._exec_stack.append(self)
        try:
            # レイヤーファイルと同階層の plugins/ を自動読込（cwd と異なる場合の保険）
            _autoload_plugins(os.path.dirname(os.path.abspath(filename)))
            with open(filename, encoding="utf-8") as f:
                code = f.read()
            namespace = {}
            exec(compile(code, filename, "exec"), namespace)
        finally:
            Project._exec_stack.pop()
            # レイヤー内で sub = Project() された場合に _current を奪還する
            Project._current = self
        end_idx = len(self.objects)
        self._layers.append((start_idx, end_idx, priority))
        for obj in self.objects[start_idx:end_idx]:
            override = getattr(obj, '_priority_override', None)
            obj.priority = override if override is not None else priority
        self._fill_auto_durations(start_idx, end_idx)
        # レイヤーが参照する素材ソースを記録（checkpoint等で差し替わる前の値）
        sources = []
        for o in self.objects[start_idx:end_idx]:
            if not isinstance(o, Object):
                continue
            # compute()済みは導出キャッシュパスではなく元素材を記録
            sources.extend(getattr(o, '_origin_sources', None) or [o.source])
            # web Objectの依存素材（deps=）も鮮度検証の対象にする
            if getattr(o, '_web_deps', None):
                sources.extend(o._web_deps)
        # morph_toターゲット等、objectsから除外された依存を併合
        sources.extend(self._extra_layer_deps.get(filename, []))
        self._layer_sources[filename] = sources
        cache_mode = next(
            (spec["cache"] for spec in self._layer_specs
             if spec["filename"] == filename), "off")
        audio_sources = []
        unknown_audio_sources = []
        if cache_mode != "off":
            for o in self.objects[start_idx:end_idx]:
                if not isinstance(o, Object) or o._audio_deleted:
                    continue
                source_text = str(os.fspath(o.source)).replace("\\", "/")
                has_audio = o._has_audio
                if has_audio is None:
                    info = self._probe_media(o.source)
                    if info is None:
                        if o.media_type == "video":
                            unknown_audio_sources.append(source_text)
                        continue
                    has_audio = bool(info.get("has_audio"))
                if has_audio:
                    audio_sources.append(source_text)
        self._layer_audio_sources[filename] = audio_sources
        self._layer_unknown_audio_sources[filename] = unknown_audio_sources
        self._current_layer_file = None

    def _fill_auto_durations(self, start_idx, end_idx):
        """duration_auto=Trueのオブジェクトにlength()でdurationを確定"""
        for obj in self.objects[start_idx:end_idx]:
            if (isinstance(obj, Object)
                    and obj._duration_auto
                    and obj.duration is None
                    and obj._until_anchor is None):
                obj.duration = obj.length()

    def _calc_total_duration(self):
        """各レイヤーの最大終了時刻を返す（show含む）"""
        max_dur = 0
        for start_idx, end_idx, _ in self._layers:
            for item in self.objects[start_idx:end_idx]:
                if isinstance(item, _AnchorMarker):
                    continue
                # _ScenePad は resolve 後に start_time/duration を持つため通常計上
                if item.duration is not None:
                    end = item.start_time + item.duration
                    max_dur = max(max_dur, end)
        return max_dur if max_dur > 0 else 5

    def _resolve_anchors(self, check_unresolved=True):
        """反復走査でアンカーとuntilを解決"""
        max_iter = len(self._layers) + 2
        for iteration in range(max_iter):
            changed = False
            for start_idx, end_idx, _ in self._layers:
                current_time = 0
                for item in self.objects[start_idx:end_idx]:
                    if isinstance(item, _AnchorMarker):
                        old_val = self._anchors.get(item.name)
                        self._anchors[item.name] = current_time
                        if old_val != current_time:
                            changed = True
                        continue
                    if isinstance(item, _ScenePad):
                        # シーン開始+目標尺まで current_time を進める（遅延パディング）。
                        # pad量を duration として保持し、末尾シーンのパディングも
                        # 総尺(_calc_total_duration)に反映されるようにする。
                        scene_start = self._anchors.get(
                            f"scene:{item.scene_name}", 0)
                        target_time = scene_start + item.target_duration
                        item.start_time = current_time
                        pad_amt = float(max(0.0, target_time - current_time))
                        if item.duration != pad_amt:
                            item.duration = pad_amt
                            changed = True
                        current_time += pad_amt
                        continue
                    item.start_time = current_time
                    # name anchor: X.start 登録
                    anchor_name = getattr(item, '_anchor_name', None)
                    if anchor_name:
                        start_key = f"{anchor_name}.start"
                        old_val = self._anchors.get(start_key)
                        self._anchors[start_key] = current_time
                        if old_val != current_time:
                            changed = True
                    # until解決（offset対応）
                    until_name = getattr(item, '_until_anchor', None)
                    if until_name:
                        anchor_time = self._anchors.get(until_name)
                        if anchor_time is not None:
                            offset = getattr(item, '_until_offset', 0.0)
                            target_time = anchor_time + offset
                            new_dur = max(0, target_time - current_time)
                            if item.duration != new_dur:
                                item.duration = new_dur
                                changed = True
                    # 時刻進行（advance=False なら進めない）
                    advance = getattr(item, '_advance', True)
                    if item.duration is not None:
                        if advance:
                            current_time += item.duration
                        # name anchor: X.end 登録
                        if anchor_name:
                            end_key = f"{anchor_name}.end"
                            end_time = item.start_time + item.duration
                            old_val = self._anchors.get(end_key)
                            self._anchors[end_key] = end_time
                            if old_val != end_time:
                                changed = True
            if not changed:
                break
        if check_unresolved:
            for item in self.objects:
                until_name = getattr(item, '_until_anchor', None)
                if until_name and until_name not in self._anchors:
                    raise RuntimeError(f"未定義のアンカー: '{until_name}'")

    def render(self, output_path, *, dry_run=False, timeout=None,
               start=None, end=None, draft=False, alpha=False):
        # _ACTIVE_QUALITY を try/finally で復元（draft レンダ後に "draft" が
        # 残留して別レンダの鍵に混入するのを防ぐ。dry_run早期returnや例外時も復元）
        _prev_active_quality = _ACTIVE_QUALITY[0]
        try:
            return self._render_impl(
                output_path, dry_run=dry_run, timeout=timeout,
                start=start, end=end, draft=draft, alpha=alpha)
        finally:
            _ACTIVE_QUALITY[0] = _prev_active_quality

    def _render_impl(self, output_path, *, dry_run=False, timeout=None,
                     start=None, end=None, draft=False, alpha=False):
        output_path = os.fsdecode(output_path)
        self._reset_runtime_state()
        self._dry_run = dry_run
        self._draft = bool(draft)
        self._alpha = bool(alpha)
        self._render_quality = "draft" if draft else "final"
        # draft時はチェックポイント/morph鍵を本番と分離
        _ACTIVE_QUALITY[0] = "draft" if draft else ""
        _GEN_COUNTER[0] = 0
        _t0 = _time.perf_counter()
        self._pending_compute_cmds = {}
        # 部分レンダの時間窓を検証・保持（式のt基準は保ちつつ窓外を出力しない）
        if start is not None or end is not None:
            s = 0.0 if start is None else float(start)
            e = end if end is None else float(end)
            if s < 0:
                raise ValueError(f"render: start は0以上が必要です: {start}")
            if e is not None and e <= s:
                raise ValueError(f"render: end({end}) は start({start}) より後が必要です")
            self._render_window = (s, e)
        else:
            self._render_window = None
        # Plan pass: アンカー解決（cache模擬、objects破棄）
        self._plan_resolve()
        # 総尺はplan pass（常にライブ実行）の結果から確定する。
        # レイヤーキャッシュ鍵が総尺を含むため、キャッシュ判定・検証より
        # 前に確定していなければならない（issue #13 P1-4）
        if self.duration is None:
            self.duration = self._calc_total_duration()
        # cache="use" の事前検証（鍵に総尺を含むため総尺確定後に行う）
        self._validate_cache_specs()
        # Render pass: 本実行（anchors確定済み）
        self.objects = []
        self._layers = []
        self._mode = "render"
        for spec in self._layer_specs:
            if self._should_use_cache(spec):
                self._load_cached_layer(spec)
            else:
                self._exec_layer(spec["filename"], spec["priority"])
        self._resolve_anchors()

        if dry_run:
            web_cmds = self._collect_web_cmds()
            # web Objectのsourceを予定webmパスに仮差し替え
            # （layer cache / checkpoint収集より前。-i xxx.html の混入を防ぐ）
            for obj in self.objects:
                if isinstance(obj, Object) and obj.media_type == "web":
                    obj.source = _web_cache_path(obj, self)
                    obj.media_type = "video"
            cache_cmds = self._collect_cache_cmds()
            checkpoint_cmds = self._collect_checkpoint_cmds()
            cmd = self._build_ffmpeg_cmd(output_path)
            all_extra = {}
            if cache_cmds:
                all_extra.update(cache_cmds)
            if web_cmds:
                all_extra.update(web_cmds)
            if checkpoint_cmds:
                all_extra.update(checkpoint_cmds)
            if self._pending_compute_cmds:
                all_extra.update(self._pending_compute_cmds)
            if all_extra:
                return {"main": cmd, "cache": all_extra}
            return cmd  # 後方互換: cache不要ならlistのまま

        self._ensure_formula_objects()
        self._ensure_web_objects()
        # 統計: このレンダが参照する中間生成物のうち既存(ヒット)/未生成(ミス)を数える
        # 注意: _collect_* はdry_run用でobj.source等を予測パスへ破壊的に差し替えるため、
        #       状態をスナップショットして復元してから実生成へ進む
        planned = set()
        _snap = [(o, o.source, o.media_type, list(o.transforms), list(o.effects),
                  getattr(o, "_resolved_length", None))
                 for o in self.objects if isinstance(o, Object)]
        try:
            planned |= set(self._collect_checkpoint_cmds().keys())
            planned |= set(self._collect_cache_cmds().keys())
            planned |= set(self._collect_web_cmds().keys())
            planned |= set(self._pending_compute_cmds.keys())
        except Exception:
            planned = set()
        finally:
            for o, src, mt, tr, ef, rl in _snap:
                o.source, o.media_type = src, mt
                o.transforms, o.effects = tr, ef
                o._resolved_length = rl
        cache_hits = sum(1 for p in planned if os.path.exists(p))
        cache_misses = len(planned) - cache_hits
        self._ensure_checkpoints()
        cmd = self._build_ffmpeg_cmd(output_path)
        print(f"実行コマンド:")
        print(f"  ffmpeg {' '.join(cmd[1:])}")
        print()
        fmt = self._resolve_output_format(output_path)
        if fmt["kind"] == "pngseq":
            # 連番は単一パスへ原子的に確定できないため従来どおり直接出力する。
            _run_ffmpeg(cmd, timeout=timeout)
        else:
            # 最終単一出力もキャッシュと同じく、同拡張子の一時パスへ書いてから
            # 原子的に確定する。timeout/Ctrl+C/ffmpeg失敗では一時ファイルだけを
            # 消すため、壊れた新規出力も、既存の正常な完成品の消失も防げる。
            final_path = fmt["output_path"]
            tmp_path = _unique_tmp_path(final_path)
            run_cmd = list(cmd)
            if not run_cmd or os.fsdecode(run_cmd[-1]) != final_path:
                raise ValueError(
                    "render: ffmpegコマンドの最終出力パスを一時パスへ置換できません")
            run_cmd[-1] = tmp_path
            try:
                _run_ffmpeg(run_cmd, timeout=timeout)
                os.replace(tmp_path, final_path)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        self._generate_pending_caches()
        elapsed = _time.perf_counter() - _t0
        generated = _GEN_COUNTER[0]
        print(f"\n完了: {output_path}")
        mode = "ドラフト" if draft else "本番"
        print(f"[統計] {mode} / 総時間 {elapsed:.2f}s / "
              f"キャッシュ ヒット{cache_hits} ミス{cache_misses} / "
              f"生成した中間ファイル {generated}件")

    def thumbnail(self, at, out, *, timeout=600):
        """指定時刻 at(秒) のフレームを1枚のPNGとして書き出す。

        render() と同じプラン解決・チェックポイント生成を通し、
        フィルタグラフの t 基準を保ったまま -ss + -frames:v 1 で抜き出す。
        """
        at = float(at)
        if at < 0:
            raise ValueError(f"thumbnail: at は0以上が必要です: {at}")
        self._prepare_thumbnail_graph()
        self._extract_frame(at, out, timeout=timeout)
        print(f"完了: {out}")
        return out

    def _prepare_thumbnail_graph(self):
        """thumbnail/storyboard 共通: プラン解決+レイヤーexec+checkpoint確保を
        一度だけ行い、-ss 単フレーム抽出可能な確定済みグラフを構築する。"""
        self._reset_runtime_state()
        self._dry_run = False
        self._draft = False
        self._alpha = False
        self._render_quality = "final"
        _ACTIVE_QUALITY[0] = ""
        self._pending_compute_cmds = {}
        self._render_window = None
        self._plan_resolve()
        # render()と同じく、キャッシュ鍵が総尺を含むため先に総尺を確定する
        if self.duration is None:
            self.duration = self._calc_total_duration()
        self._validate_cache_specs()
        self.objects = []
        self._layers = []
        self._mode = "render"
        for spec in self._layer_specs:
            if self._should_use_cache(spec):
                self._load_cached_layer(spec)
            else:
                self._exec_layer(spec["filename"], spec["priority"])
        self._resolve_anchors()
        # render() と同じく数式PNG/Webクリップを先に実体化する
        # （formula の PNG が無いと ffmpeg が "No such file or directory" で落ちる）
        self._ensure_formula_objects()
        self._ensure_web_objects()
        self._ensure_checkpoints()

    def _extract_frame(self, at, out, *, timeout=600):
        """準備済みグラフに対し -ss + -frames:v 1 で1フレームだけ抽出する。"""
        self._thumbnail_at = float(at)
        try:
            cmd = self._build_ffmpeg_cmd(out)
            print(f"サムネイル抽出 @{at}s: {out}")
            print(f"  ffmpeg {' '.join(cmd[1:])}")
            _run_ffmpeg(cmd, timeout=timeout)
        finally:
            self._thumbnail_at = None
        return out

    def storyboard(self, out_path, *, cols=4, interval=None):
        """タイムラインの絵コンテ（サムネイル格子画像）を1枚のPNGとして生成する。

        interval秒ごと（省略時は 総尺/12）に thumbnail() と同じ抽出経路
        （plan解決+checkpoint確保+ffmpeg単フレーム抽出）でサムネイルを取り出し、
        PILでcols列のグリッドに結合する（各コマ左上に時刻ラベルを焼き込む）。
        事前にrender()した最終動画は不要（このメソッド単体で完結する実装方式。
        thumbnail()を都度呼ぶためコマ数ぶんffmpegが実行される）。

        戻り値: 書き出したパス(out_path)。
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as e:
            raise ImportError(
                "storyboard() には Pillow が必要です。"
                "`pip install Pillow` を実行してください。") from e
        if cols < 1:
            raise ValueError(f"storyboard: cols は1以上が必要です: {cols}")
        if interval is not None:
            _require_number("storyboard", "interval", interval, 0.001, None)

        tmp_dir = os.path.join(_ARTIFACT_DIR, "storyboard", "_frames")
        os.makedirs(tmp_dir, exist_ok=True)
        try:
            # プラン解決・レイヤーexec・checkpoint確保は一度だけ実施し、
            # 各コマは確定済みグラフに対する -ss 単フレーム抽出だけをループする
            # （thumbnail() を毎コマ呼ぶと全パイプラインがコマ数ぶん再実行される）。
            self._prepare_thumbnail_graph()
            total = self.duration
            if not total or total <= 0:
                raise RuntimeError("storyboard: タイムラインの総尺を確定できませんでした")
            step = interval if interval is not None else max(total / 12.0, 0.01)

            times = [0.0]
            t = step
            while t < total - 1e-6:
                times.append(t)
                t += step

            frame_paths = []
            for i, tsec in enumerate(times):
                fp = os.path.join(tmp_dir, f"frame_{i:03d}.png")
                self._extract_frame(min(tsec, max(0.0, total - 0.001)), fp)
                frame_paths.append((tsec, fp))

            thumbs = [Image.open(fp).convert("RGB") for _, fp in frame_paths]
            tw, th = thumbs[0].size
            n = len(thumbs)
            rows = (n + cols - 1) // cols
            gap = 4
            grid_w = cols * tw + (cols - 1) * gap
            grid_h = rows * th + (rows - 1) * gap
            canvas = Image.new("RGB", (grid_w, grid_h), (20, 20, 20))
            draw = ImageDraw.Draw(canvas)
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 18)
            except Exception:
                font = ImageFont.load_default()
            for i, ((tsec, _fp), img) in enumerate(zip(frame_paths, thumbs)):
                r, c = divmod(i, cols)
                x = c * (tw + gap)
                y = r * (th + gap)
                canvas.paste(img, (x, y))
                label = self._fmt_timestamp(tsec)
                draw.rectangle([x, y, x + 68, y + 20], fill=(0, 0, 0))
                draw.text((x + 4, y + 3), label, fill=(255, 255, 0), font=font)

            d = os.path.dirname(out_path)
            if d:
                os.makedirs(d, exist_ok=True)
            tmp_out = out_path + ".tmp.png"
            canvas.save(tmp_out)
            os.replace(tmp_out, out_path)
        finally:
            _shutil.rmtree(tmp_dir, ignore_errors=True)
        return out_path

    def inspect(self, out_html=None, *, title=None):
        """scriptvedit.viz による検査ビュー。

        out_html 指定時は HTML ガントチャートを書き出しそのパスを返す。
        省略時はプレーンテキストのレポート文字列を返す（遅延 import）。
        """
        try:
            # 属性参照ではなくモジュール直接 import（プラグインの名前空間注入の影響を受けない）
            from importlib import import_module as _import_module
            _svi = _import_module("scriptvedit.viz")
        except ImportError as e:
            raise ImportError(
                "inspect() には scriptvedit.viz が必要です。"
                "scriptvedit.py と同じディレクトリに配置してください。") from e
        if out_html is not None:
            return _svi.render_timeline(self, out_html, title=title)
        return _svi.report_text(self)

    def _plan_resolve(self):
        """Plan pass: 固定点反復でアンカーを解決"""
        converged = False
        max_iterations = len(self._layer_specs) + 2
        for iteration in range(max_iterations):
            old_anchors = dict(self._anchors)
            self.objects = []
            self._layers = []
            self._mode = "plan"
            for spec in self._layer_specs:
                # Plan passではレイヤーキャッシュを使わず常に実行
                self._exec_layer(spec["filename"], spec["priority"])
            self._resolve_anchors(check_unresolved=False)
            if self._anchors == old_anchors and iteration > 0:
                converged = True
                break
        # 収束しなかった場合
        if not converged and self._anchors:
            raise RuntimeError(
                f"アンカー解決が{max_iterations}回の反復で収束しませんでした。"
                f"循環参照の可能性があります。\n"
                f"定義済みアンカー: {dict(self._anchors)}"
            )
        # 未解決のuntilチェック（診断付き）
        unresolved = []
        for item in self.objects:
            until_name = getattr(item, '_until_anchor', None)
            if until_name and until_name not in self._anchors:
                unresolved.append((until_name, item))
        if unresolved:
            names = ", ".join(f"'{n}'" for n in sorted(set(n for n, _ in unresolved)))
            defined = ", ".join(f"'{n}'" for n in sorted(self._anchors.keys())) or "(なし)"
            details = []
            for name, item in unresolved:
                offset = getattr(item, '_until_offset', 0.0)
                offset_str = f", offset={offset}" if offset != 0.0 else ""
                if isinstance(item, Pause):
                    details.append(f"  pause.until('{name}'{offset_str})")
                elif isinstance(item, Object):
                    details.append(f"  Object('{item.source}').until('{name}'{offset_str})")
                else:
                    details.append(f"  {type(item).__name__}.until('{name}'{offset_str})")
            raise RuntimeError(
                f"未定義のアンカーが参照されています: {names}\n"
                f"定義済みアンカー: {defined}\n"
                f"参照元:\n" + "\n".join(details)
            )

    def _validate_cache_specs(self):
        """cache='use' のファイル存在チェック"""
        for spec in self._layer_specs:
            if spec["cache"] == "use":
                webm_path, json_path = _layer_cache_paths(spec["filename"], self)
                if not os.path.exists(webm_path):
                    raise FileNotFoundError(
                        f"キャッシュファイルが見つかりません: {webm_path}\n"
                        f"レイヤー '{spec['filename']}' に cache='use' が指定されていますが、"
                        f"先に cache='make' でキャッシュを生成してください。"
                    )

    def _layer_cache_is_fresh(self, spec):
        """anchors.jsonに記録された素材FFPと現在のファイル状態を比較して鮮度を判定

        旧形式（sourcesキーなし）のメタは後方互換のため常に新鮮とみなす。
        """
        _, json_path = _layer_cache_paths(spec["filename"], self)
        if not os.path.exists(json_path):
            return True  # メタなし（後方互換）
        try:
            with open(json_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            return True
        # パース済みメタを保持し、_load_cached_layerでの再読込をスキップする
        self._layer_meta_cache[json_path] = meta
        sources = meta.get("sources")
        if not sources:
            return True  # 旧形式（後方互換）
        for path, ffp in sources.items():
            try:
                cur = _file_fingerprint(path)
            except OSError:
                return False  # 素材が消えた
            if cur != ffp:
                return False  # 素材の内容が変わった（旧形式のlist値もここで不一致→再生成）
        return True

    def _should_use_cache(self, spec):
        """キャッシュ利用判定"""
        cache = spec["cache"]
        if cache == "use":
            if not self._layer_cache_is_fresh(spec):
                warnings.warn(
                    f"レイヤーキャッシュの素材が更新されています: {spec['filename']}。"
                    f"cache='make' で再生成してください（cache='use' 指定のため続行します）。")
            return True
        if cache == "auto":
            webm_path, _ = _layer_cache_paths(spec["filename"], self)
            # 素材更新済みの古いキャッシュは使わず再実行
            return os.path.exists(webm_path) and self._layer_cache_is_fresh(spec)
        return False  # off, make

    def _load_cached_layer(self, spec):
        """キャッシュからObject生成 + anchors.jsonマージ"""
        webm_path, json_path = _layer_cache_paths(spec["filename"], self)
        start_idx = len(self.objects)
        # キャッシュwebmをObjectとして生成
        cached_obj = Object.__new__(Object)
        cached_obj.source = webm_path
        cached_obj.transforms = []
        cached_obj.effects = []
        cached_obj.audio_effects = []
        cached_obj.duration = None
        cached_obj.start_time = 0
        cached_obj.priority = spec["priority"]
        cached_obj.media_type = "video"
        cached_obj._until_anchor = None
        cached_obj._video_deleted = False
        cached_obj._audio_deleted = False
        cached_obj._has_video = True
        cached_obj._has_audio = False
        cached_obj._web_source = None
        cached_obj._web_size = None
        cached_obj._web_fps = None
        cached_obj._web_data = {}
        cached_obj._web_name = None
        cached_obj._web_debug_frames = False
        # anchors.jsonからduration/anchorsを読み込み
        # （_layer_cache_is_freshでパース済みならそのメタを流用し二重読みを避ける）
        cache_meta = self._layer_meta_cache.get(json_path)
        if cache_meta is None and os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as f:
                cache_meta = json.load(f)
        if cache_meta is not None:
            cached_obj.duration = cache_meta.get("duration")
            for name, time_val in cache_meta.get("anchors", {}).items():
                self._anchors[name] = time_val
                self._anchor_defined_in[name] = spec["filename"]
        filename = spec["filename"]
        has_runtime_audio_info = filename in self._layer_audio_sources
        audio_sources = self._layer_audio_sources.get(filename, [])
        unknown_audio_sources = self._layer_unknown_audio_sources.get(filename, [])
        if not has_runtime_audio_info and cache_meta is not None:
            audio_sources = cache_meta.get("audio_sources", [])
            unknown_audio_sources = cache_meta.get("unknown_audio_sources", [])
        legacy_audio_sources = []
        if (not has_runtime_audio_info and not audio_sources
                and not unknown_audio_sources and cache_meta is not None
                and "audio_sources" not in cache_meta):
            # issue #8以前のメタには音声情報がない。旧キャッシュをcache='use'で
            # 再生しても無言脱落を見逃さないよう、記録済み素材をprobeして補う。
            using_legacy_audio_info = True
            for source in cache_meta.get("sources", {}):
                media_type = _detect_media_type(source)
                if media_type == "audio":
                    legacy_audio_sources.append(source)
                    continue
                info = self._probe_media(source)
                if info and info.get("has_audio"):
                    legacy_audio_sources.append(source)
                elif info is None and media_type == "video":
                    unknown_audio_sources.append(source)
            audio_sources = legacy_audio_sources
        else:
            using_legacy_audio_info = False
        if audio_sources or unknown_audio_sources:
            if using_legacy_audio_info:
                details = list(audio_sources) + list(unknown_audio_sources)
                warnings.warn(
                    f"旧形式のレイヤーキャッシュを再生するため音声が脱落する"
                    f"可能性があります (cache='{spec['cache']}', "
                    f"{spec['filename']}): {', '.join(details)}。"
                    f"cache='make' で再生成するか、音声素材を cache='off' の"
                    f"別レイヤーへ分離してください。")
            elif unknown_audio_sources:
                details = list(audio_sources) + list(unknown_audio_sources)
                warnings.warn(
                    f"レイヤーキャッシュを再生しますが、ffprobeで音声の有無を"
                    f"確認できない動画があるため音声が脱落する可能性があります "
                    f"(cache='{spec['cache']}', {spec['filename']}): "
                    f"{', '.join(details)}。"
                    f"音声素材を cache='off' の別レイヤーへ分離してください。")
            else:
                warnings.warn(
                    f"レイヤーキャッシュを再生するため音声が脱落します "
                    f"(cache='{spec['cache']}', {spec['filename']}): "
                    f"{', '.join(audio_sources)}。"
                    f"音声素材を cache='off' の別レイヤーへ分離してください。")
        self.objects.append(cached_obj)
        end_idx = len(self.objects)
        self._layers.append((start_idx, end_idx, spec["priority"]))

    def _get_layer_data(self, spec_index):
        """指定レイヤーのオブジェクト群とアンカー群を取得"""
        spec = self._layer_specs[spec_index]
        # _layersのインデックスはspec_indexに対応
        if spec_index >= len(self._layers):
            return [], {}
        start_idx, end_idx, _ = self._layers[spec_index]
        objects = self.objects[start_idx:end_idx]
        anchors = {}
        current_time = 0
        for item in objects:
            if isinstance(item, _AnchorMarker):
                anchors[item.name] = current_time
                continue
            if isinstance(item, _ScenePad):
                # シーン開始+目標尺まで進める（遅延パディング、キャッシュ用アンカー整合）
                scene_start = anchors.get(f"scene:{item.scene_name}", 0)
                target_time = scene_start + item.target_duration
                if current_time < target_time:
                    current_time = target_time
                continue
            # 正規リゾルバ(_resolve_anchors)と同じ非進行判定を適用する。
            # show()/show_until() は _advance=False で時刻を進めないため、
            # ここで無条件に加算するとキャッシュ用メタのアンカーだけずれて
            # cache有無で後続レイヤーの開始時刻が変わる（issue #13 P2-10）
            if item.duration is not None and getattr(item, "_advance", True):
                current_time += item.duration
        return objects, anchors

    def _collect_cache_cmds(self):
        """dry_run用のキャッシュ生成コマンド辞書構築"""
        cache_cmds = {}
        for i, spec in enumerate(self._layer_specs):
            # "make" は常に生成（"auto" はキャッシュ有無に関わらず生成コマンドを持たない）
            if spec["cache"] == "make":
                webm_path, _ = _layer_cache_paths(spec["filename"], self)
                cmd = self._build_layer_cache_cmd(i, webm_path)
                cache_cmds[webm_path] = cmd
        return cache_cmds

    def _build_checkpoint_image_cmd(self, source, transforms, cache_path, quality="final"):
        """画像チェックポイント: Transform適用→透過PNG"""
        # 一時Object経由で _build_transform_filters を再利用
        temp = Object.__new__(Object)
        temp.source = source
        temp.transforms = list(transforms)
        temp.effects = []
        filters = _build_transform_filters(temp)
        cmd = ["ffmpeg", "-y", "-i", source]
        if filters:
            cmd.extend(["-vf", ",".join(filters)])
        cmd.extend(["-frames:v", "1", "-pix_fmt", "rgba", cache_path])
        return cmd

    def _build_checkpoint_video_cmd(self, source, media_type, transforms, effects,
                                     cache_path, dur, fps, quality="final"):
        """動画チェックポイント: Transform+Effect適用→透明VP9"""
        cmd = ["ffmpeg", "-y"]
        cmd.extend(_decoder_input_args(source, media_type, fps))

        # フィルタ構築: 一時Object経由で既存ビルダーを再利用
        temp = Object.__new__(Object)
        temp.source = source
        temp.transforms = list(transforms)
        temp.effects = list(effects)
        temp.media_type = media_type

        base_dims = _get_base_dimensions(temp)
        filters = _build_transform_filters(temp)
        pre_filters = _build_video_pre_filters(temp)
        filters = pre_filters + filters
        eff_filters, _ = _build_effect_filters(temp, 0, dur, base_dims=base_dims)
        filters.extend(eff_filters)
        filters = _optimize_filter_chain(filters)

        if filters:
            cmd.extend(["-vf", ",".join(filters)])

        cmd.extend([
            "-c:v", "ffv1", "-level", "3",
            "-pix_fmt", "yuva444p",
            "-t", str(dur), cache_path,
        ])
        return cmd

    def _build_morph_webm_cmd(self, frame_pattern, cache_path, duration, fps, quality="final"):
        """PNG連番 → alpha映像 のffmpegコマンドを構築"""
        return ["ffmpeg", "-y", "-framerate", str(fps),
                "-i", frame_pattern,
                "-c:v", "ffv1", "-level", "3",
                "-pix_fmt", "yuva444p",
                "-t", str(duration), cache_path]

    @staticmethod
    def _require_morph_duration(bakeable_ops, dur, source):
        """morph_toを含むObjectのduration未設定を明示エラーにする

        画像 + duration未設定のまま進むと int(fps * None) の TypeError で
        原因が分かりにくいため、ここで日本語エラーを投げる。
        """
        has_term = any(t == "effect" and op.name in _TERMINAL_FRAME_EFFECTS
                       for t, op in bakeable_ops)
        if has_term and dur is None:
            raise ValueError(
                f"morph_to/explode_to/assemble_from を含むObject ('{source}') には"
                f"表示時間の指定が必要です。obj.time(秒数) で duration を設定してください。")

    def _checkpoint_bake_duration(self, obj, original_source):
        """チェックポイントのベイク尺を決定する。

        speed/reverse/freeze_frame 等の live 時間系Effectが残るObjectは、
        表示尺(duration)ではなくソース基準の実長(trimのみ反映)でベイクする。
        表示尺でベイクすると、後段の時間系Effect適用でソース素材が
        不足/過剰になる（例: speed(2)で表示尺5s → 元素材10sが必要）ため。
        """
        is_video = _detect_media_type(original_source) in ("video",)
        has_time_live = any(
            getattr(e, "name", None) in _TIME_LIVE_EFFECTS for e in obj.effects)
        if is_video and has_time_live:
            info = self._probe_media(original_source)
            base = info.get("duration") if info else None
            if base is None:
                base = getattr(obj, "_resolved_length", None) or obj.duration
            if base:
                cur = base
                for e in obj.effects:
                    if e.name == "trim" and e.params.get("duration") is not None:
                        cur = _builtins.min(cur, e.params["duration"])
                return cur
        dur = obj.duration
        # video + duration未指定 → obj.length() で補完
        if dur is None and is_video:
            dur = obj.length()
        return dur

    def _process_checkpoints(self, obj):
        """1つのObjectのチェックポイント処理（実レンダ）"""
        ops = _build_unified_ops(obj)
        bakeable_ops, live_ops = _split_ops(ops)
        # bakeable ops があるか確認
        if not bakeable_ops:
            return
        # 全opがpolicy="off"ならスキップ
        if all(getattr(op, 'policy', 'auto') == "off" for _, op in bakeable_ops):
            return

        _validate_morph_position(bakeable_ops)

        save_points = _compute_save_points(bakeable_ops)
        if not save_points:
            return

        original_source = obj.source
        original_media_type = obj.media_type
        dur = self._checkpoint_bake_duration(obj, original_source)
        fps = self.fps
        self._require_morph_duration(bakeable_ops, dur, original_source)

        # 復元点チェック（bakeable_opsベース）
        resume_idx, resume_path = self._find_resume_point(original_source, bakeable_ops, dur, fps, save_points)
        if resume_idx is not None:
            current_source = resume_path
            current_media_type = _detect_media_type(resume_path)
            remaining_ops = bakeable_ops[resume_idx + 1:]
        else:
            current_source = original_source
            current_media_type = original_media_type
            remaining_ops = list(bakeable_ops)

        # 前方実行: 保存点でのみチェックポイント生成
        executed = bakeable_ops[:len(bakeable_ops) - len(remaining_ops)]
        pos = 0
        while pos < len(remaining_ops):
            global_idx = len(executed) + pos
            if global_idx in save_points:
                typ, op = remaining_ops[pos]
                segment_ops = executed + remaining_ops[:pos + 1]
                has_effects = any(t == "effect" for t, _ in segment_ops)
                is_video = _detect_media_type(original_source) in ("video",)
                cp_dur = dur if (has_effects or is_video) else None
                cp_fps = fps if cp_dur is not None else None
                quality = getattr(op, 'quality', 'final')

                # morph_to 分岐
                if typ == "effect" and op.name == "morph_to" and hasattr(op, '_morph_target'):
                    # morph直前の未ベイクopsを先に中間チェックポイントへベイク
                    # （破棄するとmorph前のresize等が黙って消えるため）
                    if pos > 0:
                        pre_ops = remaining_ops[:pos]
                        pre_segment = executed + pre_ops
                        pre_has_effects = any(t == "effect" for t, _ in pre_segment)
                        pre_dur = dur if (pre_has_effects or is_video) else None
                        pre_fps = fps if pre_dur is not None else None
                        pre_quality = getattr(pre_ops[-1][1], 'quality', 'final')
                        pre_path = _checkpoint_cache_path(
                            original_source, pre_segment, pre_dur, pre_fps, pre_quality)
                        if not os.path.exists(pre_path):
                            pre_transforms = [o for t, o in pre_ops if t == "transform"]
                            pre_effects = [o for t, o in pre_ops if t == "effect"]
                            os.makedirs(os.path.dirname(pre_path), exist_ok=True)
                            if pre_dur is None:
                                pre_cmd = self._build_checkpoint_image_cmd(
                                    current_source, pre_transforms, pre_path, pre_quality)
                            else:
                                pre_cmd = self._build_checkpoint_video_cmd(
                                    current_source, current_media_type,
                                    pre_transforms, pre_effects,
                                    pre_path, pre_dur, fps, pre_quality)
                            print(f"チェックポイント保存 (morph前処理): {pre_path}")
                            _run_ffmpeg_to_cache(pre_cmd, pre_path, timeout=600)
                        current_source = pre_path
                        current_media_type = _detect_media_type(pre_path)
                    # morph（PIL）は画像のみ対応: 直前ソースが動画（前ベイクの.mkv等）
                    # なら最終フレームをRGBA PNGに抽出してmorphの入力にする
                    if _detect_media_type(current_source) == "video":
                        frame_path = _morph_input_frame_path(current_source)
                        if not os.path.exists(frame_path):
                            frame_cmd = _build_morph_frame_extract_cmd(
                                current_source, frame_path)
                            os.makedirs(os.path.dirname(frame_path), exist_ok=True)
                            print(f"モーフ入力フレーム抽出: {frame_path}")
                            _run_ffmpeg_to_cache(frame_cmd, frame_path, timeout=600)
                        current_source = frame_path
                        current_media_type = "image"
                    morph_path = _morph_cache_path(current_source, op, dur, fps, quality)
                    policy = getattr(op, 'policy', 'auto')
                    need_render = (policy == "force") or not os.path.exists(morph_path)
                    if need_render:
                        import tempfile
                        from scriptvedit.morph import generate_rgba_frames
                        with tempfile.TemporaryDirectory() as tmpdir:
                            n_frames = int(fps * dur)
                            # blend Exprを数値関数に変換
                            blend_expr = op.params.get("blend")
                            if blend_expr is not None and isinstance(blend_expr, Expr):
                                blend_fn = lambda t, _e=blend_expr: _e.eval_at(t)
                            else:
                                blend_fn = None
                            morph_kw = {k: v for k, v in op.params.items() if k != "blend"}
                            generate_rgba_frames(
                                current_source, op._morph_target.source,
                                tmpdir, n_frames, blend_fn=blend_fn, **morph_kw)
                            frame_pattern = os.path.join(tmpdir, "frame_%05d.png")
                            os.makedirs(os.path.dirname(morph_path), exist_ok=True)
                            cmd = self._build_morph_webm_cmd(
                                frame_pattern, morph_path, dur, fps, quality)
                            print(f"モーフキャッシュ保存: {morph_path}")
                            _run_ffmpeg_to_cache(cmd, morph_path, timeout=600)
                    current_source = morph_path
                    current_media_type = "video"
                elif typ == "effect" and op.name in ("explode_to", "assemble_from"):
                    from scriptvedit.morph import (generate_explode_frames,
                                       generate_assemble_frames)
                    if op.name == "explode_to":
                        # explode: 直前の未ベイクopsを先にベイク（morphと同じ経路）
                        if pos > 0:
                            pre_ops = remaining_ops[:pos]
                            pre_segment = executed + pre_ops
                            pre_has_effects = any(t == "effect" for t, _ in pre_segment)
                            pre_dur = dur if (pre_has_effects or is_video) else None
                            pre_fps = fps if pre_dur is not None else None
                            pre_quality = getattr(pre_ops[-1][1], 'quality', 'final')
                            pre_path = _checkpoint_cache_path(
                                original_source, pre_segment, pre_dur, pre_fps, pre_quality)
                            if not os.path.exists(pre_path):
                                pre_transforms = [o for t, o in pre_ops if t == "transform"]
                                pre_effects = [o for t, o in pre_ops if t == "effect"]
                                os.makedirs(os.path.dirname(pre_path), exist_ok=True)
                                if pre_dur is None:
                                    pre_cmd = self._build_checkpoint_image_cmd(
                                        current_source, pre_transforms, pre_path, pre_quality)
                                else:
                                    pre_cmd = self._build_checkpoint_video_cmd(
                                        current_source, current_media_type,
                                        pre_transforms, pre_effects,
                                        pre_path, pre_dur, fps, pre_quality)
                                print(f"チェックポイント保存 (explode前処理): {pre_path}")
                                _run_ffmpeg_to_cache(pre_cmd, pre_path, timeout=600)
                            current_source = pre_path
                            current_media_type = _detect_media_type(pre_path)
                        img_path = current_source
                        gen = generate_explode_frames
                    else:  # assemble_from: 集合元画像を入力にする
                        img_path = op._assemble_source.source
                        gen = generate_assemble_frames
                    # 粒子生成（PIL）は画像のみ: 動画ソースは最終フレームを抽出
                    if _detect_media_type(img_path) == "video":
                        frame_path = _morph_input_frame_path(img_path)
                        if not os.path.exists(frame_path):
                            frame_cmd = _build_morph_frame_extract_cmd(img_path, frame_path)
                            os.makedirs(os.path.dirname(frame_path), exist_ok=True)
                            print(f"粒子入力フレーム抽出: {frame_path}")
                            _run_ffmpeg_to_cache(frame_cmd, frame_path, timeout=600)
                        img_path = frame_path
                    part_path = _particle_cache_path(img_path, op, dur, fps, quality)
                    policy = getattr(op, 'policy', 'auto')
                    need_render = (policy == "force") or not os.path.exists(part_path)
                    if need_render:
                        import tempfile
                        with tempfile.TemporaryDirectory() as tmpdir:
                            n_frames = int(fps * dur)
                            blend_expr = op.params.get("blend")
                            if blend_expr is not None and isinstance(blend_expr, Expr):
                                blend_fn = lambda t, _e=blend_expr: _e.eval_at(t)
                            else:
                                blend_fn = None
                            part_kw = {k: v for k, v in op.params.items() if k != "blend"}
                            gen(img_path, tmpdir, n_frames, blend_fn=blend_fn, **part_kw)
                            frame_pattern = os.path.join(tmpdir, "frame_%05d.png")
                            os.makedirs(os.path.dirname(part_path), exist_ok=True)
                            cmd = self._build_morph_webm_cmd(
                                frame_pattern, part_path, dur, fps, quality)
                            print(f"粒子キャッシュ保存: {part_path}")
                            _run_ffmpeg_to_cache(cmd, part_path, timeout=600)
                    current_source = part_path
                    current_media_type = "video"
                else:
                    cache_path = _checkpoint_cache_path(
                        original_source, segment_ops, cp_dur, cp_fps, quality)

                    policy = getattr(op, 'policy', 'auto')
                    need_render = (policy == "force") or not os.path.exists(cache_path)
                    if need_render:
                        local_ops = remaining_ops[:pos + 1]
                        local_transforms = [op for t, op in local_ops if t == "transform"]
                        local_effects = [op for t, op in local_ops if t == "effect"]

                        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                        if cp_dur is None:
                            cmd = self._build_checkpoint_image_cmd(
                                current_source, local_transforms, cache_path, quality)
                        else:
                            cmd = self._build_checkpoint_video_cmd(
                                current_source, current_media_type,
                                local_transforms, local_effects,
                                cache_path, cp_dur, fps, quality)
                        print(f"チェックポイント保存: {cache_path}")
                        _run_ffmpeg_to_cache(cmd, cache_path, timeout=600)
                    current_source = cache_path
                    current_media_type = _detect_media_type(cache_path)

                executed = executed + remaining_ops[:pos + 1]
                remaining_ops = remaining_ops[pos + 1:]
                pos = 0
                continue
            pos += 1

        # Objectを更新: source差し替え、残余bakeable ops + live opsを再設定
        # 差し替え前に解決した実長を保持（差し替え後のprobe依存を排除し、
        # dry_runと実レンダで式を一致させる）。
        # live 時間系Effect（speed/freeze_frame）が残る場合は表示尺に換算する
        if dur:
            obj._resolved_length = _apply_time_effects_to_duration(
                dur, [op for t, op in live_ops if t == "effect"])
        obj.source = current_source
        obj.media_type = current_media_type
        obj.transforms = [op for t, op in remaining_ops if t == "transform"]
        obj.effects = ([op for t, op in remaining_ops if t == "effect"]
                       + [op for t, op in live_ops if t == "effect"])

    def _find_resume_point(self, original_source, ops, duration, fps, save_points):
        """force地点より左のauto保存点のみresume候補"""
        # 最左force位置
        first_force = None
        for i, (typ, op) in enumerate(ops):
            if getattr(op, 'policy', 'auto') == "force" and _is_bakeable(typ, op):
                first_force = i
                break
        boundary = (first_force - 1) if first_force is not None else len(ops) - 1

        # boundary以下のauto保存点を右から探索
        candidates = sorted([i for i in save_points
                            if i <= boundary and getattr(ops[i][1], 'policy', 'auto') == "auto"],
                           reverse=True)

        is_video = _detect_media_type(original_source) in ("video",)
        for idx in candidates:
            segment_ops = ops[:idx + 1]
            # 保存側と同じくセグメント（保存点までのprefix）単位でhas_effectsを計算
            # （全ops基準だとキャッシュキーが食い違い、永久にキャッシュミスする）
            has_effects = any(t == "effect" for t, _ in segment_ops)
            cp_dur = duration if (has_effects or is_video) else None
            cp_fps = fps if cp_dur is not None else None
            quality = getattr(ops[idx][1], 'quality', 'final')
            path = _checkpoint_cache_path(original_source, segment_ops, cp_dur, cp_fps, quality)
            if os.path.exists(path):
                return idx, path
        return None, None

    def _ensure_checkpoints(self):
        """bakeable opsを持つ全Objectのチェックポイント処理"""
        for obj in self.objects:
            if not isinstance(obj, Object):
                continue
            if obj.media_type == "text":
                continue  # テキスト系は実体ファイルを持たずベイク対象外
            bakeable_ops, _ = _split_ops(_build_unified_ops(obj))
            if not bakeable_ops:
                continue
            # 全opがpolicy="off"ならスキップ
            if all(getattr(op, 'policy', 'auto') == "off" for _, op in bakeable_ops):
                continue
            self._process_checkpoints(obj)

    def _collect_checkpoint_cmds(self):
        """dry_run用: 全チェックポイントコマンドを収集"""
        cmds = {}
        for obj in self.objects:
            if not isinstance(obj, Object):
                continue
            if obj.media_type == "text":
                continue  # テキスト系は実体ファイルを持たずベイク対象外
            ops = _build_unified_ops(obj)
            bakeable_ops, live_ops = _split_ops(ops)
            if not bakeable_ops:
                continue
            if all(getattr(op, 'policy', 'auto') == "off" for _, op in bakeable_ops):
                continue

            _validate_morph_position(bakeable_ops)

            save_points = _compute_save_points(bakeable_ops)
            if not save_points:
                continue

            original_source = obj.source
            dur = self._checkpoint_bake_duration(obj, original_source)
            fps = self.fps
            self._require_morph_duration(bakeable_ops, dur, original_source)
            current_source = original_source
            current_media_type = obj.media_type

            sorted_sps = sorted(save_points)
            for sp_idx in sorted_sps:
                segment_ops = bakeable_ops[:sp_idx + 1]
                has_effects = any(t == "effect" for t, _ in segment_ops)
                is_video = _detect_media_type(original_source) in ("video",)
                cp_dur = dur if (has_effects or is_video) else None
                cp_fps = fps if cp_dur is not None else None
                sp_typ, sp_op = bakeable_ops[sp_idx]
                quality = getattr(sp_op, 'quality', 'final')

                # current_sourceの解決（前の保存点からの更新）
                prev_sps = [j for j in sorted_sps if j < sp_idx]
                if prev_sps:
                    prev_sp_idx = prev_sps[-1]
                    prev_sp_typ, prev_sp_op = bakeable_ops[prev_sp_idx]
                    # 前の保存点がmorph_toの場合
                    if prev_sp_typ == "effect" and prev_sp_op.name == "morph_to" and hasattr(prev_sp_op, '_morph_target'):
                        current_source = _morph_cache_path(
                            current_source, prev_sp_op, dur, fps,
                            getattr(prev_sp_op, 'quality', 'final'))
                    else:
                        prev_seg = bakeable_ops[:prev_sp_idx + 1]
                        prev_has_eff = any(t == "effect" for t, _ in prev_seg)
                        prev_is_video = _detect_media_type(original_source) in ("video",)
                        current_source = _checkpoint_cache_path(
                            original_source, prev_seg,
                            dur if (prev_has_eff or prev_is_video) else None,
                            fps if (prev_has_eff or prev_is_video) else None,
                            getattr(prev_sp_op, 'quality', 'final'))
                    current_media_type = _detect_media_type(current_source)

                # morph_to 分岐
                if sp_typ == "effect" and sp_op.name == "morph_to" and hasattr(sp_op, '_morph_target'):
                    # morph直前の未ベイクopsの中間チェックポイントコマンドも収集
                    # （実レンダの_process_checkpointsと同じ経路）
                    pre_start = prev_sps[-1] + 1 if prev_sps else 0
                    pre_ops = bakeable_ops[pre_start:sp_idx]
                    if pre_ops:
                        pre_segment = bakeable_ops[:sp_idx]
                        pre_has_effects = any(t == "effect" for t, _ in pre_segment)
                        pre_dur = dur if (pre_has_effects or is_video) else None
                        pre_fps = fps if pre_dur is not None else None
                        pre_quality = getattr(pre_ops[-1][1], 'quality', 'final')
                        pre_path = _checkpoint_cache_path(
                            original_source, pre_segment, pre_dur, pre_fps, pre_quality)
                        pre_transforms = [o for t, o in pre_ops if t == "transform"]
                        pre_effects = [o for t, o in pre_ops if t == "effect"]
                        if pre_dur is None:
                            pre_cmd = self._build_checkpoint_image_cmd(
                                current_source, pre_transforms, pre_path, pre_quality)
                        else:
                            pre_cmd = self._build_checkpoint_video_cmd(
                                current_source, current_media_type,
                                pre_transforms, pre_effects,
                                pre_path, pre_dur, fps, pre_quality)
                        cmds[pre_path] = pre_cmd
                        current_source = pre_path
                        current_media_type = _detect_media_type(pre_path)
                    # 動画ソースは最終フレームPNG抽出を挟む（実レンダと同じ経路）
                    if _detect_media_type(current_source) == "video":
                        frame_path = _morph_input_frame_path(current_source)
                        cmds[frame_path] = _build_morph_frame_extract_cmd(
                            current_source, frame_path)
                        current_source = frame_path
                        current_media_type = "image"
                    morph_path = _morph_cache_path(current_source, sp_op, dur, fps, quality)
                    frame_pattern = os.path.join("__morph_frames__", "frame_%05d.png")
                    cmd = self._build_morph_webm_cmd(
                        frame_pattern, morph_path, dur, fps, quality)
                    cmds[morph_path] = cmd
                elif sp_typ == "effect" and sp_op.name in ("explode_to", "assemble_from"):
                    # 粒子Effect分岐（実レンダの_process_checkpointsと同じ経路）
                    if sp_op.name == "explode_to":
                        pre_start = prev_sps[-1] + 1 if prev_sps else 0
                        pre_ops = bakeable_ops[pre_start:sp_idx]
                        if pre_ops:
                            pre_segment = bakeable_ops[:sp_idx]
                            pre_has_effects = any(t == "effect" for t, _ in pre_segment)
                            pre_dur = dur if (pre_has_effects or is_video) else None
                            pre_fps = fps if pre_dur is not None else None
                            pre_quality = getattr(pre_ops[-1][1], 'quality', 'final')
                            pre_path = _checkpoint_cache_path(
                                original_source, pre_segment, pre_dur, pre_fps, pre_quality)
                            pre_transforms = [o for t, o in pre_ops if t == "transform"]
                            pre_effects = [o for t, o in pre_ops if t == "effect"]
                            if pre_dur is None:
                                pre_cmd = self._build_checkpoint_image_cmd(
                                    current_source, pre_transforms, pre_path, pre_quality)
                            else:
                                pre_cmd = self._build_checkpoint_video_cmd(
                                    current_source, current_media_type,
                                    pre_transforms, pre_effects,
                                    pre_path, pre_dur, fps, pre_quality)
                            cmds[pre_path] = pre_cmd
                            current_source = pre_path
                            current_media_type = _detect_media_type(pre_path)
                        img_path = current_source
                    else:  # assemble_from
                        img_path = sp_op._assemble_source.source
                    if _detect_media_type(img_path) == "video":
                        frame_path = _morph_input_frame_path(img_path)
                        cmds[frame_path] = _build_morph_frame_extract_cmd(
                            img_path, frame_path)
                        img_path = frame_path
                    part_path = _particle_cache_path(img_path, sp_op, dur, fps, quality)
                    frame_pattern = os.path.join("__particle_frames__", "frame_%05d.png")
                    cmds[part_path] = self._build_morph_webm_cmd(
                        frame_pattern, part_path, dur, fps, quality)
                else:
                    cache_path = _checkpoint_cache_path(
                        original_source, segment_ops, cp_dur, cp_fps, quality)

                    local_ops_start = 0
                    if prev_sps:
                        local_ops_start = prev_sps[-1] + 1

                    local_ops = bakeable_ops[local_ops_start:sp_idx + 1]
                    local_transforms = [op for t, op in local_ops if t == "transform"]
                    local_effects = [op for t, op in local_ops if t == "effect"]

                    if cp_dur is None:
                        cmd = self._build_checkpoint_image_cmd(
                            current_source, local_transforms, cache_path, quality)
                    else:
                        cmd = self._build_checkpoint_video_cmd(
                            current_source, current_media_type,
                            local_transforms, local_effects,
                            cache_path, cp_dur, fps, quality)
                    cmds[cache_path] = cmd

            # Object source差し替え（最後の保存点）
            last_sp = sorted_sps[-1]
            last_typ, last_op = bakeable_ops[last_sp]
            if last_typ == "effect" and last_op.name == "morph_to" and hasattr(last_op, '_morph_target'):
                last_path = _morph_cache_path(
                    current_source, last_op, dur, fps,
                    getattr(last_op, 'quality', 'final'))
            elif last_typ == "effect" and last_op.name in ("explode_to", "assemble_from"):
                if last_op.name == "assemble_from":
                    img_path = last_op._assemble_source.source
                else:
                    img_path = current_source
                if _detect_media_type(img_path) == "video":
                    img_path = _morph_input_frame_path(img_path)
                last_path = _particle_cache_path(
                    img_path, last_op, dur, fps,
                    getattr(last_op, 'quality', 'final'))
            else:
                last_seg = bakeable_ops[:last_sp + 1]
                last_has_eff = any(t == "effect" for t, _ in last_seg)
                last_is_video = _detect_media_type(original_source) in ("video",)
                last_path = _checkpoint_cache_path(
                    original_source, last_seg,
                    dur if (last_has_eff or last_is_video) else None,
                    fps if (last_has_eff or last_is_video) else None,
                    getattr(last_op, 'quality', 'final'))
            # 差し替え前に解決した実長を保持（未生成予定パスへのprobe fallback防止）。
            # live 時間系Effect（speed/freeze_frame）が残る場合は表示尺に換算する
            if dur:
                obj._resolved_length = _apply_time_effects_to_duration(
                    dur, [op for t, op in live_ops if t == "effect"])
            obj.source = last_path
            obj.media_type = _detect_media_type(last_path)
            remaining = bakeable_ops[last_sp + 1:]
            obj.transforms = [op for t, op in remaining if t == "transform"]
            obj.effects = ([op for t, op in remaining if t == "effect"]
                           + [op for t, op in live_ops if t == "effect"])

        return cmds

    def _collect_web_cmds(self):
        """dry_run用: web Objectのwebmエンコードコマンドを収集"""
        cmds = {}
        for obj in self.objects:
            if isinstance(obj, Object) and obj.media_type == "web":
                webm_path = _web_cache_path(obj, self)
                cmds[webm_path] = obj._build_web_cmd(self, webm_path)
        return cmds

    def _ensure_formula_objects(self):
        """formula()/formula_lines() の数式PNGを実レンダ直前に生成する。

        Objectのsourceは構築時点で content-addressed なキャッシュパス
        （__cache__/artifacts/formula/<hash>.png）に決まっているため、
        dry_run ではPlaywrightを起動せずコマンドを組み立てられる。
        """
        from scriptvedit.formula import _render_formula_png
        for obj in self.objects:
            spec = getattr(obj, "_formula_spec", None)
            if not isinstance(obj, Object) or spec is None:
                continue
            if os.path.exists(obj.source):
                continue
            print(f"数式レンダ: {spec['lines']}")
            _render_formula_png(spec, obj.source, getattr(obj, "_formula_fn", "formula"))
            print(f"  完了: {obj.source}")

    def _ensure_web_objects(self):
        """web ObjectのPlaywrightレンダ+ffmpegエンコード実行、sourceをwebmに差し替え"""
        for obj in self.objects:
            if not isinstance(obj, Object) or obj.media_type != "web":
                continue
            webm_path = _web_cache_path(obj, self)
            frames_dir = _web_frames_dir(obj._web_name)

            if not os.path.exists(webm_path):
                print(f"Webクリップ生成: {obj.source}")
                try:
                    obj._render_web_frames(self)
                    cmd = obj._build_web_cmd(self, webm_path)
                    os.makedirs(os.path.dirname(webm_path), exist_ok=True)
                    print(f"  ffmpeg {' '.join(cmd[1:])}")
                    _run_ffmpeg_to_cache(cmd, webm_path, timeout=600)
                    print(f"  完了: {webm_path}")
                finally:
                    # フレーム削除（失敗時も中間フレームを残さない）
                    if not obj._web_debug_frames and os.path.exists(frames_dir):
                        import shutil
                        shutil.rmtree(frames_dir, ignore_errors=True)

            obj.source = webm_path
            obj.media_type = "video"

    def _parallel_workers(self):
        """キャッシュ並列生成のワーカ数を決定（configure(parallel=N)優先、既定は控えめ）"""
        if self._parallel is not None:
            return _builtins.max(1, int(self._parallel))
        cpu = os.cpu_count() or 2
        # ffmpeg自体がマルチスレッドのため控えめに（CPU数-1、上限4）
        return _builtins.max(1, _builtins.min(cpu - 1, 4))

    def _generate_pending_caches(self):
        """レイヤーキャッシュ生成を実行（独立レイヤーは ThreadPoolExecutor で並列）"""
        pending = [i for i, spec in enumerate(self._layer_specs)
                   if spec["cache"] == "make"]
        if not pending:
            return
        workers = _builtins.min(self._parallel_workers(), len(pending))
        if workers <= 1 or len(pending) == 1:
            for i in pending:
                self._render_layer_to_cache(i)
            return
        # 各レイヤーキャッシュは独立（相互に入力参照しない）ため並列化して差し支えない
        print(f"レイヤーキャッシュを並列生成: {len(pending)}件 (workers={workers})")
        errors = []
        with _futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(self._render_layer_to_cache, i): i for i in pending}
            for fut in _futures.as_completed(futs):
                try:
                    fut.result()
                except Exception as e:  # 1件失敗しても他の結果は確定させる
                    errors.append((futs[fut], e))
        if errors:
            i, e = errors[0]
            raise RuntimeError(
                f"レイヤーキャッシュ生成に失敗しました "
                f"({self._layer_specs[i]['filename']}): {e}") from e

    def _build_layer_cache_cmd(self, spec_index, webm_path):
        """レイヤーキャッシュ用ffmpegコマンド（透明webm VP9 alpha）

        webm_path: 出力先パス。呼び出し側で計算して渡す
        （_layer_cache_pathsはFFP依存のため、二重計算するとレイヤーファイルの
        mtime変化等で構築時と実行時のパスが食い違うおそれがある）。
        """
        spec = self._layer_specs[spec_index]
        objects, anchors = self._get_layer_data(spec_index)
        # 本レンダと同じく priority ソート + 映像を持つオブジェクトのみ合成
        renderable = sorted(
            [o for o in objects if isinstance(o, Object) and o.has_video],
            key=lambda o: o.priority)
        # レイヤーキャッシュは映像のみ保存するため、既知の音声と判定不能動画を警告
        audio_sources = self._layer_audio_sources.get(spec["filename"], [])
        unknown_audio_sources = self._layer_unknown_audio_sources.get(
            spec["filename"], [])
        if audio_sources or unknown_audio_sources:
            details = list(audio_sources) + list(unknown_audio_sources)
            status = ("音声はキャッシュ再生時に脱落します" if not unknown_audio_sources
                      else "音声がキャッシュ再生時に脱落する可能性があります")
            warnings.warn(
                f"レイヤーキャッシュ ({spec['filename']}) は映像のみ保存します。"
                f"{status}: {', '.join(details)}\n"
                f"回避策: 音声を持つ素材は cache を付けない別レイヤーに分離してください"
                f"（透過VP9への音声多重化はレイヤー内amix/adelay/duck_underの"
                f"再現が必要で本ウェーブでは見送り）。")

        dur = self.duration or self._calc_total_duration()

        inputs = []
        filter_parts = []

        # 入力0: 透明キャンバス
        inputs.extend([
            "-f", "lavfi",
            "-i", f"color=c=black@0.0:s={self.width}x{self.height}:d={dur}:r={self.fps},format=rgba",
        ])

        current_base = "[0:v]"

        for i, obj in enumerate(renderable):
            input_idx = i + 1
            inputs.extend(_build_input_args(obj, self.fps))
            # 本レンダと同じ解決ロジックでu正規化の分母を統一
            # （レイヤー全体尺fallbackだとcache有無でアニメ速度が変わる）
            obj_dur = self._resolve_obj_duration(obj)
            parts, out_label = _build_video_overlay_parts(
                obj, input_idx, current_base, obj_dur)
            filter_parts.extend(parts)
            current_base = out_label

        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)

        if filter_parts:
            cmd.extend(["-filter_complex", ";".join(filter_parts)])
            cmd.extend(["-map", current_base])

        cmd.extend([
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-b:v", "0",
            "-crf", "30",
            "-auto-alt-ref", "0",
            "-t", str(dur),
            webm_path,
        ])
        return cmd

    def _render_layer_to_cache(self, spec_index):
        """レイヤーキャッシュ生成実行"""
        spec = self._layer_specs[spec_index]
        webm_path, json_path = _layer_cache_paths(spec["filename"], self)
        os.makedirs(os.path.dirname(webm_path), exist_ok=True)

        cmd = self._build_layer_cache_cmd(spec_index, webm_path)
        print(f"キャッシュ生成: {webm_path}")
        print(f"  ffmpeg {' '.join(cmd[1:])}")
        _run_ffmpeg_to_cache(cmd, webm_path, timeout=600)
        print(f"  完了: {webm_path}")

        # anchors.json書き出し（素材FFPも記録してキャッシュ鮮度検証に使う）
        objects, anchors = self._get_layer_data(spec_index)
        dur = self.duration or self._calc_total_duration()
        sources_meta = {}
        for src in self._layer_sources.get(spec["filename"], []):
            try:
                # キーは指定されたままのパス（相対のまま保つ＝メタも移植可能に）
                sources_meta[str(src).replace("\\", "/")] = _file_fingerprint(src)
            except OSError:
                pass
        cache_meta = {
            "duration": dur,
            "anchors": anchors,
            "sources": sources_meta,
            "audio_sources": self._layer_audio_sources.get(spec["filename"], []),
            "unknown_audio_sources": self._layer_unknown_audio_sources.get(
                spec["filename"], []),
        }
        # アトミック書き込み（webmと同様、中断による壊れたメタの残留を防ぐ）。
        # 一時パスは pid + 乱数でユニーク化（並列レイヤー生成での衝突防止）
        tmp_json = _unique_tmp_path(json_path)
        try:
            with open(tmp_json, "w", encoding="utf-8") as f:
                json.dump(cache_meta, f, indent=2, ensure_ascii=False)
            os.replace(tmp_json, json_path)
        finally:
            try:
                os.remove(tmp_json)  # 失敗時の残骸掃除（成功時は replace 済みで存在しない）
            except OSError:
                pass
        print(f"  アンカー保存: {json_path}")

    def _loop_trim_duration(self, obj, loop_effect):
        """loop(until=...) の実効トリム尺を返す（until優先→duration→全体尺）"""
        start = obj.start_time
        until = loop_effect.params.get("until")
        if until is not None:
            return max(0.0, until - start)
        if obj.duration is not None:
            return obj.duration
        total = self.duration or self._calc_total_duration()
        return max(0.0, total - start)

    def _build_aloop_filter(self, obj, loop_effect):
        """aloop フィルタ文字列を構築（元素材長からループ用サンプル数を決定）。
        aloopは無限ループ(loop=-1)し、後段のatrim/durationで尺を確定する。"""
        length = _probe_audio_length(obj.source)
        # 実サンプルレートを取得（高SR素材でも1周期分を確実に確保するため）。
        info = self._probe_media(obj.source)
        sr = info.get("sample_rate") if info else None
        if length and sr:
            size = int(_math.ceil(length * sr)) + sr
        elif length:
            # SR不明時は大きめ（192kHz相当）で1周期分＋余裕を確保
            size = int(_math.ceil(length * 192000)) + 192000
        else:
            size = 192000 * 60  # 取得不能時のフォールバック（約1分・192kHz相当）
        return f"aloop=loop=-1:size={size}"

    def _resolve_obj_duration(self, obj, fallback=5):
        """objのduration未設定/0のとき実長で補完（取得不能・0のときのみfallback）

        duration=0 をそのまま返すと u正規化 clip((t-start)/0,...) のゼロ除算で
        ffmpegがEINVAL失敗するため、0はfallbackに落とす。
        """
        if obj.duration:
            return obj.duration
        # checkpoint等でsourceが予定パスに差し替わる前に解決した実長を最優先
        resolved = getattr(obj, '_resolved_length', None)
        if resolved:
            return resolved
        if obj.media_type not in ("image", "text"):
            # trim/atrim/atempoを反映した加工後長（チェックポイントベイクと同一基準）
            try:
                length = obj.length()
            except Exception:
                return fallback
            if length:
                return length
        return fallback

    def _resolve_output_format(self, output_path):
        """出力パスの拡張子・draft/alpha/thumbnail設定から出力形式を決定する。

        戻り値 dict:
          kind:  "h264" | "gif" | "webp" | "pngseq" | "webm" | "thumb"
          alpha: 背景を透過にするか
          has_audio: この形式が音声トラックを持てるか
          output_path: 実際にffmpegへ渡す出力パス（連番PNGは %05d 化）
        """
        alpha = bool(getattr(self, "_alpha", False))
        if getattr(self, "_thumbnail_at", None) is not None:
            return {"kind": "thumb", "alpha": False, "has_audio": False,
                    "output_path": output_path}
        ext = os.path.splitext(output_path)[1].lower()
        if ext == ".gif":
            return {"kind": "gif", "alpha": False, "has_audio": False,
                    "output_path": output_path}
        if ext == ".webp":
            return {"kind": "webp", "alpha": alpha, "has_audio": False,
                    "output_path": output_path}
        if ext == ".png":
            # 連番PNG（out.png -> out_%05d.png）。既に%が含まれるなら尊重
            op = output_path
            if "%" not in op:
                base, _e = os.path.splitext(output_path)
                op = f"{base}_%05d.png"
            return {"kind": "pngseq", "alpha": True, "has_audio": False,
                    "output_path": op}
        if ext == ".webm":
            return {"kind": "webm", "alpha": alpha, "has_audio": True,
                    "output_path": output_path}
        return {"kind": "h264", "alpha": alpha, "has_audio": True,
                "output_path": output_path}

    def _build_ffmpeg_cmd(self, output_path):
        inputs = []
        filter_parts = []
        fmt = self._resolve_output_format(output_path)
        output_path = fmt["output_path"]

        # 背景入力（alpha出力時は透明キャンバス）
        if fmt["alpha"]:
            bg_src = (f"color=c=black@0.0:s={self.width}x{self.height}"
                      f":d={self.duration}:r={self.fps},format=rgba")
        else:
            bg_src = (f"color=c={self.background_color}:s={self.width}x{self.height}"
                      f":d={self.duration}:r={self.fps}")
        inputs.extend(["-f", "lavfi", "-i", bg_src])

        renderable = [o for o in self.objects if isinstance(o, Object)]
        sorted_objects = sorted(renderable, key=lambda o: o.priority)

        # 入力を追加（映像+音声共通）
        input_map = {}  # obj id → input_idx
        for i, obj in enumerate(sorted_objects):
            input_idx = i + 1
            input_map[id(obj)] = input_idx
            inputs.extend(_build_input_args(obj, self.fps))

        # --- 映像チェーン ---
        current_base = "[0:v]"
        video_objects = [o for o in sorted_objects if o.has_video]

        for obj in video_objects:
            input_idx = input_map[id(obj)]
            dur = self._resolve_obj_duration(obj)
            parts, out_label = _build_video_overlay_parts(
                obj, input_idx, current_base, dur)
            filter_parts.extend(parts)
            current_base = out_label

        # --- 音声チェーン ---
        # サムネイル等の映像専用出力では音声枝を構築しない。構築だけして
        # -map しないと、loudnorm 等の終端が未接続になり ffmpeg が EINVAL で落ちる。
        audio_objects = ([o for o in sorted_objects if o.has_audio]
                         if fmt["has_audio"] else [])
        audio_out = None

        if audio_objects:
            audio_labels = []
            idx_by_id = {}  # id(obj) → audio_labels内index（duck_underのother参照用）
            for ai, obj in enumerate(audio_objects):
                idx_by_id[id(obj)] = ai
                input_idx = input_map[id(obj)]
                dur = self._resolve_obj_duration(obj)
                start = obj.start_time

                a_filters = []
                # loop（aloop）: atrim/adelayより前に置き、以降のトリムで尺を確定
                loop_effect = next(
                    (e for e in obj.audio_effects if e.name == "loop"), None)
                if loop_effect is not None:
                    a_filters.append(self._build_aloop_filter(obj, loop_effect))
                # atrim/atempo前処理
                a_pre = _build_audio_pre_filters(obj)
                # auto atrim: obj.durationがあり、明示atrimがなければ自動トリム
                has_explicit_atrim = any(
                    e.name == "atrim" for e in obj.audio_effects)
                if not has_explicit_atrim and obj.duration is not None:
                    # auto atrim は atempo（speed 追従含む）の後段に置く。
                    # 先頭に前置すると atrim=(base/factor)→atempo=factor の順になり
                    # 音声尺が base/factor² まで縮む不具合になるため末尾に回す。
                    a_pre = a_pre + [f"atrim=duration={obj.duration}",
                                     "asetpts=PTS-STARTPTS"]
                # loop で until 指定かつ obj.duration 未設定なら until までトリム
                if (loop_effect is not None and not has_explicit_atrim
                        and obj.duration is None):
                    lt = self._loop_trim_duration(obj, loop_effect)
                    a_pre = [f"atrim=duration={lt}", "asetpts=PTS-STARTPTS"] + a_pre
                a_filters.extend(a_pre)
                # 音声エフェクト（again/afade）
                a_filters.extend(_build_audio_effect_filters(obj, dur))
                # adelay（タイミングシフト）: all=1 で全チャンネルに適用（2ch前提を排除）
                delay_ms = int(start * 1000)
                if delay_ms > 0:
                    a_filters.append(f"adelay={delay_ms}:all=1")

                a_label = f"[a{ai}]"
                if a_filters:
                    filter_parts.append(
                        f"[{input_idx}:a]{','.join(a_filters)}{a_label}"
                    )
                else:
                    a_label = f"[{input_idx}:a]"
                audio_labels.append(a_label)

            # duck_under（sidechaincompress）: other音声再生中に自音量を下げる。
            # otherをasplitでミックス用/サイドチェーン用に分岐して供給する。
            for ai, obj in enumerate(audio_objects):
                duck = next(
                    (e for e in obj.audio_effects if e.name == "duck_under"), None)
                if duck is None:
                    continue
                other = duck.params["other"]
                if other is obj:
                    raise ValueError("duck_under: other に自分自身は指定できません")
                if id(other) not in idx_by_id:
                    raise ValueError(
                        "duck_under: other が同じProjectの再生対象音声に含まれていません。"
                        "other 側の音声が adelete 等で除外されていないか確認してください。")
                oi = idx_by_id[id(other)]
                other_ref = audio_labels[oi]
                filter_parts.append(
                    f"{other_ref}asplit[dmix{ai}][dside{ai}]")
                audio_labels[oi] = f"[dmix{ai}]"
                my_ref = audio_labels[ai]
                p = duck.params
                filter_parts.append(
                    f"{my_ref}[dside{ai}]sidechaincompress="
                    f"threshold={p['threshold']}:ratio={p['ratio']}"
                    f":attack={p['attack']}:release={p['release']}[duck{ai}]")
                audio_labels[ai] = f"[duck{ai}]"

            if len(audio_labels) == 1:
                audio_out = audio_labels[0]
                # フィルタなしの生入力参照（[N:a]）はフィルタグラフのラベルではないため、
                # -map にはブラケットを外したストリーム指定（N:a）で渡す
                inner = audio_out[1:-1]
                if audio_out.startswith("[") and inner.endswith(":a") \
                        and inner[:-2].isdigit():
                    audio_out = inner
            else:
                amix_in = "".join(audio_labels)
                audio_out = "[aout]"
                filter_parts.append(
                    f"{amix_in}amix=inputs={len(audio_labels)}:normalize=0{audio_out}"
                )

            # normalize_audio（loudnorm）: 最終音声にラウドネス正規化を適用
            if self._loudnorm_target is not None and audio_out is not None:
                ln_in = audio_out if audio_out.startswith("[") else f"[{audio_out}]"
                filter_parts.append(
                    f"{ln_in}loudnorm=I={self._loudnorm_target}:TP=-1.5:LRA=11[aout_ln]")
                audio_out = "[aout_ln]"

        # 出力前の映像後処理（draft縮小・GIFパレット生成）
        video_map = current_base
        if getattr(self, "_draft", False):
            # ドラフト: 解像度を半分に（幾何は保持、偶数寸法に丸め）
            filter_parts.append(
                f"{video_map}scale=trunc(iw/4)*2:trunc(ih/4)*2[vdraft]")
            video_map = "[vdraft]"
        if fmt["kind"] == "gif":
            # 高品質パレット: split→palettegen→paletteuse を1グラフで実行
            filter_parts.append(
                f"{video_map}split[gsrc][gpg];"
                f"[gpg]palettegen=stats_mode=diff[gpal];"
                f"[gsrc][gpal]paletteuse=dither=bayer:bayer_scale=5"
                f":diff_mode=rectangle[vgif]")
            video_map = "[vgif]"

        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)

        # チャプター: FFMETADATAを追加入力にして -map_metadata で埋め込む
        meta_idx = None
        emit_meta = bool(self._markers) and fmt["has_audio"]
        if emit_meta:
            meta_path = self._chapters_metadata_path()
            if not getattr(self, "_dry_run", False):
                self._write_chapters_metadata(meta_path)
            # メタ入力のストリーム index = 既存 -i 個数（color 1 + オブジェクト入力数）
            meta_idx = 1 + len(sorted_objects)
            cmd.extend(["-f", "ffmetadata", "-i", meta_path])

        use_audio = bool(audio_out) and fmt["has_audio"]
        if filter_parts:
            cmd.extend(["-filter_complex", ";".join(filter_parts)])
            # 映像Objectが無い（音声のみ＋音声フィルタ）場合、video_mapは
            # 生入力参照（[0:v]）のまま。filter_complex併用時の -map に
            # ブラケット付きで渡すとグラフ出力ラベル扱いになり
            # "Output with label '0:v' does not exist" で落ちるため、
            # 音声側と同様にストリーム指定（0:v）へ外す
            vm_inner = video_map[1:-1]
            if video_map.startswith("[") and vm_inner.endswith(":v") \
                    and vm_inner[:-2].isdigit():
                video_map = vm_inner
            cmd.extend(["-map", video_map])
            if use_audio:
                cmd.extend(["-map", audio_out])

        if meta_idx is not None:
            cmd.extend(["-map_metadata", str(meta_idx)])

        # --- 出力形式ごとのエンコード指定 ---
        cmd.extend(self._encode_args(fmt, use_audio))

        # thumbnail: 単一フレーム抽出（-ss + -frames:v 1、-update で単一画像出力）
        if fmt["kind"] == "thumb":
            cmd.extend(["-ss", str(self._thumbnail_at), "-frames:v", "1",
                        "-update", "1", output_path])
            return cmd

        # 部分レンダ: 出力側 -ss/-t で窓を切り出す（フィルタのt基準は保つ）
        window = getattr(self, "_render_window", None)
        if window is not None:
            w_start, w_end = window
            w_end = self.duration if w_end is None else min(w_end, self.duration)
            out_dur = max(0.0, w_end - w_start)
            if w_start > 0:
                cmd.extend(["-ss", str(w_start)])
            cmd.extend(["-t", str(out_dur), output_path])
        else:
            cmd.extend(["-t", str(self.duration), output_path])

        return cmd

    def _encode_args(self, fmt, use_audio):
        """出力形式に応じた -c:v / -pix_fmt / -c:a 等のエンコード引数を返す"""
        kind = fmt["kind"]
        draft = bool(getattr(self, "_draft", False))
        args = []
        if kind == "thumb":
            return ["-pix_fmt", "rgba", "-an"]
        if kind == "gif":
            # パレット適用済みなのでコーデック指定は不要。音声なし。
            return ["-an"]
        if kind == "webp":
            q = "60" if draft else "80"
            return ["-c:v", "libwebp", "-lossless", "0", "-q:v", q,
                    "-loop", "0", "-an"]
        if kind == "pngseq":
            return ["-c:v", "png", "-pix_fmt", "rgba", "-an"]
        if kind == "webm":
            pix = "yuva420p" if fmt["alpha"] else "yuv420p"
            crf = "34" if draft else "24"
            args = ["-c:v", "libvpx-vp9", "-pix_fmt", pix,
                    "-b:v", "0", "-crf", crf, "-auto-alt-ref", "0"]
            if use_audio:
                args.extend(["-c:a", "libopus"])
            else:
                args.append("-an")
            return args
        # h264 / 指定エンコーダ（yuv420p固定・透過非対応コンテナ）
        if getattr(self, "_alpha", False):
            raise ValueError(
                f"alpha=True は透過対応の出力(.webm/.webp/.png)でのみ有効です。\n"
                f"現在の出力形式({kind})では yuv420p 固定のため透明背景が黒潰れします。\n"
                f"透過が必要なら .webm / .webp / 連番.png で出力してください。")
        args = ["-c:v", self._encoder_cv]
        if draft:
            args.extend(self._encoder_draft_args)
        else:
            args.extend(self._encoder_args)
        args.extend(["-pix_fmt", "yuv420p"])
        if use_audio:
            args.extend(["-c:a", "aac"])
        else:
            args.append("-an")
        return args


# --- 遅延解決の相互参照（関数本体からのみ使用: 循環importを避けるため末尾で束縛）---
from scriptvedit.audio import _probe_audio_length
from scriptvedit.cache import _apply_time_effects_to_duration, _build_morph_frame_extract_cmd, _build_unified_ops, _checkpoint_cache_path, _compute_save_points, _file_fingerprint, _is_bakeable, _is_pending_cache_path, _layer_cache_paths, _morph_cache_path, _morph_input_frame_path, _particle_cache_path, _split_ops, _validate_morph_position, _web_cache_path
from scriptvedit.expr import Expr, lt, max, min, step
from scriptvedit.ffmpeg import _decoder_input_args, _ffmpeg_available_encoders, _run_ffmpeg, _run_ffmpeg_to_cache, _unique_tmp_path
from scriptvedit.filters.audio import _build_audio_effect_filters, _build_audio_pre_filters
from scriptvedit.filters.video import _build_effect_filters, _build_input_args, _build_move_exprs, _build_transform_filters, _build_video_overlay_parts, _build_video_pre_filters, _get_base_dimensions, _optimize_filter_chain
from scriptvedit.objects import Object, _web_frames_dir
from scriptvedit.assets import resolve_layer_path
from scriptvedit.plugins import _autoload_plugins
from scriptvedit.state import _ACTIVE_QUALITY, _ARTIFACT_DIR, _CACHE_DIR, _CONFIGURE_KEYS, _ENCODER_MAP, _ENGINE_VER, _GEN_COUNTER, _PRESETS, _TERMINAL_FRAME_EFFECTS, _TIME_LIVE_EFFECTS, _detect_media_type, _suggest_hint
from scriptvedit.timeline import Pause, Scene, _AnchorMarker, _ScenePad
from scriptvedit.validate import _require_number, _validate_ffmpeg_color
from scriptvedit.web import label
