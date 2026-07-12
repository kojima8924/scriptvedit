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
import threading as _threading
import atexit as _atexit

from scriptvedit.state import _CACHE_DIR


# --- ファイル指紋（内容ハッシュ方式）---
#
# 指紋は「ファイル内容の sha256 先頭16桁」。パスにも mtime にも依存しないため、
# 別マシンへの clone・ファイルのコピー・CRLF変換なしの touch ではキャッシュ鍵が
# 変わらない（＝スナップショットが環境をまたいで一致する＝移植性）。
#
# 性能対策は2段構え:
#   1) プロセス内メモ化（_FFP_MEMO）: 同一 render 中に同じファイルを再ハッシュしない
#   2) ディスクキャッシュ（__cache__/ffp.json）: (絶対パス, サイズ, mtime_ns) →
#      内容ハッシュ を記録。mtime が変わらない限り2回目以降は再ハッシュ不要。
#      壊れていたら黙って捨てて再計算にフォールバックする（正しさは内容ハッシュ側が担保）。
_FFP_MEMO = {}
_FFP_DISK = [None]         # 遅延ロードするディスクキャッシュ dict（None=未ロード）
_FFP_DIRTY = [False]
_FFP_LOCK = _threading.Lock()
_FFP_CACHE_VER = 1


def _ffp_cache_file():
    return os.path.join(_CACHE_DIR, "ffp.json")


