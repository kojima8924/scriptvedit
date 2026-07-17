# -*- coding: utf-8 -*-
"""issue #13 P2-18: 数値入力の検証（configure / scriptvedit new / watch / 共通validator）"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from scriptvedit import Project, glow  # noqa: E402
from scriptvedit.cli import _main  # noqa: E402
from scriptvedit.scaffold import new_project  # noqa: E402


# --- configure() の検証 ---

def test_configure_width_zero():
    """configure(width=0) → ValueError（FFmpeg の s=0x720 で落ちる前に弾く）"""
    p = Project()
    with pytest.raises(ValueError, match="width は正の整数"):
        p.configure(width=0)


def test_configure_height_negative():
    """configure(height=-720) → ValueError"""
    p = Project()
    with pytest.raises(ValueError, match="height は正の整数"):
        p.configure(height=-720)


def test_configure_width_non_int():
    """configure(width=1280.5) → ValueError（整数のみ）"""
    p = Project()
    with pytest.raises(ValueError, match="width は正の整数"):
        p.configure(width=1280.5)


def test_configure_fps_nan():
    """configure(fps=NaN) → ValueError"""
    p = Project()
    with pytest.raises(ValueError, match="fps は正の有限数"):
        p.configure(fps=float("nan"))


def test_configure_fps_inf():
    """configure(fps=inf) → ValueError"""
    p = Project()
    with pytest.raises(ValueError, match="fps は正の有限数"):
        p.configure(fps=float("inf"))


def test_configure_fps_zero():
    """configure(fps=0) → ValueError"""
    p = Project()
    with pytest.raises(ValueError, match="fps は正の有限数"):
        p.configure(fps=0)


def test_configure_duration_negative():
    """configure(duration=-1) → ValueError"""
    p = Project()
    with pytest.raises(ValueError, match="duration は正の有限数"):
        p.configure(duration=-1)


def test_configure_duration_nan():
    """configure(duration=NaN) → ValueError"""
    p = Project()
    with pytest.raises(ValueError, match="duration は正の有限数"):
        p.configure(duration=float("nan"))


def test_configure_valid_values():
    """正常値は従来どおり通る（duration=None も可）"""
    p = Project()
    p.configure(width=1280, height=720, fps=29.97, duration=None)
    assert p.width == 1280 and p.height == 720 and p.fps == 29.97
    p.configure(duration=12.5)
    assert p.duration == 12.5


# --- 共通validator（Effect パラメータ）の NaN/Infinity 拒否 ---

def test_effect_param_rejects_nan():
    """_require_number 経由のパラメータに NaN → ValueError（従来は範囲比較をすり抜けた）"""
    with pytest.raises(ValueError, match="NaN/Infinity"):
        glow(radius=math.nan)


def test_method_param_rejects_inf():
    """上限なしパラメータ（marker の time）に Infinity → ValueError"""
    p = Project()
    with pytest.raises(ValueError, match="NaN/Infinity"):
        p.marker(math.inf, "章1")


# --- scriptvedit new の検証 ---

def test_new_width_zero_cli(tmp_path, capsys):
    """scriptvedit new --width 0 → rc=2 で1行診断"""
    rc = _main(["new", str(tmp_path / "proj0"), "--width", "0"])
    assert rc == 2
    err = capsys.readouterr().err.strip()
    assert "--width は正の整数" in err
    assert "\n" not in err  # 1行診断（traceback ではない）
    assert not os.path.exists(tmp_path / "proj0" / "main.py")


def test_new_fps_negative_cli(tmp_path, capsys):
    """scriptvedit new --fps -1 → rc=2"""
    rc = _main(["new", str(tmp_path / "projf"), "--fps", "-1"])
    assert rc == 2
    assert "--fps は正の整数" in capsys.readouterr().err


def test_new_project_height_zero_direct(tmp_path):
    """new_project(height=0) 直呼び → ValueError"""
    with pytest.raises(ValueError, match="--height は正の整数"):
        new_project(str(tmp_path / "projh"), height=0, quiet=True)


def test_new_valid_cli(tmp_path):
    """正常値は従来どおり生成できる"""
    rc = _main(["new", str(tmp_path / "ok"), "--width", "640", "--height", "360"])
    assert rc == 0
    main_py = open(tmp_path / "ok" / "main.py", encoding="utf-8").read()
    assert "width=640" in main_py and "height=360" in main_py


# --- watch の検証 ---

def test_watch_missing_script_cli(tmp_path, capsys):
    """watch 不存在スクリプト → rc=2 で1行診断（起動前）"""
    missing = str(tmp_path / "nai.py")
    rc = _main(["watch", missing])
    assert rc == 2
    err = capsys.readouterr().err.strip()
    assert "スクリプトが見つかりません" in err
    assert "\n" not in err


def test_watch_negative_interval_cli(tmp_path, capsys):
    """watch --interval -1 → rc=2（初回実行前に弾く）"""
    script = tmp_path / "noop.py"
    script.write_text("raise SystemExit('実行されてはいけない')\n", encoding="utf-8")
    rc = _main(["watch", str(script), "--interval", "-1"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "interval は正の有限数" in captured.err
    assert "[watch] 実行" not in captured.out  # 初回実行前に止まる


def test_watch_zero_interval_cli(tmp_path, capsys):
    """watch --interval 0 → rc=2"""
    script = tmp_path / "noop.py"
    script.write_text("pass\n", encoding="utf-8")
    rc = _main(["watch", str(script), "--interval", "0"])
    assert rc == 2
    assert "interval は正の有限数" in capsys.readouterr().err


def test_watch_bad_max_cycles_cli(tmp_path, capsys):
    """watch --max-cycles 0 → rc=2"""
    script = tmp_path / "noop.py"
    script.write_text("pass\n", encoding="utf-8")
    rc = _main(["watch", str(script), "--max-cycles", "0"])
    assert rc == 2
    assert "max_cycles は1以上の整数" in capsys.readouterr().err


def test_watch_valid_runs(tmp_path, capsys):
    """正常値: 実在スクリプト + 正interval + max_cycles=1 で正常終了"""
    script = tmp_path / "noop.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    rc = _main(["watch", str(script), "--interval", "0.01", "--max-cycles", "1"])
    assert rc == 0
    assert "max_cycles 到達" in capsys.readouterr().out


# --- cache の検証 ---

def test_cache_negative_keep_days_cli(tmp_path, capsys):
    """cache --gc --keep-days -1 → rc=2"""
    rc = _main(["cache", "--gc", "--keep-days", "-1", "--dir", str(tmp_path / "__cache__")])
    assert rc == 2
    assert "--keep-days は0以上の有限数" in capsys.readouterr().err
