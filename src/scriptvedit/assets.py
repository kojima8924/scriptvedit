# -*- coding: utf-8 -*-
"""素材(assets/)とレイヤーファイルのパス解決

レイヤーファイルや examples/tests は cwd に依存せずに素材を参照できる必要がある。
本モジュールは利用者プロジェクトの `assets/` ディレクトリを自動発見し、
`asset("images/onigiri_tenmusu.png")` のような相対指定を絶対パスへ解決する。

## プロジェクトの assets/ の発見順（**利用者プロジェクト優先**）

  1. カレントディレクトリから上方向に `assets/` を探索
     （想定運用: 動画編集用フォルダから scriptvedit をライブラリとして使い、
      そのフォルダ固有の assets/ を持つ）
  2. 実行中のレイヤーファイルの位置から上方向に `assets/` を探索
  3. パッケージ位置から上方向に `assets/` を探索
     （editable インストール: <repo>/src/scriptvedit/ → <repo>/assets）

注意: パッケージ位置を先に見ると、editable インストール（標準構成）では
リポジトリ同梱の assets/ が常に勝ち、利用者プロジェクトの assets/ が
永久に無視される。この順序は逆転させないこと。
結果はキャッシュしない（cwd 変更・レイヤー切替に追随できなくなるため。
探索は isdir 数回で十分安い）。

## asset() の解決順序（共有ライブラリ + 自動取り込み）

環境変数 `SCRIPTVEDIT_ASSETS` は「assets ディレクトリの上書き指定」ではなく、
**共有素材ライブラリの探索パス（複数可・`;` 区切り。PATH と同じ流儀）**である。

  1. <project>/assets/<relpath>              手で置いた素材（最優先）
  2. <project>/assets/_imported/<relpath>    過去に自動コピー済みの共有素材
  3. SCRIPTVEDIT_ASSETS の各パス/<relpath>   共有ライブラリ
       → 見つかったら 2 の場所へ**コピーして**、コピー先のパスを返す
  4. FileNotFoundError（difflib による「もしかして」候補付き）

コピーは dry_run でも常に行う: asset() の戻り値は ffmpeg コマンドに埋まるため、
dry_run と本レンダでパスが食い違うとスナップショットが壊れる（一貫性が最優先）。
キャッシュ鍵は**内容ハッシュ**なので、コピーでパスが変わっても再レンダは起きない。

コピー結果は `assets/_imported/` に残るため、プロジェクトは共有ライブラリ無しでも
自己完結してレンダできる（配布・別マシンへの clone が安全）。
"""
import inspect as _inspect
import os
import shutil as _shutil
import warnings as _warnings

_ENV_VAR = "SCRIPTVEDIT_ASSETS"
# 共有ライブラリから自動コピーした素材の置き場（assets/ 直下）
IMPORTED_DIR = "_imported"


def _search_up(start):
    """start から親方向へ `assets` ディレクトリを探す"""
    d = os.path.abspath(start)
    while True:
        cand = os.path.join(d, "assets")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _current_layer_dir():
    """実行中のレイヤーファイルのディレクトリ（レイヤー外なら None）"""
    try:
        from scriptvedit.project import Project
        proj = Project._current
        cur = getattr(proj, "_current_layer_file", None) if proj is not None else None
        if cur:
            return os.path.dirname(os.path.abspath(cur))
    except Exception:
        pass
    return None


def assets_dir():
    """プロジェクトの素材ディレクトリ(assets/)の絶対パスを返す。見つからなければ例外。

    環境変数による上書きは無い（SCRIPTVEDIT_ASSETS は共有ライブラリの探索パス）。
    """
    starts = [os.getcwd()]
    layer_dir = _current_layer_dir()
    if layer_dir:
        starts.append(layer_dir)
    starts.append(os.path.dirname(os.path.abspath(__file__)))
    for start in starts:
        found = _search_up(start)
        if found:
            return found
    raise FileNotFoundError(
        "素材ディレクトリ assets/ が見つかりません。\n"
        "プロジェクト直下に assets/ を作ってください"
        "（`scriptvedit new <path>` で雛形を生成できます）。\n"
        f"※ 環境変数 {_ENV_VAR} は assets/ の上書きではなく、"
        "共有素材ライブラリの探索パス（; 区切り）です。")


def library_dirs():
    """共有素材ライブラリの探索パス一覧（環境変数 SCRIPTVEDIT_ASSETS、`;` 区切り）"""
    env = os.environ.get(_ENV_VAR) or ""
    dirs = []
    for part in env.split(";"):
        part = part.strip().strip('"')
        if part:
            dirs.append(os.path.abspath(part))
    return dirs


def _rel_parts(relpath):
    return [p for p in str(relpath).replace("\\", "/").split("/") if p not in ("", ".")]


def imported_dir():
    """共有ライブラリからの自動コピー先（<project>/assets/_imported）"""
    return os.path.join(assets_dir(), IMPORTED_DIR)


def _fmt_size(n):
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f}MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.1f}KB"
    return f"{n}B"


def _same_content(a, b):
    """2ファイルの内容が同じか（内容ハッシュ。キャッシュ鍵と同じ判定基準）"""
    from scriptvedit.cache import _file_fingerprint
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        return _file_fingerprint(a) == _file_fingerprint(b)
    except OSError:
        return False


