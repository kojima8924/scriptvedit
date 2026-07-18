# -*- coding: utf-8 -*-
"""DSL糖衣（タイムライン3点セット）のテスト

obj[a:b]  … 素材時間の切り出し（trim/atrim。表示尺は切り出し長が既定）
obj @ t   … タイムライン絶対配置（秒 or アンカー名。非進行）
a >> b    … 直後連結（pause.time() を挟める。非進行）
"""
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from scriptvedit import Object, Project, anchor, asset, pause, text  # noqa: E402


def _mk():
    p = Project()
    p.configure(width=320, height=180, fps=30)
    return p


def _two_color_video(tmp_path):
    """前半2秒=赤、後半2秒=青の4秒動画（イン点検証用）"""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg が無い環境")
    out = tmp_path / "redblue.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=red:s=64x36:d=2:r=10",
         "-f", "lavfi", "-i", "color=c=blue:s=64x36:d=2:r=10",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
         "-map", "[v]", "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True, timeout=60)
    return str(out)


def _resolve(p):
    """直接生成したObject群をリゾルバにかける（render はレイヤー再実行で
    objects を破棄するため、単体テストでは内部リゾルバを直接使う）"""
    p._layers = [(0, len(p.objects), 0)]
    p._resolve_anchors()
    return p._calc_total_duration()


# --- obj[a:b] スライス -----------------------------------------------------

def test_slice_sets_trim_and_duration():
    """スライスは trim/atrim(start, duration) を積み、表示尺を切り出し長にする"""
    _mk()
    o = Object(asset("video/fox_noaudio.mp4"))[1:3]
    trims = [e for e in o.effects if e.name == "trim"]
    assert trims and trims[0].params == {"start": 1.0, "duration": 2.0}
    atrims = [e for e in o.audio_effects if e.name == "atrim"]
    assert atrims and atrims[0].params == {"start": 1.0, "duration": 2.0}
    assert o.duration == 2.0


def test_slice_open_end_uses_auto_duration():
    """obj[3:] はアウト点省略＝素材末尾まで（尺は自動確定）"""
    _mk()
    o = Object(asset("video/fox_noaudio.mp4"))[3:]
    assert o.duration is None and o._duration_auto
    # length() は「末尾-3秒」（fox_noaudio は約5.5秒）
    assert abs(o.length() - (5.545 - 3)) < 0.1


def test_slice_negative_indices():
    """負値は素材末尾からの相対（obj[-2:] = 末尾2秒）"""
    _mk()
    o = Object(asset("video/fox_noaudio.mp4"))[-2:]
    trims = [e for e in o.effects if e.name == "trim"]
    assert trims and abs(trims[0].params["start"] - (5.545 - 2)) < 0.1


def test_slice_errors():
    """step・非スライス・画像・逆転範囲は明示エラー"""
    _mk()
    src = asset("video/fox_noaudio.mp4")
    with pytest.raises(ValueError, match="step"):
        Object(src)[::2]
    with pytest.raises(TypeError, match="スライス"):
        Object(src)[2]
    with pytest.raises(TypeError, match="素材時間がない"):
        Object(asset("images/onigiri_tenmusu.png"))[1:2]
    with pytest.raises(ValueError, match="end > start"):
        Object(src)[3:1]


