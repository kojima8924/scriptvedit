# -*- coding: utf-8 -*-
"""監査issue #14/#15/#16 の P0 回帰テスト

- #14: Plan/Render構造差の検出、`>>` の長い逆順連結・循環
- #15: obj*n の異FPS素材、外部WebM(VP8/AV1)のデコーダ選択
- #16: layer cacheの依存集合差し替え検出
"""
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from scriptvedit import Object, Project, asset  # noqa: E402
from scriptvedit.cache import _layer_cache_paths  # noqa: E402
from scriptvedit.ffmpeg import _decoder_input_args  # noqa: E402


def _need_ffmpeg():
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe が無い環境")


def _lavfi(tmp_path, name, spec, extra=()):
    _need_ffmpeg()
    out = tmp_path / name
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", spec,
         *extra, str(out)],
        check=True, capture_output=True, timeout=60)
    return str(out)


def _center_rgb(video, at, w=64, h=36):
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(video),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        check=True, capture_output=True, timeout=30)
    c = ((h // 2) * w + w // 2) * 3
    return tuple(r.stdout[c:c + 3])


# --- #14: `>>` の依存解決 ---------------------------------------------------

def test_rshift_long_reverse_chain_resolves():
    """10個の逆順連結でも全開始時刻が正しく収束する"""
    p = Project()
    p.configure(width=320, height=180, fps=30)
    src = asset("video/fox_noaudio.mp4")
    objs = [Object(src)[0:1] for _ in range(10)]
    chain = objs[9]
    for o in reversed(objs[:-1]):
        chain = chain >> o
    p._layers = [(0, len(p.objects), 0)]
    p._resolve_anchors()
    assert [o.start_time for o in objs] == [9.0, 8.0, 7.0, 6.0, 5.0,
                                            4.0, 3.0, 2.0, 1.0, 0]


def test_rshift_cycle_detected():
    """a >> b; b >> a は関係Objectを示す循環エラー"""
    p = Project()
    p.configure(width=320, height=180, fps=30)
    src = asset("video/fox_noaudio.mp4")
    x = Object(src)[0:1]
    y = Object(src)[0:1]
    x >> y
    y >> x
    p._layers = [(0, len(p.objects), 0)]
    with pytest.raises(RuntimeError, match="循環"):
        p._resolve_anchors()


def test_rshift_three_way_cycle_detected():
    """3個以上の循環も検出する"""
    p = Project()
    p.configure(width=320, height=180, fps=30)
    src = asset("video/fox_noaudio.mp4")
    a, b, c = (Object(src)[0:1] for _ in range(3))
    a >> b >> c
    c >> a
    p._layers = [(0, len(p.objects), 0)]
    with pytest.raises(RuntimeError, match="循環"):
        p._resolve_anchors()


# --- #14: Plan/Render構造差 -------------------------------------------------

def test_nondeterministic_layer_detected(tmp_path):
    """実行のたびに尺が変わるレイヤーは診断付きで停止する"""
    counter = tmp_path / "count.txt"
    counter.write_text("0")
    layer = tmp_path / "nondet.py"
    layer.write_text(
        "from scriptvedit import *\n"
        f"_c = r\"{counter}\"\n"
        "n = int(open(_c).read()) + 1\n"
        "open(_c, 'w').write(str(n))\n"
        "o = Object(asset('images/onigiri_tenmusu.png'))\n"
        "o.time(n) <= move(x=0.5, y=0.5)\n",
        encoding="utf-8")
    p = Project()
    p.configure(width=320, height=180, fps=30)
    p.layer(str(layer))
    with pytest.raises(RuntimeError, match="Plan と Render で一致しません"):
        p.render(str(tmp_path / "x.mp4"), dry_run=True)


def test_deterministic_layer_passes(tmp_path):
    """決定的なレイヤーは従来どおり通る（誤検出しない）"""
    layer = tmp_path / "det.py"
    layer.write_text(
        "from scriptvedit import *\n"
        "o = Object(asset('images/onigiri_tenmusu.png'))\n"
        "o.time(2) <= move(x=0.5, y=0.5)\n",
        encoding="utf-8")
    p = Project()
    p.configure(width=320, height=180, fps=30)
    p.layer(str(layer))
    result = p.render(str(tmp_path / "x.mp4"), dry_run=True)
    assert result["main"]


# --- #15: obj*n の異FPS -----------------------------------------------------

def test_repeat_mixed_fps_real_render(tmp_path):
    """10fps素材を30fps Projectで*2しても2周目の内容が正しい"""
    _need_ffmpeg()
    src = tmp_path / "rb10.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=red:s=64x36:d=1:r=10",
         "-f", "lavfi", "-i", "color=c=blue:s=64x36:d=1:r=10",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
         "-map", "[v]", "-pix_fmt", "yuv420p", str(src)],
        check=True, capture_output=True, timeout=60)
    layer = tmp_path / "rep.py"
    layer.write_text(
        "from scriptvedit import *\n"
        f"o = Object(r\"{src}\") * 2\n"
        "o <= move(x=0.5, y=0.5, anchor='center')\n",
        encoding="utf-8")
    out = tmp_path / "o.mp4"
    p = Project()
    p.configure(width=64, height=36, fps=30)  # 素材10fps ≠ Project30fps
    p.layer(str(layer))
    p.render(str(out), timeout=120)

    r1 = _center_rgb(out, 2.5)   # 2周目の赤区間
    r2 = _center_rgb(out, 3.5)   # 2周目の青区間
    assert r1[0] > 128 and r1[2] < 100, f"2周目(赤)が不正: {r1}"
    assert r2[2] > 128 and r2[0] < 100, f"2周目(青)が不正: {r2}"


