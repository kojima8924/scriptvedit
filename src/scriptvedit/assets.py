# -*- coding: utf-8 -*-
"""素材(assets/)とレイヤーファイルのパス解決

レイヤーファイルや examples/tests は cwd に依存せずに素材を参照できる必要がある。
本モジュールはリポジトリの `assets/` ディレクトリを自動発見し、
`asset("images/onigiri_tenmusu.png")` のような相対指定を絶対パスへ解決する。

解決順序:
  1. 環境変数 SCRIPTVEDIT_ASSETS（明示指定・最優先）
  2. パッケージ位置から上方向に `assets/` を探索
     （editable インストール: <repo>/src/scriptvedit/ → <repo>/assets）
  3. カレントディレクトリから上方向に `assets/` を探索
"""
import inspect as _inspect
import os

_ENV_VAR = "SCRIPTVEDIT_ASSETS"
_CACHED_DIR = [None]


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


def assets_dir():
    """素材ディレクトリ(assets/)の絶対パスを返す。見つからなければ例外。"""
    env = os.environ.get(_ENV_VAR)
    if env:
        if not os.path.isdir(env):
            raise FileNotFoundError(
                f"環境変数 {_ENV_VAR} が指すディレクトリがありません: {env}")
        return os.path.abspath(env)
    if _CACHED_DIR[0] and os.path.isdir(_CACHED_DIR[0]):
        return _CACHED_DIR[0]
    for start in (os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
        found = _search_up(start)
        if found:
            _CACHED_DIR[0] = found
            return found
    raise FileNotFoundError(
        "素材ディレクトリ assets/ が見つかりません。\n"
        f"リポジトリ外から使う場合は環境変数 {_ENV_VAR} に assets/ の絶対パスを設定してください。")


def asset(relpath, *, must_exist=True):
    """assets/ 配下の素材を絶対パスで解決する。

    例: asset("images/onigiri_tenmusu.png") / asset("audio/Impact-38.mp3")
    cwd に依存しないため、レイヤーファイル・テスト・examples から安全に使える。
    """
    path = os.path.join(assets_dir(), *str(relpath).replace("\\", "/").split("/"))
    if must_exist and not os.path.exists(path):
        base = assets_dir()
        avail = []
        for root, _dirs, files in os.walk(base):
            for f in files:
                avail.append(os.path.relpath(os.path.join(root, f), base).replace("\\", "/"))
        hint = ""
        if avail:
            import difflib
            near = difflib.get_close_matches(
                str(relpath).replace("\\", "/"), avail, n=3, cutoff=0.4)
            if near:
                hint = f"\nもしかして: {', '.join(near)}?"
        raise FileNotFoundError(f"素材が見つかりません: {path}{hint}")
    return path


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
