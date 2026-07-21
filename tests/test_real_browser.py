# -*- coding: utf-8 -*-
"""実ブラウザ(Playwright/Chromium)での formula / web Object 生成テスト

CI(Linux)では Chromium を導入して実行される(監査 issue #17: コマンド文字列
だけでなく実際の生成物を検証する)。Chromium が無い環境では正直に skip。
"""
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from scriptvedit import Object, Project, formula  # noqa: E402


def _require_chromium():
    """Playwright + Chromium が実際に起動できることを確認(不可なら skip)"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright が無い環境")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            browser.close()
    except Exception as exc:
        pytest.skip(f"Chromium が起動できない環境: {type(exc).__name__}")


def _require_ffmpeg():
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe が無い環境")


def test_formula_real_png_generation(tmp_path):
    """formula() の数式PNGが実際に生成され、不透明画素を持つ"""
    _require_chromium()
    _require_ffmpeg()
    layer = tmp_path / "formula_layer.py"
    layer.write_text(
        "from scriptvedit import *\n"
        "eq = formula(r'x^2 + 1', size=48, color='white')\n"
        "eq.time(1) <= move(x=0.5, y=0.5, anchor='center')\n",
        encoding="utf-8")
    out = tmp_path / "f.mp4"
    p = Project()
    p.configure(width=320, height=180, fps=10, background_color="black")
    p.layer(str(layer))
    p.render(str(out), timeout=300)

    # 数式PNG自体が生成されている
    pngs = [o.source for o in p.objects
            if getattr(o, "source", "").endswith(".png")]
    assert pngs and os.path.getsize(pngs[0]) > 100
    # レンダ結果に白い画素(数式)が含まれる
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(out), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"],
        check=True, capture_output=True, timeout=60)
    assert max(r.stdout) > 200, "数式の白画素が見つからない"


def test_web_object_real_render(tmp_path):
    """web Object(HTML)が実ブラウザでキャプチャされ、指定色が画素に現れる"""
    _require_chromium()
    _require_ffmpeg()
    html = tmp_path / "solid.html"
    html.write_text(
        "<body style='margin:0;background:#ff0000'>"
        "<script>function renderFrame(t) {}</script></body>",
        encoding="utf-8")
    layer = tmp_path / "web_layer.py"
    layer.write_text(
        "from scriptvedit import *\n"
        f"w = Object(r\"{html}\", duration=1, size=(64, 36))\n"
        "w <= move(x=0.5, y=0.5, anchor='center')\n",
        encoding="utf-8")
    out = tmp_path / "w.mp4"
    p = Project()
    p.configure(width=64, height=36, fps=10, background_color="black")
    p.layer(str(layer))
    p.render(str(out), timeout=300)

    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(out), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        check=True, capture_output=True, timeout=60)
    c = ((36 // 2) * 64 + 32) * 3
    px = tuple(r.stdout[c:c + 3])
    assert px[0] > 128 and px[1] < 100, f"HTMLの赤が画素に現れない: {px}"
