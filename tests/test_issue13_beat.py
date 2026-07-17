# -*- coding: utf-8 -*-
"""issue #13 P2-16: beat 解析の長尺入力対策の検証

- 上限尺(_MAX_ANALYSIS_SEC)超過時はデコード段階で先頭区間へ切り詰め、
  警告を出して解析が完了すること
- 自己相関の FFT 化(fftconvolve)後も既知 BPM の合成クリック音で
  検出 BPM が実用上一致(±2 BPM 以内)すること
"""
import shutil
import subprocess

import pytest

# numpy/scipy([beat] extra)が無い環境ではモジュールごと skip
np = pytest.importorskip("numpy")
beat = pytest.importorskip("scriptvedit.beat")


def _require_ffmpeg():
    """ffmpeg が無い環境では正直に skip する(PASS 扱いにしない)"""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg が無い環境")


def _make_click_wav(path, *, bpm=120.0, duration=12.0, sr=22050):
    """ffmpeg lavfi で既知 BPM のクリック音(短いサイン波パルス)を生成する"""
    interval = 60.0 / bpm
    expr = (f"0.9*sin(2*PI*880*t)*lt(mod(t\\,{interval})\\,0.04)")
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi",
        "-i", f"aevalsrc={expr}:s={sr}:d={duration}",
        "-ac", "1", "-ar", str(sr),
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


def test_detect_beats_known_bpm(tmp_path):
    """既知 120BPM の合成クリック音で検出 BPM が ±2 以内"""
    _require_ffmpeg()
    wav = tmp_path / "click120.wav"
    _make_click_wav(wav, bpm=120.0, duration=12.0)
    res = beat.detect_beats(wav, min_bpm=60, max_bpm=200)
    assert abs(res["bpm"] - 120.0) <= 2.0, f"検出BPM={res['bpm']}"
    assert len(res["beats"]) >= 10


def test_max_analysis_sec_truncates_with_warning(tmp_path, monkeypatch):
    """上限尺超過の入力は警告付きで先頭のみ解析され、解析自体は完了する

    実際に1時間音声は作らず、上限を monkeypatch で 6 秒へ縮めて
    12 秒入力で超過経路を踏む。
    """
    _require_ffmpeg()
    wav = tmp_path / "click120_long.wav"
    _make_click_wav(wav, bpm=120.0, duration=12.0)
    monkeypatch.setattr(beat, "_MAX_ANALYSIS_SEC", 6)
    with pytest.warns(RuntimeWarning, match="先頭"):
        res = beat.detect_beats(wav, min_bpm=60, max_bpm=200)
    # デコードが先頭 6 秒へ切り詰められている(解析対象尺 = 上限尺)
    assert res["duration"] == pytest.approx(6.0, abs=0.1)
    # 切り詰め後も BPM 検出は成立する
    assert abs(res["bpm"] - 120.0) <= 2.0, f"検出BPM={res['bpm']}"
    assert all(t <= 6.0 + 0.1 for t in res["beats"])


def test_max_analysis_sec_no_warning_within_limit(tmp_path, monkeypatch):
    """上限尺以内の入力では切り詰め警告を出さない"""
    _require_ffmpeg()
    wav = tmp_path / "click120_short.wav"
    _make_click_wav(wav, bpm=120.0, duration=8.0)
    monkeypatch.setattr(beat, "_MAX_ANALYSIS_SEC", 30)
    with warnings_none():
        res = beat.detect_beats(wav, min_bpm=60, max_bpm=200)
    assert res["duration"] == pytest.approx(8.0, abs=0.1)


class warnings_none:
    """RuntimeWarning(切り詰め警告)が出ないことを検証するコンテキスト"""

    def __enter__(self):
        import warnings as _w
        self._ctx = _w.catch_warnings(record=True)
        self._records = self._ctx.__enter__()
        import warnings as _w2
        _w2.simplefilter("always")
        return self._records

    def __exit__(self, exc_type, exc, tb):
        self._ctx.__exit__(exc_type, exc, tb)
        if exc_type is None:
            truncation = [r for r in self._records
                          if issubclass(r.category, RuntimeWarning)
                          and "先頭" in str(r.message)]
            assert not truncation, f"切り詰め警告が出ています: {truncation}"
        return False


def test_fft_autocorrelation_matches_np_correlate():
    """FFT ベース自己相関が np.correlate(mode='full') と実用上一致する

    _tempo_candidates が内部で使う fftconvolve(x, x[::-1]) の lag>=0 部分が
    旧実装の np.correlate と数値的に一致することを直接検証(ffmpeg 不要)。
    """
    from scipy.signal import fftconvolve
    rng = np.random.default_rng(42)
    x = rng.standard_normal(5000)
    x = x - x.mean()
    n = len(x)
    ref = np.correlate(x, x, mode="full")[n - 1:]
    fft = fftconvolve(x, x[::-1], mode="full")[n - 1:]
    assert np.allclose(ref, fft, rtol=1e-8, atol=1e-6)


def test_tempo_candidates_on_synthetic_envelope():
    """合成 onset 包絡(周期 0.5 秒 = 120BPM)から正しい周期候補が出る(ffmpeg 不要)"""
    frame_dt = 512 / 22050.0
    n = int(30.0 / frame_dt)  # 30 秒ぶん
    env = np.zeros(n)
    period_frames = 0.5 / frame_dt
    k = 0
    while True:
        i = int(round(k * period_frames))
        if i >= n:
            break
        env[i] = 1.0
        k += 1
    periods = beat._tempo_candidates(env, frame_dt, 60, 200)
    assert any(abs(p - 0.5) < 2 * frame_dt for p in periods), f"candidates={periods}"