def test_repeat_after_speed(tmp_path):
    """speed適用後の*2も全区間を反復する（途中だけの反復にならない）"""
    _need_ffmpeg()
    src = tmp_path / "rb10.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=red:s=64x36:d=1:r=10",
         "-f", "lavfi", "-i", "color=c=blue:s=64x36:d=1:r=10",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
         "-map", "[v]", "-pix_fmt", "yuv420p", str(src)],
        check=True, capture_output=True, timeout=60)
    layer = tmp_path / "sp.py"
    layer.write_text(
        "from scriptvedit import *\n"
        f"o = Object(r\"{src}\")\n"
        "o <= speed(2.0)\n"          # 2秒→1秒(赤0.5+青0.5)
        "o2 = o * 2\n"               # ×2 = 2秒
        "o2 <= move(x=0.5, y=0.5, anchor='center')\n",
        encoding="utf-8")
    out = tmp_path / "o.mp4"
    p = Project()
    p.configure(width=64, height=36, fps=30)
    p.layer(str(layer))
    p.render(str(out), timeout=120)
    # 2周目にも青(各周の後半)が現れる = 全区間が反復されている
    r = _center_rgb(out, 1.75)
    assert r[2] > 128 and r[0] < 100, f"2周目後半(青)が不正: {r}"


# --- #15: 外部WebMのデコーダ選択 --------------------------------------------

def test_external_vp8_webm_renders(tmp_path):
    """VP8 WebMはlibvpxで読み、レンダが成功する"""
    src = _lavfi(tmp_path, "vp8.webm", "color=c=red:s=64x36:d=1:r=10",
                 ("-c:v", "libvpx", "-b:v", "200k"))
    args = _decoder_input_args(src, "video", 10)
    assert args[:2] == ["-c:v", "libvpx"], args

    layer = tmp_path / "v8.py"
    layer.write_text(
        "from scriptvedit import *\n"
        f"o = Object(r\"{src}\")\n"
        "o.time(1) <= move(x=0.5, y=0.5, anchor='center')\n",
        encoding="utf-8")
    out = tmp_path / "o.mp4"
    p = Project()
    p.configure(width=64, height=36, fps=10)
    p.layer(str(layer))
    p.render(str(out), timeout=120)
    assert _center_rgb(out, 0.5)[0] > 128


def test_external_plain_vp9_forced_libvpx(tmp_path):
    """外部VP9 WebMはlibvpx-vp9（alpha保持の可能性に備える）"""
    src = _lavfi(tmp_path, "vp9.webm", "color=c=red:s=64x36:d=1:r=10",
                 ("-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "40"))
    args = _decoder_input_args(src, "video", 10)
    assert args[:2] == ["-c:v", "libvpx-vp9"], args


def test_cache_artifact_webm_still_forced_vp9(tmp_path):
    """自前生成物(__cache__配下)のwebmはprobeせずlibvpx-vp9固定"""
    from scriptvedit.state import _ARTIFACT_DIR
    fake = os.path.join(_ARTIFACT_DIR, "web", "x", "deadbeef.webm")
    args = _decoder_input_args(fake, "video", 30)
    assert args[:2] == ["-c:v", "libvpx-vp9"], args


# --- #16: layer cacheの依存集合 ---------------------------------------------

def test_layer_cache_detects_dependency_swap(tmp_path, monkeypatch):
    """環境変数で素材をa→bへ切り替えたら旧キャッシュを使わない"""
    _need_ffmpeg()
    a = _lavfi(tmp_path, "a.png", "color=c=red:s=32x18:d=1",
               ("-frames:v", "1"))
    b = _lavfi(tmp_path, "b.png", "color=c=blue:s=32x18:d=1",
               ("-frames:v", "1"))
    layer = tmp_path / "envlayer.py"
    layer.write_text(
        "import os\nfrom scriptvedit import *\n"
        "o = Object(os.environ['SV_AUDIT_CLIP'])\n"
        "o.time(1) <= move(x=0.5, y=0.5)\n",
        encoding="utf-8")

    monkeypatch.setenv("SV_AUDIT_CLIP", a)
    p1 = Project()
    p1.configure(width=32, height=18, fps=10)
    p1.layer(str(layer), cache="make")
    p1.render(str(tmp_path / "m.mp4"), timeout=120)
    cache1, meta1 = _layer_cache_paths(str(layer), p1)
    assert os.path.exists(cache1)

    try:
        def _auto_uses_cache():
            p = Project()
            p.configure(width=32, height=18, fps=10)
            p.layer(str(layer), cache="auto")
            result = p.render(str(tmp_path / "x.mp4"), dry_run=True)
            return cache1.replace("\\", "/") in \
                " ".join(result["main"]).replace("\\", "/")

        # 同一素材aなら使う
        assert _auto_uses_cache()
        # bへ切り替えたら使わない（aは無変化のまま）
        monkeypatch.setenv("SV_AUDIT_CLIP", b)
        assert not _auto_uses_cache(), "依存差し替え後も旧キャッシュを使っている"
    finally:
        for path in (cache1, meta1):
            try:
                os.remove(path)
            except OSError:
                pass
