# -*- coding: utf-8 -*-
"""asset() の解決順序（プロジェクト → _imported → 共有ライブラリ）と自動コピーの検証

共有ライブラリ = 環境変数 SCRIPTVEDIT_ASSETS（`;` 区切りの探索パス）。
"""
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from scriptvedit import asset, assets_dir  # noqa: E402
from scriptvedit.assets import IMPORTED_DIR, library_dirs  # noqa: E402


def _write(path, data=b"dummy"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """空のプロジェクト（cwd = プロジェクト直下、assets/ あり、共有ライブラリ無し）"""
    root = tmp_path / "proj"
    (root / "assets").mkdir(parents=True)
    monkeypatch.chdir(root)
    monkeypatch.delenv("SCRIPTVEDIT_ASSETS", raising=False)
    yield root


def test_project_assets_wins(proj, monkeypatch):
    """1. プロジェクトの assets/ が最優先（_imported・共有ライブラリより先）"""
    mine = _write(str(proj / "assets" / "bgm" / "x.mp3"), b"MINE")
    _write(str(proj / "assets" / IMPORTED_DIR / "bgm" / "x.mp3"), b"IMPORTED")
    lib = proj.parent / "lib"
    _write(str(lib / "bgm" / "x.mp3"), b"LIB")
    monkeypatch.setenv("SCRIPTVEDIT_ASSETS", str(lib))
    assert os.path.samefile(asset("bgm/x.mp3"), mine)
    assert os.path.samefile(assets_dir(), proj / "assets")


def test_imported_resolves(proj):
    """2. _imported/ 配下の取り込み済み素材が解決される"""
    imp = _write(str(proj / "assets" / IMPORTED_DIR / "bgm" / "x.mp3"), b"IMPORTED")
    assert os.path.samefile(asset("bgm/x.mp3"), imp)


def test_library_copies_into_imported(proj, monkeypatch, capsys):
    """3. 共有ライブラリの素材は _imported/ へコピーされ、コピー先のパスが返る"""
    lib = proj.parent / "lib"
    src = _write(str(lib / "bgm" / "テーマ曲.mp3"), b"L" * 2048)
    monkeypatch.setenv("SCRIPTVEDIT_ASSETS", str(lib))

    got = asset("bgm/テーマ曲.mp3")
    dst = proj / "assets" / IMPORTED_DIR / "bgm" / "テーマ曲.mp3"  # 相対構造・ファイル名を維持
    assert os.path.samefile(got, dst)
    assert dst.read_bytes() == open(src, "rb").read()
    out = capsys.readouterr().out
    assert "素材をコピーしました" in out and "_imported/bgm/テーマ曲.mp3" in out
    # 一時ファイルを残さない（アトミックコピー）
    assert not [p for p in os.listdir(os.path.dirname(dst)) if ".tmp" in p]

    # 2回目は再コピーしない（_imported から即返る）
    mtime = os.stat(dst).st_mtime_ns
    got2 = asset("bgm/テーマ曲.mp3")
    assert os.path.samefile(got2, dst)
    assert os.stat(dst).st_mtime_ns == mtime
    assert "素材をコピーしました" not in capsys.readouterr().out


def test_library_multiple_paths(proj, monkeypatch):
    """共有ライブラリは `;` 区切りで複数指定でき、先頭から順に探す"""
    lib1, lib2 = proj.parent / "lib1", proj.parent / "lib2"
    _write(str(lib1 / "a.png"), b"A1")
    _write(str(lib1 / "only1.png"), b"O1")
    _write(str(lib2 / "a.png"), b"A2")
    _write(str(lib2 / "only2.png"), b"O2")
    monkeypatch.setenv("SCRIPTVEDIT_ASSETS", f"{lib1};{lib2}")
    assert library_dirs() == [str(lib1), str(lib2)]
    assert open(asset("a.png"), "rb").read() == b"A1"  # 先勝ち
    assert open(asset("only2.png"), "rb").read() == b"O2"  # 2番目のパスからも解決
    assert os.path.exists(proj / "assets" / IMPORTED_DIR / "only2.png")


def test_library_update_warns_and_keeps_imported(proj, monkeypatch):
    """取り込み済みと内容が違う共有ライブラリ素材: 警告し、取り込み済みを使う"""
    lib = proj.parent / "lib"
    _write(str(lib / "a.png"), b"NEW")
    imp = _write(str(proj / "assets" / IMPORTED_DIR / "a.png"), b"OLD")
    monkeypatch.setenv("SCRIPTVEDIT_ASSETS", str(lib))
    with pytest.warns(UserWarning, match="共有ライブラリの素材"):
        got = asset("a.png")
    assert os.path.samefile(got, imp)
    assert open(got, "rb").read() == b"OLD"  # 黙って上書きしない（レンダ結果を変えない）


def test_must_exist_false_does_not_copy(proj, monkeypatch):
    """must_exist=False は存在チェックをスキップし、コピーもしない"""
    lib = proj.parent / "lib"
    _write(str(lib / "audio" / "bgm.mp3"), b"L")
    monkeypatch.setenv("SCRIPTVEDIT_ASSETS", str(lib))
    got = asset("audio/bgm.mp3", must_exist=False)
    assert got == str(proj / "assets" / "audio" / "bgm.mp3")
    assert not os.path.exists(proj / "assets" / IMPORTED_DIR / "audio" / "bgm.mp3")


def test_not_found_suggests(proj, monkeypatch):
    """4. 見つからないときは difflib の「もしかして」候補を出す（ライブラリも走査）"""
    _write(str(proj / "assets" / "images" / "logo.png"))
    lib = proj.parent / "lib"
    _write(str(lib / "audio" / "Impact-38.mp3"))
    monkeypatch.setenv("SCRIPTVEDIT_ASSETS", str(lib))
    with pytest.raises(FileNotFoundError) as e:
        asset("images/logo.jpg")
    assert "もしかして" in str(e.value) and "images/logo.png" in str(e.value)
    with pytest.raises(FileNotFoundError) as e2:
        asset("audio/Impact-39.mp3")
    assert "audio/Impact-38.mp3" in str(e2.value)


def test_env_no_longer_overrides_assets_dir(proj, monkeypatch):
    """旧仕様の廃止: SCRIPTVEDIT_ASSETS は assets/ の上書きではない"""
    lib = proj.parent / "lib"
    _write(str(lib / "a.png"), b"L")
    monkeypatch.setenv("SCRIPTVEDIT_ASSETS", str(lib))
    assert os.path.samefile(assets_dir(), proj / "assets")


def test_copy_does_not_invalidate_cache(proj, monkeypatch):
    """コピーでパスが変わってもキャッシュ鍵（内容ハッシュ）は変わらない = 再レンダしない"""
    from scriptvedit import resize
    from scriptvedit.cache import _checkpoint_cache_path, _src_bucket, _src_signature

    lib = proj.parent / "lib"
    src = _write(str(lib / "images" / "logo.png"), b"\x89PNG\r\n\x1a\n" + b"P" * 512)
    monkeypatch.setenv("SCRIPTVEDIT_ASSETS", str(lib))

    ops = [("transform", resize(sx=0.5, sy=0.5))]
    before = _checkpoint_cache_path(src, ops)          # 共有ライブラリの元パスでの鍵
    got = asset("images/logo.png")                     # → _imported/ へコピー
    after = _checkpoint_cache_path(got, ops)           # コピー先パスでの鍵
    assert not os.path.samefile(src, got)
    assert _src_signature(src) == _src_signature(got)  # 内容指紋（パス非依存）
    assert _src_bucket(src) == _src_bucket(got)
    assert before == after, "コピーでキャッシュパスが変わった（再レンダが起きる）"


def test_project_is_self_contained_after_copy(proj, monkeypatch):
    """コピー後は共有ライブラリが無くても（環境変数を消しても）解決できる"""
    lib = proj.parent / "lib"
    _write(str(lib / "images" / "logo.png"), b"L")
    monkeypatch.setenv("SCRIPTVEDIT_ASSETS", str(lib))
    got = asset("images/logo.png")
    monkeypatch.delenv("SCRIPTVEDIT_ASSETS")
    shutil.rmtree(lib)
    assert os.path.samefile(asset("images/logo.png"), got)