def _hash_file_content(path):
    """ファイル全内容の sha256 先頭16桁（1MBずつのチャンク読み）"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _load_ffp_disk_cache():
    """ディスクキャッシュを遅延ロード（呼び出し元で _FFP_LOCK 保持のこと）"""
    if _FFP_DISK[0] is None:
        entries = {}
        try:
            with open(_ffp_cache_file(), encoding="utf-8") as f:
                data = json.load(f)
            if (isinstance(data, dict) and data.get("v") == _FFP_CACHE_VER
                    and isinstance(data.get("entries"), dict)):
                entries = data["entries"]
        except (OSError, ValueError):
            entries = {}  # 破損・不在時は再計算にフォールバック
        _FFP_DISK[0] = entries
    return _FFP_DISK[0]


def _flush_ffp_disk_cache():
    """ディスクキャッシュをアトミックに書き出す（atexit / render後に呼ばれる）"""
    with _FFP_LOCK:
        if not _FFP_DIRTY[0] or not _FFP_DISK[0]:
            return
        entries = dict(_FFP_DISK[0])
        _FFP_DIRTY[0] = False
    path = _ffp_cache_file()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # 他プロセスが書いた分をマージ（丸ごと上書きで失わないように）
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
            if isinstance(old, dict) and old.get("v") == _FFP_CACHE_VER:
                merged = dict(old.get("entries") or {})
                merged.update(entries)
                entries = merged
        except (OSError, ValueError):
            pass
        tmp = f"{path}.tmp{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"v": _FFP_CACHE_VER, "entries": entries}, f)
        os.replace(tmp, path)
    except OSError:
        pass  # キャッシュ書き出し失敗は致命的ではない


def _file_fingerprint(path):
    """ファイル内容の指紋（sha256 先頭16桁の文字列）を返す。

    パス・mtime に依存しないので、同一内容のファイルはどこに置いても同じ指紋になる。
    ファイルが無ければ従来通り OSError を送出する。
    """
    st = os.stat(path)  # 不在なら OSError（呼び出し側が捕捉している）
    key = f"{os.path.abspath(path).replace(chr(92), '/')}|{st.st_size}|{st.st_mtime_ns}"
    with _FFP_LOCK:
        h = _FFP_MEMO.get(key)
        if h is not None:
            return h
        h = _load_ffp_disk_cache().get(key)
        if isinstance(h, str):
            _FFP_MEMO[key] = h
            return h
    h = _hash_file_content(path)  # I/O はロック外で
    with _FFP_LOCK:
        _FFP_MEMO[key] = h
        _load_ffp_disk_cache()[key] = h
        _FFP_DIRTY[0] = True
    return h


_atexit.register(_flush_ffp_disk_cache)


def _is_cache_artifact_path(path):
    """パスがキャッシュディレクトリ(__cache__)配下の生成物かどうか判定"""
    abs_path = os.path.abspath(path).replace("\\", "/")
    cache_root = os.path.abspath(_CACHE_DIR).replace("\\", "/")
    return abs_path.startswith(cache_root + "/")


def _is_pending_cache_path(path):
    """未生成のキャッシュ予定パスかどうか判定（dry_run中のprobe抑制用）

    dry_runではチェックポイント等のsourceが「これから生成される予定のパス」に
    差し替わるため、存在しないキャッシュ配下パスへのffprobeは警告スパムになる。
    """
    return (not os.path.exists(path)) and _is_cache_artifact_path(path)


# ファイルパスを値に持つパラメータ（指紋には生パスではなく内容指紋を使う）。
# 生パスを混ぜるとリポジトリの置き場所でキャッシュ鍵が変わり移植性が失われるため、
# ここに挙げたキーはパラメータ列挙から除外し、下で *_ffp として内容指紋を足す。
_OP_PATH_PARAMS = {"lut": ("file",), "mask": ("image",), "mask_wipe": ("image",)}


def _op_fingerprint_str(op):
    """単一opのフィンガープリント文字列を生成"""
    parts = [op.name]
    skip = _OP_PATH_PARAMS.get(op.name, ())
    for k in sorted(op.params):
        if k in skip:
            continue
        v = op.params[k]
        parts.append(f"{k}={v.to_ffmpeg('u') if isinstance(v, Expr) else repr(v)}")
    # policy はレンダ結果に影響しないためフィンガープリントに含めない
    quality = getattr(op, 'quality', 'final')
    parts.append(f"q={quality}")
    # morph_to: ターゲット画像のFFPをsignatureに含める
    if op.name == "morph_to" and hasattr(op, '_morph_target'):
        try:
            tgt_ffp = _file_fingerprint(op._morph_target.source)
            parts.append(f"tgt_ffp={tgt_ffp}")
        except OSError:
            parts.append(f"tgt_src={_norm_src_path(str(op._morph_target.source))}")
    # assemble_from: 集合元画像のFFPをsignatureに含める
    if op.name == "assemble_from" and hasattr(op, '_assemble_source'):
        try:
            parts.append(f"asm_ffp={_file_fingerprint(op._assemble_source.source)}")
        except OSError:
            parts.append(f"asm_src={_norm_src_path(str(op._assemble_source.source))}")
    # lut: LUTファイルのFFPをsignatureに含める（内容変更でキャッシュ無効化）
    if op.name == "lut":
        lut_file = op.params.get("file")
        try:
            parts.append(f"lut_ffp={_file_fingerprint(lut_file)}")
        except (OSError, TypeError):
            parts.append(f"lut_src={_norm_src_path(str(lut_file))}")
    # mask/mask_wipe: マスク画像のFFPをsignatureに含める（内容変更でキャッシュ無効化）
    if op.name in ("mask", "mask_wipe"):
        mask_img = op.params.get("image")
        try:
            parts.append(f"mask_ffp={_file_fingerprint(mask_img)}")
        except (OSError, TypeError):
            parts.append(f"mask_src={_norm_src_path(str(mask_img))}")
    # プラグインEffect: ソースコードの内容ハッシュを鍵に含める
    # （プラグインを書き換えたらキャッシュが再生成されるように）
    plug = _EFFECT_PLUGINS.get(op.name)
    if plug is not None:
        parts.append(f"plugin_ffp={plug.code_ffp}")
    return "|".join(parts)


def _op_prefix_fingerprint(ops_list):
    """ops列のSHA256[:16]フィンガープリントを計算"""
    sigs = []
    for typ, op in ops_list:
        sigs.append(f"{typ}:{_op_fingerprint_str(op)}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    return key


def _is_bakeable(op_type, op):
    """opがbakeable（チェックポイント保存対象）かどうか判定"""
    if op_type == "transform":
        return True
    if op_type == "effect" and op.name in _BAKEABLE_EFFECTS:
        return True
    return False


def _compute_save_points(ops):
    """保存点を計算: FSP(forceの全位置) + RAA(最右auto、force以降になければ)
    ops: [(type, op), ...]
    戻り値: set of indices
    """
    save_points = set()
    # FSP: policy="force" の全位置（bakeableかつforce）
    force_indices = []
    for i, (typ, op) in enumerate(ops):
        if getattr(op, 'policy', 'auto') == "force" and _is_bakeable(typ, op):
            save_points.add(i)
            force_indices.append(i)

    # RAA: bakeable ops中の最右 policy="auto"（最後のFSP以降にforceがなければ）
    last_force = max(force_indices) if force_indices else -1
    raa_candidate = None
    for i, (typ, op) in enumerate(ops):
        policy = getattr(op, 'policy', 'auto')
        if policy == "auto" and _is_bakeable(typ, op):
            raa_candidate = i
    # RAAはFSP以降にforceがない場合のみ有効（= 最後のforce以降にautoがある場合）
    if raa_candidate is not None and raa_candidate > last_force:
        save_points.add(raa_candidate)

    return save_points


def _src_bucket(path):
    """キャッシュ生成物を仕分けるサブディレクトリ名（8桁）

    パス文字列ではなく内容指紋から導出するため、リポジトリを別の場所へ置いても
    同じバケットになる（移植性）。指紋が取れない場合（dry_run 中の未生成キャッシュ
    予定パスなど）だけ、パス文字列（cwd相対に正規化）で代用する。
    """
    try:
        return _file_fingerprint(path)[:8]
    except OSError:
        return hashlib.sha256(_norm_src_path(path).encode()).hexdigest()[:8]


def _norm_src_path(path):
    """パス文字列を正規化（cwd配下なら相対化・区切りは / ）"""
    try:
        rel = os.path.relpath(path, os.getcwd())
        if not rel.startswith(".."):
            path = rel
    except ValueError:
        pass  # 別ドライブ等（Windows）はそのまま
    return path.replace("\\", "/")


def _checkpoint_cache_path(original_source, ops, duration=None, fps=None, quality="final"):
    """チェックポイントのキャッシュファイルパスを計算（signature方式）"""
    try:
        ffp = _file_fingerprint(original_source)
        sigs = [f"ffp={ffp}"]
    except OSError:
        sigs = [f"src={_norm_src_path(original_source)}"]
    opfp = _op_prefix_fingerprint(ops)
    sigs.append(opfp)
    sigs.append(f"q={quality}")
    # 注: 生成される中間物の内容は draft/本番で同一のため、_ACTIVE_QUALITY(rq)は
    # 鍵に含めない（含めると本番↔draft で全キャッシュミスになり無駄な再生成が起きる）
    sigs.append(f"ev={_ENGINE_VER}")
    if duration is not None:
        sigs.append(f"dur={duration}")
    if fps is not None:
        sigs.append(f"fps={fps}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    # video入力 + transform-only でも動画ならmkv (ffv1)
    is_video = _detect_media_type(original_source) in ("video",)
    ext = ".mkv" if (duration is not None or is_video) else ".png"
    cache_dir = os.path.join(_ARTIFACT_DIR, "checkpoint", _src_bucket(original_source))
    return os.path.join(cache_dir, f"{key}{ext}")


def _morph_cache_path(src_path, morph_op, duration, fps, quality="final"):
    """morph WebMのキャッシュパスを計算"""
    if _is_cache_artifact_path(src_path):
        # キャッシュ生成物はパス自体が内容由来の鍵を含むため、常にパス文字列署名を使う
        # （dry_runでは未生成でFFP不可→実レンダとの鍵不一致を防ぐ）
        sigs = [f"src={_norm_src_path(src_path)}"]
    else:
        try:
            sigs = [f"ffp={_file_fingerprint(src_path)}"]
        except OSError:
            sigs = [f"src={_norm_src_path(src_path)}"]
    # ターゲットFFP
    if hasattr(morph_op, '_morph_target'):
        try:
            sigs.append(f"tgt_ffp={_file_fingerprint(morph_op._morph_target.source)}")
        except OSError:
            sigs.append(f"tgt_src={morph_op._morph_target.source}")
    sigs.append(f"op={_op_fingerprint_str(morph_op)}")
    sigs.append(f"dur={duration}")
    sigs.append(f"fps={fps}")
    sigs.append(f"q={quality}")
    # 中間物は draft/本番で同一内容のため rq(_ACTIVE_QUALITY)は鍵に含めない
    sigs.append(f"ev={_ENGINE_VER}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    cache_dir = os.path.join(_ARTIFACT_DIR, "morph", _src_bucket(src_path))
    return os.path.join(cache_dir, f"{key}.mkv")


def _particle_cache_path(img_path, particle_op, duration, fps, quality="final"):
    """explode_to/assemble_from の粒子アニメmkvキャッシュパスを計算

    img_path: 粒子化する単一画像（explode=直前ソース, assemble=集合元）
    """
    if _is_cache_artifact_path(img_path):
        sigs = [f"src={_norm_src_path(img_path)}"]
    else:
        try:
            sigs = [f"ffp={_file_fingerprint(img_path)}"]
        except OSError:
            sigs = [f"src={_norm_src_path(img_path)}"]
    sigs.append(f"op={_op_fingerprint_str(particle_op)}")
    sigs.append(f"dur={duration}")
    sigs.append(f"fps={fps}")
    sigs.append(f"q={quality}")
    # 中間物は draft/本番で同一内容のため rq(_ACTIVE_QUALITY)は鍵に含めない
    sigs.append(f"ev={_ENGINE_VER}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    cache_dir = os.path.join(_ARTIFACT_DIR, "particle", _src_bucket(img_path))
    return os.path.join(cache_dir, f"{key}.mkv")


def _morph_input_frame_path(src_path):
    """morph入力用の最終フレームPNGの置き場所を導出

    morph（PIL）は画像しか読めないため、動画ソース（前ベイクの.mkv等）は
    最終フレームをRGBA PNGに抽出してからmorphの入力にする。
    """
    if _is_cache_artifact_path(src_path):
        # キャッシュ生成物: 拡張子差し替え（パス自体が内容由来の鍵を含む）
        return os.path.splitext(src_path)[0] + ".morphsrc.png"
    # 元素材が動画: キャッシュ配下に内容由来の鍵で生成
    try:
        sig = f"ffp={_file_fingerprint(src_path)}"
    except OSError:
        sig = f"src={_norm_src_path(src_path)}"
    key = hashlib.sha256(sig.encode()).hexdigest()[:16]
    return os.path.join(_ARTIFACT_DIR, "morph", "src", f"{key}.png")


def _build_morph_frame_extract_cmd(src_path, frame_path):
    """動画の最終フレームをRGBA PNGに抽出するffmpegコマンド（morph入力用）

    -sseof -0.5: 終端0.5秒前からデコード
    -update 1: 残り全フレームを同一ファイルへ上書き → 最終フレームが残る
    -pix_fmt rgba: alpha維持（前ベイクのffv1 yuva444p等の透過を保つ）
    """
    cmd = ["ffmpeg", "-y", "-sseof", "-0.5"]
    cmd.extend(_decoder_input_args(src_path, "video", None))
    cmd.extend(["-update", "1", "-pix_fmt", "rgba", frame_path])
    return cmd


def _validate_morph_position(bakeable_ops):
    """終端フレーム生成Effect(morph_to/explode_to/assemble_from)が
    bakeable opsの末尾に1つだけあることを検証"""
    term_indices = [i for i, (typ, op) in enumerate(bakeable_ops)
                    if typ == "effect" and op.name in _TERMINAL_FRAME_EFFECTS]
    if not term_indices:
        return
    if len(term_indices) > 1:
        names = [bakeable_ops[i][1].name for i in term_indices]
        raise ValueError(
            f"morph_to/explode_to/assemble_from は1つのObjectに1回しか適用できません"
            f"（{len(term_indices)}個指定: {names}, idx={term_indices}）。\n"
            f"複数段には compute() 等で中間素材を生成して分割してください。")
    term_idx = term_indices[0]
    term_name = bakeable_ops[term_idx][1].name
    # 終端Effectの後に他のbakeable opがあればエラー（policy='off'は実質ライブなのでスキップ）
    for i in range(term_idx + 1, len(bakeable_ops)):
        after_op = bakeable_ops[i][1]
        if getattr(after_op, 'policy', 'auto') == "off":
            continue
        raise ValueError(
            f"{term_name} はbakeable opsの末尾に配置してください。"
            f"{term_name}(idx={term_idx})の後に "
            f"{after_op.name}(idx={i})があります。\n"
            f"回避策: {after_op.name} を {term_name} の前に移動するか、"
            f"-{after_op.name}(...) で checkpoint対象から除外してください。")


def _build_unified_ops(obj):
    """transforms + effects を統合ops列に変換（2-tuple: type, op）"""
    ops = []
    for t in obj.transforms:
        ops.append(("transform", t))
    for e in obj.effects:
        ops.append(("effect", e))
    return ops


def _split_ops(ops):
    """ops列をbakeable/liveに分離"""
    bakeable = [(t, op) for t, op in ops if _is_bakeable(t, op)]
    live = [(t, op) for t, op in ops if not _is_bakeable(t, op)]
    return bakeable, live


def _apply_time_effects_to_duration(dur, effects):
    """時間系 live Effect（speed/freeze_frame）を尺に反映した表示尺を返す。

    speed: 尺 / factor、freeze_frame: 尺 + duration、reverse: 変化なし。
    effects の並び順に適用する。
    """
    cur = dur
    for e in effects:
        name = getattr(e, "name", None)
        if name == "speed":
            f = e.params.get("factor", 1.0)
            if f:
                cur = cur / f
        elif name == "freeze_frame":
            # at がその時点の実効尺以上なら静止区間は成立しない（length()と整合）
            at = e.params.get("at", 0.0)
            if at < cur:
                cur = cur + e.params.get("duration", 0.0)
    return cur


def _web_cache_path(obj, project):
    """Web Objectのsignatureベースキャッシュパスを計算"""
    sigs = []
    # テンプレートファイルのフィンガープリント
    try:
        ffp = _file_fingerprint(obj._web_source)
        sigs.append(f"ffp={ffp}")
    except (OSError, TypeError):
        sigs.append(f"src={obj._web_source}")
    # データハッシュ
    data_str = json.dumps(obj._web_data, sort_keys=True, default=str)
    sigs.append(f"data={hashlib.sha256(data_str.encode()).hexdigest()[:12]}")
    sigs.append(f"dur={obj.duration}")
    fps = obj._web_fps or project.fps
    sigs.append(f"fps={fps}")
    if obj._web_size:
        sigs.append(f"size={obj._web_size[0]}x{obj._web_size[1]}")
    if obj._web_deps:
        deps_fps = []
        for dep in sorted(obj._web_deps):
            try:
                deps_fps.append(str(_file_fingerprint(dep)))
            except OSError:
                deps_fps.append(dep)
        sigs.append(f"deps={hashlib.sha256('|'.join(deps_fps).encode()).hexdigest()[:12]}")
    sigs.append(f"ev={_ENGINE_VER}")
    key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
    name = obj._web_name or "web"
    return os.path.join(_ARTIFACT_DIR, "web", name, f"{key}.webm")


def _layer_cache_paths(filename, project=None):
    """レイヤーキャッシュパスを計算（signature方式）"""
    basename = os.path.splitext(os.path.basename(filename))[0]
    if project is not None:
        # signatureベース
        sigs = []
        try:
            ffp = _file_fingerprint(filename)
            sigs.append(f"ffp={ffp}")
        except (OSError, TypeError):
            sigs.append(f"src={filename}")
        sigs.append(f"ev={_ENGINE_VER}")
        sigs.append(f"w={project.width}")
        sigs.append(f"h={project.height}")
        sigs.append(f"fps={project.fps}")
        sigs.append(f"bg={project.background_color}")
        key = hashlib.sha256("||".join(sigs).encode()).hexdigest()[:16]
        layer_dir = os.path.join(_ARTIFACT_DIR, "layer", basename)
        return (os.path.join(layer_dir, f"{key}.mkv"),
                os.path.join(layer_dir, f"{key}.anchors.json"))
    # フォールバック（後方互換）
    return (os.path.join(_CACHE_DIR, f"{basename}.mkv"),
            os.path.join(_CACHE_DIR, f"{basename}.anchors.json"))


def _iter_cache_files(cache_dir=_CACHE_DIR):
    """__cache__ 配下の全ファイルを (絶対パス, カテゴリ, サイズ, mtime) で列挙する"""
    if not os.path.isdir(cache_dir):
        return
    root_abs = os.path.abspath(cache_dir)
    for dirpath, _dirs, files in os.walk(cache_dir):
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            rel = os.path.relpath(path, root_abs)
            parts = rel.replace("\\", "/").split("/")
            # artifacts/<種別>/... は種別を、それ以外は先頭ディレクトリをカテゴリに
            if parts[0] == "artifacts" and len(parts) > 1:
                category = parts[1]
            elif len(parts) > 1:
                category = parts[0]
            else:
                category = "(直下)"
            yield path, category, st.st_size, st.st_mtime


def _fmt_size(n):
    """バイト数を人間可読な単位で整形"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024.0


