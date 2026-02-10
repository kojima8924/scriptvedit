# エラーケーステスト: 各種エラー条件の自動検証
import sys, os, tempfile
sys.path.insert(0, "..")
from scriptvedit import _resolve_param, Project, P


def test_math_sin_in_lambda():
    """lambda内でmath.sinを使用 → TypeErrorかつ案内メッセージ"""
    import math
    try:
        _resolve_param(lambda u: math.sin(u))
        return False, "例外が発生しませんでした"
    except TypeError as e:
        msg = str(e)
        if "scriptvedit" in msg and "sin" in msg:
            return True, msg.split('\n')[0]
        return False, f"メッセージが不適切: {msg}"


def test_undefined_anchor():
    """未定義アンカー参照 → RuntimeError"""
    layer_code = (
        'from scriptvedit import *\n'
        'pause.until("nonexistent")\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj.time(1) <= move(x=0.5, y=0.5, anchor="center")\n'
    )
    temp_path = os.path.join(os.path.dirname(__file__), "_tmp_err_undef.py")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(layer_code)
        p = Project()
        p.configure(width=320, height=240, fps=1, background_color="black")
        p.layer(temp_path, priority=0)
        p.render("_tmp_err.mp4", dry_run=True)
        return False, "例外が発生しませんでした"
    except RuntimeError as e:
        msg = str(e)
        if "nonexistent" in msg and "pause.until" in msg:
            return True, msg.split('\n')[0]
        return False, f"メッセージが不適切: {msg}"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_same_anchor_different_files():
    """異ファイル間で同名アンカー定義 → RuntimeError"""
    layer1_code = (
        'from scriptvedit import *\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj.time(1) <= move(x=0.5, y=0.5, anchor="center")\n'
        'anchor("my_anchor")\n'
    )
    layer2_code = (
        'from scriptvedit import *\n'
        'anchor("my_anchor")\n'
        'obj = Object("../onigiri_tenmusu.png")\n'
        'obj.time(1) <= move(x=0.5, y=0.5, anchor="center")\n'
    )
    temp1 = os.path.join(os.path.dirname(__file__), "_tmp_err_dup1.py")
    temp2 = os.path.join(os.path.dirname(__file__), "_tmp_err_dup2.py")
    try:
        with open(temp1, "w", encoding="utf-8") as f:
            f.write(layer1_code)
        with open(temp2, "w", encoding="utf-8") as f:
            f.write(layer2_code)
        p = Project()
        p.configure(width=320, height=240, fps=1, background_color="black")
        p.layer(temp1, priority=0)
        p.layer(temp2, priority=1)
        p.render("_tmp_err.mp4", dry_run=True)
        return False, "例外が発生しませんでした"
    except RuntimeError as e:
        msg = str(e)
        if "my_anchor" in msg and "再定義は禁止" in msg:
            return True, msg.split('\n')[0]
        return False, f"メッセージが不適切: {msg}"
    finally:
        for f in [temp1, temp2]:
            if os.path.exists(f):
                os.unlink(f)


def test_configure_typo():
    """configure()のtypo → ValueError"""
    p = Project()
    try:
        p.configure(widht=1280)
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "widht" in msg and "width" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_percent_value():
    """50%P == 0.5 の確認"""
    result = 50%P
    if result == 0.5:
        return True, f"50%P = {result}"
    return False, f"50%P = {result} (期待: 0.5)"


def test_cache_invalid():
    """cache='invalid' → ValueError"""
    p = Project()
    try:
        p.layer("dummy.py", cache="invalid")
        return False, "例外が発生しませんでした"
    except ValueError as e:
        msg = str(e)
        if "invalid" in msg:
            return True, msg
        return False, f"メッセージが不適切: {msg}"


def test_cache_use_no_file():
    """cache='use' でファイル不在 → FileNotFoundError"""
    p = Project()
    p.configure(width=320, height=240, fps=1, background_color="black")
    p.layer("nonexistent_layer.py", cache="use")
    try:
        p.render("_tmp.mp4", dry_run=True)
        return False, "例外が発生しませんでした"
    except FileNotFoundError as e:
        msg = str(e)
        if "キャッシュファイルが見つかりません" in msg:
            return True, msg.split('\n')[0]
        return False, f"メッセージが不適切: {msg}"


ALL_TESTS = [
    ("math.sin in lambda", test_math_sin_in_lambda),
    ("未定義アンカー参照", test_undefined_anchor),
    ("同名アンカー異ファイル", test_same_anchor_different_files),
    ("configure typo", test_configure_typo),
    ("50%P == 0.5", test_percent_value),
    ("cache='invalid'", test_cache_invalid),
    ("cache='use' ファイル不在", test_cache_use_no_file),
]


if __name__ == "__main__":
    print("エラーケーステスト")
    passed = 0
    failed = 0
    for name, fn in ALL_TESTS:
        ok, msg = fn()
        status = "OK" if ok else "FAIL"
        print(f"  {name}: {status} - {msg[:80]}")
        if ok:
            passed += 1
        else:
            failed += 1
    print(f"\n結果: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