def _copy_atomic(src, dst):
    """一時ファイル → os.replace でアトミックにコピー（中断で壊れた素材を残さない）"""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + f".tmp{os.getpid()}"
    try:
        _shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _find_in_library(parts):
    """共有ライブラリから素材を探す（見つかった絶対パス or None）"""
    for lib in library_dirs():
        cand = os.path.join(lib, *parts)
        if os.path.exists(cand):
            return cand
    return None


def _suggest(relpath, project_assets):
    """difflib で「もしかして」候補を作る（プロジェクト assets/ + 共有ライブラリ）"""
    avail = []
    roots = []
    if project_assets and os.path.isdir(project_assets):
        roots.append(project_assets)
    roots += [d for d in library_dirs() if os.path.isdir(d)]
    for base in roots:
        for root, _dirs, files in os.walk(base):
            for f in files:
                avail.append(
                    os.path.relpath(os.path.join(root, f), base).replace("\\", "/"))
    if not avail:
        return ""
    import difflib
    near = difflib.get_close_matches(
        str(relpath).replace("\\", "/"), sorted(set(avail)), n=3, cutoff=0.4)
    return f"\nもしかして: {', '.join(near)}?" if near else ""


def asset(relpath, *, must_exist=True):
    """素材を絶対パスで解決する（プロジェクト → _imported → 共有ライブラリ）。

    例: asset("images/onigiri_tenmusu.png") / asset("audio/Impact-38.mp3")
    cwd に依存しないため、レイヤーファイル・テスト・examples から安全に使える。

    共有ライブラリ（環境変数 SCRIPTVEDIT_ASSETS、`;` 区切り）にしか無い素材は
    `assets/_imported/<relpath>` へコピーしてから、そのコピー先のパスを返す
    （プロジェクトが自己完結する。dry_run でも同じパスを返すためコピーは常に行う）。
    """
    parts = _rel_parts(relpath)
    base = assets_dir()
    direct = os.path.join(base, *parts)
    imported = os.path.join(base, IMPORTED_DIR, *parts)

    if os.path.exists(direct):
        return direct
    if os.path.exists(imported):
        # 共有ライブラリ側が更新されていても、取り込み済みの内容を優先する
        # （黙って上書きするとレンダ結果が勝手に変わるため。警告だけ出す）
        lib_hit = _find_in_library(parts)
        if lib_hit and not _same_content(lib_hit, imported):
            _warnings.warn(
                f"共有ライブラリの素材が取り込み済みのコピーと異なります: {'/'.join(parts)}\n"
                f"  取り込み済み: {imported}\n"
                f"  共有ライブラリ: {lib_hit}\n"
                f"  取り込み済みを使います。更新したい場合はコピーを削除して再実行してください。",
                stacklevel=2)
        return imported

    if not must_exist:
        # 存在チェックをスキップする用途（出力先の組み立て等）。コピーもしない。
        return direct

    lib_hit = _find_in_library(parts)
    if lib_hit:
        _copy_atomic(lib_hit, imported)
        try:
            size = _fmt_size(os.path.getsize(imported))
        except OSError:
            size = "?"
        shown = "/".join(["assets", IMPORTED_DIR] + parts)
        print(f"[assets] 素材をコピーしました: {shown} ({size}) ← {lib_hit}")
        return imported

    raise FileNotFoundError(
        f"素材が見つかりません: {'/'.join(parts)}\n"
        f"  探した場所: {direct} / {imported}"
        + (f" / 共有ライブラリ {', '.join(library_dirs())}" if library_dirs() else "")
        + _suggest(relpath, base))


def here(relpath=""):
    """「今実行中のレイヤーファイル（または呼び出し元スクリプト）の隣」を絶対パスで返す。

    レイヤー固有のフィクスチャ（HTML/SRT/LUT など）を cwd 非依存で参照するための糖衣。
    例: Object(here("scene.html"))
    """
    base = None
    try:
        from scriptvedit.project import Project
        proj = Project._current
        cur = getattr(proj, "_current_layer_file", None) if proj is not None else None
        if cur:
            base = os.path.dirname(os.path.abspath(cur))
    except Exception:
        base = None
    if base is None:
        # レイヤー外（通常のスクリプト）からの呼び出し: 呼び出し元ファイルの隣
        frame = _inspect.stack()[1]
        base = os.path.dirname(os.path.abspath(frame.filename))
    return os.path.join(base, *str(relpath).replace("\\", "/").split("/")) if relpath else base


def resolve_layer_path(filename, project=None):
    """Project.layer() のファイル名を cwd 非依存に解決する。

    絶対パス → そのまま / cwd 相対で存在 → それ /
    実行中レイヤーファイルの隣（レイヤー内で更にレイヤーを読む場合）/
    呼び出し元スクリプトの隣 の順に探す。
    """
    if os.path.isabs(filename):
        return filename
    if os.path.exists(filename):
        return os.path.abspath(filename)
    cur = getattr(project, "_current_layer_file", None) if project is not None else None
    bases = []
    if cur:
        bases.append(os.path.dirname(os.path.abspath(cur)))
    try:
        for fr in _inspect.stack()[1:]:
            fn = fr.filename
            if not fn or fn.startswith("<"):
                continue
            # scriptvedit パッケージ自身のフレームは飛ばす
            if os.path.dirname(os.path.abspath(fn)).startswith(
                    os.path.dirname(os.path.abspath(__file__))):
                continue
            bases.append(os.path.dirname(os.path.abspath(fn)))
            break
    except Exception:
        pass
    for b in bases:
        cand = os.path.join(b, filename)
        if os.path.exists(cand):
            return cand
    return filename