def cache_stats(cache_dir=_CACHE_DIR):
    """種別ごとの件数・合計サイズを集計して表示する"""
    stats = {}
    total_n = 0
    total_sz = 0
    for _path, category, size, _mtime in _iter_cache_files(cache_dir):
        c = stats.setdefault(category, [0, 0])
        c[0] += 1
        c[1] += size
        total_n += 1
        total_sz += size
    print(f"=== キャッシュ統計: {os.path.abspath(cache_dir)} ===")
    if total_n == 0:
        print("  (キャッシュはありません)")
        return
    print(f"  {'種別':<16} {'件数':>8} {'サイズ':>12}")
    print("  " + "-" * 38)
    for category in sorted(stats):
        n, sz = stats[category]
        print(f"  {category:<16} {n:>8} {_fmt_size(sz):>12}")
    print("  " + "-" * 38)
    print(f"  {'合計':<16} {total_n:>8} {_fmt_size(total_sz):>12}")


def cache_gc(keep_days, cache_dir=_CACHE_DIR):
    """keep_days 日より古い（mtime基準）キャッシュファイルを削除する"""
    cutoff = _time.time() - float(keep_days) * 86400.0
    removed_n = 0
    removed_sz = 0
    for path, _category, size, mtime in list(_iter_cache_files(cache_dir)):
        if mtime < cutoff:
            try:
                os.remove(path)
                removed_n += 1
                removed_sz += size
            except OSError:
                pass
    # 空ディレクトリを掃除
    _prune_empty_dirs(cache_dir)
    print(f"GC完了: {keep_days}日より古い {removed_n}件 "
          f"({_fmt_size(removed_sz)}) を削除しました")
    return removed_n


def _prune_empty_dirs(root):
    """空ディレクトリを再帰的に削除する（bottom-up）"""
    if not os.path.isdir(root):
        return
    for dirpath, dirs, files in os.walk(root, topdown=False):
        if dirpath == root:
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
        except OSError:
            pass


def cache_clear(cache_dir=_CACHE_DIR):
    """__cache__ を丸ごと削除する"""
    if os.path.isdir(cache_dir):
        _shutil.rmtree(cache_dir, ignore_errors=True)
        print(f"キャッシュ全削除: {os.path.abspath(cache_dir)}")
    else:
        print(f"キャッシュディレクトリはありません: {cache_dir}")


# watch が監視する拡張子（レイヤー.py + 画像/音声/フォント/字幕/HTML等の素材）


# --- 遅延解決の相互参照（関数本体からのみ使用: 循環importを避けるため末尾で束縛）---
from scriptvedit.expr import Expr, max
from scriptvedit.ffmpeg import _decoder_input_args
from scriptvedit.plugins import _EFFECT_PLUGINS
from scriptvedit.state import _ARTIFACT_DIR, _BAKEABLE_EFFECTS, _ENGINE_VER, _TERMINAL_FRAME_EFFECTS, _detect_media_type