def test_slice_in_point_real_render(tmp_path):
    """実レンダ: 赤2秒+青4秒の動画を[2:4]で切ると先頭フレームが青"""
    src = _two_color_video(tmp_path)
    layer = tmp_path / "slice_layer.py"
    layer.write_text(
        "from scriptvedit import *\n"
        f"o = Object(r\"{src}\")[2:4]\n"
        "o <= move(x=0.5, y=0.5, anchor='center')\n",
        encoding="utf-8")
    out = tmp_path / "out.mp4"
    p = Project()
    p.configure(width=64, height=36, fps=10, background_color="black")
    p.layer(str(layer))
    p.render(str(out), timeout=120)

    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(out), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        check=True, capture_output=True, timeout=30)
    center = ((36 // 2) * 64 + 64 // 2) * 3
    r, g, b = result.stdout[center:center + 3]
    assert b > 128 and r < 100, f"先頭フレームが青でない: RGB=({r},{g},{b})"


# --- obj @ t 絶対配置 ------------------------------------------------------

def test_at_places_absolutely_and_does_not_advance():
    """@は絶対配置かつ非進行（後続の順次配置に影響しない）"""
    p = _mk()
    src = asset("video/fox_noaudio.mp4")
    a = Object(src)[0:2]           # 順次: 0〜2
    b = Object(src)[0:1] @ 10      # 絶対: 10〜11（カーソルは進めない）
    c = Object(src)[0:2]           # 順次: 2〜4（bの影響を受けない）
    total = _resolve(p)
    assert (a.start_time, b.start_time, c.start_time) == (0, 10.0, 2.0)
    assert abs(total - 11.0) < 1e-6  # 総尺はbの終端まで


def test_at_anchor_name():
    """@ にアンカー名を渡せる（"名前.end" 等）"""
    p = _mk()
    src = asset("video/fox_noaudio.mp4")
    a = Object(src)[0:2]
    a.time(2, name="head")
    b = Object(src)[0:1] @ "head.end"
    _resolve(p)
    assert b.start_time == 2.0


def test_at_undefined_anchor_raises():
    """@ の未定義アンカーは診断付きエラー"""
    p = _mk()
    Object(asset("video/fox_noaudio.mp4"))[0:1] @ "no_such_anchor"
    with pytest.raises(RuntimeError, match="no_such_anchor"):
        _resolve(p)


def test_at_validates_operand():
    """@ の右辺は数値かアンカー名のみ・負の時刻は拒否"""
    _mk()
    src = asset("video/fox_noaudio.mp4")
    with pytest.raises(TypeError):
        Object(src) @ [1, 2]
    with pytest.raises(ValueError):
        Object(src) @ -1


# --- a >> b 連結 -----------------------------------------------------------

def test_rshift_chains_after():
    """a >> b は b を a の終了直後に開始（pause.time() を挟める）"""
    p = _mk()
    src = asset("video/fox_noaudio.mp4")
    a = Object(src)[0:2]
    b = Object(src)[0:1]
    c = Object(src)[0:1]
    a >> b                          # b: 2〜3
    b >> pause.time(0.5) >> c       # c: 3.5〜4.5
    _resolve(p)
    assert b.start_time == 2.0
    assert c.start_time == 3.5


def test_rshift_after_at():
    """スライス+@+>> の組み合わせ: src[3:8] @ 12 の直後に次クリップ"""
    p = _mk()
    src = asset("video/fox_noaudio.mp4")
    a = Object(src)[1:3] @ 12
    b = Object(src)[0:1]
    a >> b
    _resolve(p)
    assert a.start_time == 12.0
    assert b.start_time == 14.0


def test_rshift_requires_known_duration():
    """先行アイテムの尺未確定は日本語エラー"""
    p = _mk()
    src = asset("video/fox_noaudio.mp4")
    a = Object(src)          # time()もスライスもなし＝尺未確定
    b = Object(src)[0:1]
    a >> b
    with pytest.raises(RuntimeError, match="尺が確定していません"):
        _resolve(p)


def test_rshift_rejects_bad_operand():
    """>> の右辺の型チェックと自己連結の拒否"""
    _mk()
    a = Object(asset("video/fox_noaudio.mp4"))[0:1]
    with pytest.raises(TypeError):
        a >> 5
    with pytest.raises(ValueError):
        a >> a


# --- 既存機能との整合 ------------------------------------------------------

def test_until_from_floating_start():
    """浮動配置(@)のuntilは実開始時刻を基準に尺を計算する"""
    p = _mk()
    src = asset("video/fox_noaudio.mp4")
    a = Object(src)[0:2]
    a.time(2, name="head")
    b = Object(src) @ 1
    b.until("head.end")     # 1〜2 → dur=1
    _resolve(p)
    assert b.start_time == 1.0
    assert b.duration == 1.0


def test_text_slice_rejected():
    """テキストにも素材時間はない"""
    _mk()
    t = text("字幕", size=48, border=3)
    with pytest.raises(TypeError, match="素材時間がない"):
        t[1:2]
