# -*- coding: utf-8 -*-
"""scriptvedit.testkit 公開APIの正常系テスト"""

from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")

import scriptvedit.testkit as testkit


def test_load_image_normalizes_gray_rgba_and_path(tmp_path):
    gray = np.array([[0, 255], [64, 128]], dtype=np.uint8)
    assert testkit._load_image(gray).shape == (2, 2, 3)

    rgba = np.zeros((2, 2, 4), dtype=np.uint8)
    rgba[:, :, :3] = (10, 20, 30)
    assert np.array_equal(testkit._load_image(rgba), rgba[:, :, :3])

    path = tmp_path / "image.png"
    Image.fromarray(rgba, mode="RGBA").save(path)
    loaded = testkit._load_image(path)
    assert loaded.dtype == np.uint8 and loaded.shape == (2, 2, 3)


@pytest.mark.parametrize("shape,size", [((9, 11), 3), ((12, 8), 5), ((15, 17), 7)])
def test_uniform_filter_scipy_and_numpy_paths_match(monkeypatch, shape, size):
    """SciPy有/無のreflect境界処理を同じ入力で一致させる"""
    if testkit._scipy_uniform_filter is None:
        pytest.skip("scipy が無い環境")
    rng = np.random.default_rng(8924)
    image = rng.normal(size=shape)
    expected = testkit._uniform_filter(image, size)
    monkeypatch.setattr(testkit, "_scipy_uniform_filter", None)
    actual = testkit._uniform_filter(image, size)
    assert np.allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_ssim_and_frame_diff_normal_paths(tmp_path):
    base = np.zeros((9, 9, 3), dtype=np.uint8)
    changed = base.copy()
    changed[4, 4] = (255, 64, 0)
    assert testkit.ssim(base, base) == pytest.approx(1.0)
    assert testkit.ssim(base, changed) < 1.0

    heatmap = tmp_path / "nested" / "heat.png"
    stats = testkit.frame_diff(base, changed, heatmap)
    assert stats["max_abs"] == 255
    assert stats["diff_ratio"] == pytest.approx(1 / 81)
    assert heatmap.exists()


def test_extract_frame_builds_accurate_command(monkeypatch, tmp_path):
    """ffmpeg呼び出しをモックし、正常なPNG抽出と出力側seekを検証する"""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    output = tmp_path / "frame.png"
    seen = {}

    monkeypatch.setattr(testkit, "_check_ffmpeg", lambda: None)

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        Image.fromarray(np.full((4, 5, 3), 80, dtype=np.uint8), mode="RGB").save(cmd[-1])
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(testkit.subprocess, "run", fake_run)
    frame = testkit.extract_frame(video, 1.25, output)
    assert frame.shape == (4, 5, 3)
    assert seen["cmd"].index("-ss") > seen["cmd"].index("-i")
    assert output.exists()


def test_assert_frame_and_assert_frames_normal_paths(monkeypatch):
    expected = np.full((9, 9, 3), 42, dtype=np.uint8)
    monkeypatch.setattr(testkit, "extract_frame", lambda video, at: expected.copy())
    assert testkit.assert_frame("video.mp4", 1.0, expected) == pytest.approx(1.0)
    assert testkit.assert_frames(
        "video.mp4", [(0.5, expected), (1.0, expected)]) == pytest.approx([1.0, 1.0])

