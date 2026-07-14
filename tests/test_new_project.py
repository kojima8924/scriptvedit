# -*- coding: utf-8 -*-
"""`scriptvedit new <path>` の雛形生成テスト（生成物が実際にレンダできること）"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from scriptvedit.cli import _main  # noqa: E402
from scriptvedit.scaffold import new_project  # noqa: E402

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def _has_ffmpeg():
    from shutil import which
    return which("ffmpeg") is not None


def test_scaffold_structure(tmp_path):
    """生成される構造（main.py / layers / assets / plugins / output / README / .gitignore）"""
    root = new_project(str(tmp_path / "myvideo"), quiet=True)
    for rel in ("main.py", "layers/intro.py", "README.md", ".gitignore",
                "plugins/README.md", "assets/images", "assets/audio", "output"):
        assert os.path.exists(os.path.join(root, *rel.split("/"))), rel
    gi = open(os.path.join(root, ".gitignore"), encoding="utf-8").read()
    for pat in ("output/", "__cache__/", "assets/_imported/"):
        assert pat in gi
    readme = open(os.path.join(root, "README.md"), encoding="utf-8").read()
    assert "SCRIPTVEDIT_ASSETS" in readme and "_imported" in readme


def test_scaffold_refuses_nonempty_dir(tmp_path):
    """既存ディレクトリが空でなければエラー（--force で許可）"""
    d = tmp_path / "used"
    d.mkdir()
    (d / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="空ではありません"):
        new_project(str(d), quiet=True)
    new_project(str(d), force=True, quiet=True)  # --force なら生成できる
    assert os.path.exists(d / "main.py")
    assert os.path.exists(d / "keep.txt")  # 既存ファイルは消さない


def test_cli_new(tmp_path, capsys):
    """CLI 経由: scriptvedit new <path> / 未知テンプレートはエラー / 案内メッセージ"""
    rc = _main(["new", str(tmp_path / "cliproj")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "次にやること" in out and "python main.py" in out
    assert os.path.exists(tmp_path / "cliproj" / "main.py")
    rc2 = _main(["new", str(tmp_path / "cliproj")])  # 空でない → エラー
    assert rc2 == 2


def test_scaffold_explainer(tmp_path):
    """--template explainer: 数式・字幕・BGM のレイヤーが入る"""
    root = new_project(str(tmp_path / "exp"), template="explainer", quiet=True)
    body = open(os.path.join(root, "layers", "body.py"), encoding="utf-8").read()
    bgm = open(os.path.join(root, "layers", "bgm.py"), encoding="utf-8").read()
    assert "formula(" in body and "text(" in body
    assert 'asset("audio/bgm.mp3"' in bgm
    main = open(os.path.join(root, "main.py"), encoding="utf-8").read()
    for f in ("intro.py", "body.py", "bgm.py"):
        assert f in main
    with pytest.raises(ValueError, match="未知のテンプレート"):
        new_project(str(tmp_path / "bad"), template="nope", quiet=True)


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg が無い")
def test_scaffold_renders(tmp_path):
    """生成した雛形が実際にレンダできる（短尺・小サイズ）"""
    root = new_project(str(tmp_path / "rendertest"), quiet=True, width=320, height=180,
                       fps=10)
    env = dict(os.environ)
    env["PYTHONPATH"] = _SRC + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("SCRIPTVEDIT_ASSETS", None)
    out = os.path.join(root, "output", "t.mp4")
    r = subprocess.run([sys.executable, "main.py", out], cwd=root, env=env,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert os.path.getsize(out) > 0
