# スナップショットテスト: dry_runで生成したffmpegコマンドをスナップショットと比較
import sys, os, json, shutil
sys.path.insert(0, "..")
from scriptvedit import *

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "snapshots")


def normalize_cmd(cmd):
    """コマンドリスト/辞書をOS非依存に正規化"""
    if isinstance(cmd, dict):
        result = {}
        for k, v in cmd.items():
            nk = k.replace("\\", "/") if isinstance(k, str) else k
            result[nk] = normalize_cmd(v)
        return result
    if isinstance(cmd, list):
        return [c.replace("\\", "/") for c in cmd]
    return cmd


def load_snapshot(name):
    path = os.path.join(SNAPSHOT_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_snapshot(name, cmd):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    path = os.path.join(SNAPSHOT_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cmd, f, indent=2, ensure_ascii=False)


def run_test(name, setup_fn, update=False):
    """スナップショットテストを実行。update=Trueならスナップショットを更新"""
    cmd = normalize_cmd(setup_fn())
    expected = load_snapshot(name)
    if expected is None or update:
        save_snapshot(name, cmd)
        print(f"  {name}: スナップショット{'更新' if expected else '作成'}")
        return True
    if cmd != expected:
        print(f"  {name}: 不一致!")
        for i, (a, b) in enumerate(zip(cmd, expected)):
            if a != b:
                print(f"    [{i}] 期待: {b}")
                print(f"    [{i}] 実際: {a}")
        if len(cmd) != len(expected):
            print(f"    長さ: 期待={len(expected)}, 実際={len(cmd)}")
        return False
    print(f"  {name}: OK")
    return True


# --- テスト定義 ---

def setup_test01():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkred")
    p.layer("test01_bg.py", priority=0)
    p.layer("test01_oni.py", priority=1)
    return p.render("test01.mp4", dry_run=True)

def setup_test02():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test02_maku.py", priority=0)
    p.layer("test02_cafe.py", priority=1)
    return p.render("test02.mp4", dry_run=True)

def setup_test03():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test03_bg.py", priority=0)
    p.layer("test03_oni.py", priority=1)
    p.layer("test03_virus.py", priority=2)
    return p.render("test03.mp4", dry_run=True)

def setup_test04():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="white")
    p.layer("test04_maku.py", priority=0)
    p.layer("test04_cache_layer.py", priority=1)
    return p.render("test04.mp4", dry_run=True)

def setup_test05():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="green")
    p.layer("test05_bg.py", priority=0)
    p.layer("test05_pop.py", priority=1)
    return p.render("test05.mp4", dry_run=True)

def setup_test06():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="olive")
    p.layer("test06_oni.py", priority=0)
    return p.render("test06.mp4", dry_run=True)

def setup_test07():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="navy")
    p.layer("test07_oni.py", priority=0)
    p.layer("test07_cafe.py", priority=1)
    p.layer("test07_virus.py", priority=2)
    return p.render("test07.mp4", dry_run=True)

def setup_test08():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkgreen")
    p.layer("test08_bg.py", priority=0)
    p.layer("test08_pop.py", priority=1)
    return p.render("test08.mp4", dry_run=True)

def setup_test09():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="gray")
    p.layer("test09_oni.py", priority=0)
    p.layer("test09_cafe.py", priority=1)
    p.layer("test09_virus.py", priority=2)
    p.layer("test09_pop.py", priority=3)
    return p.render("test09.mp4", dry_run=True)

def setup_test10():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="purple")
    p.layer("test10_maku.py", priority=0)
    p.layer("test10_cache_layer.py", priority=1)
    return p.render("test10.mp4", dry_run=True)

def setup_test11():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkblue")
    p.layer("test11_maku.py", priority=0)
    p.layer("test11_oni.py", priority=1)
    return p.render("test11.mp4", dry_run=True)

def setup_test12():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkslategray")
    p.layer("test12_sin_fade.py", priority=0)
    p.layer("test12_lambda_scale.py", priority=1)
    p.layer("test12_lambda_move.py", priority=2)
    return p.render("test12.mp4", dry_run=True)


def setup_test13():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test13_percent.py", priority=0)
    return p.render("test13.mp4", dry_run=True)

def setup_test14():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkblue")
    p.layer("test14_maku.py", priority=0, cache="make")
    p.layer("test14_oni.py", priority=1)
    result = p.render("test14.mp4", dry_run=True)
    return result

def setup_test15():
    """cache='use' テスト: ダミーキャッシュからの読み込み"""
    from scriptvedit import _layer_cache_paths
    # まずProjectを作って正しいキャッシュパスを計算
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkblue")
    dummy_webm, dummy_json = _layer_cache_paths("test14_maku.py", p)
    os.makedirs(os.path.dirname(dummy_webm), exist_ok=True)
    # ダミーwebmファイル（空でよい、dry_runなので実行されない）
    with open(dummy_webm, "wb") as f:
        f.write(b"\x00")
    # anchors.json
    with open(dummy_json, "w", encoding="utf-8") as f:
        json.dump({"duration": 3.0, "anchors": {"curtain_done": 3.0}}, f)
    try:
        p2 = Project()
        p2.configure(width=1280, height=720, fps=30, background_color="darkblue")
        p2.layer("test14_maku.py", priority=0, cache="use")
        p2.layer("test14_oni.py", priority=1)
        return p2.render("test15.mp4", dry_run=True)
    finally:
        # ダミーファイル削除
        if os.path.exists(dummy_webm):
            os.unlink(dummy_webm)
        if os.path.exists(dummy_json):
            os.unlink(dummy_json)
        # クリーンアップ
        parent = os.path.dirname(dummy_webm)
        if os.path.exists(parent) and not os.listdir(parent):
            os.rmdir(parent)


def setup_test16():
    """音声ミックステスト: BGM(mp3) + 画像+SE"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test16_bgm.py", priority=0)
    p.layer("test16_oni.py", priority=1)
    return p.render("test16.mp4", dry_run=True)

def setup_test17():
    """AV splitテスト: 音声なし動画 + 音声のみ"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkgreen")
    p.layer("test17_video_split.py", priority=0)
    p.layer("test17_audio.py", priority=1)
    return p.render("test17.mp4", dry_run=True)

def setup_test18():
    """length()テスト: ffprobeで取得した長さを使用"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="gray")
    p.layer("test18_length.py", priority=0)
    return p.render("test18.mp4", dry_run=True)


def setup_test19():
    """webクリップテスト: HTML→透明webm→合成"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test19_web.py", priority=0)
    return p.render("test19.mp4", dry_run=True)


def setup_test20():
    """字幕/吹き出しテスト: subtitle+bubble+背景合成"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test20_bg.py", priority=0)
    p.layer("test20_subtitles.py", priority=1)
    p.layer("test20_bubble.py", priority=2)
    return p.render("test20.mp4", dry_run=True)


def setup_test21():
    """図解テスト: diagram SVG図形+from/toアニメ+画像合成"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkslategray")
    p.layer("test21_diagram.py", priority=0)
    p.layer("test21_overlay.py", priority=1)
    return p.render("test21.mp4", dry_run=True)


def setup_test22():
    """チェックポイントキャッシュテスト"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test22_checkpoint.py", priority=0)
    return p.render("test22.mp4", dry_run=True)


def setup_test23():
    """move保存テスト: resize(force) + move + scaleでmoveが消えないことを確認"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test23_move_preserve.py", priority=0)
    return p.render("test23.mp4", dry_run=True)


def setup_test24():
    """video checkpointテスト: 動画のtransform-only → .webm拡張子"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test24_video_checkpoint.py", priority=0)
    return p.render("test24.mp4", dry_run=True)


def setup_test25():
    """video + transform-only + time未指定 → obj.length()でduration補完"""
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test25_video_no_time.py", priority=0)
    return p.render("test25.mp4", dry_run=True)


ALL_TESTS = [
    ("test01", setup_test01),
    ("test02", setup_test02),
    ("test03", setup_test03),
    ("test04", setup_test04),
    ("test05", setup_test05),
    ("test06", setup_test06),
    ("test07", setup_test07),
    ("test08", setup_test08),
    ("test09", setup_test09),
    ("test10", setup_test10),
    ("test11", setup_test11),
    ("test12", setup_test12),
    ("test13", setup_test13),
    ("test14", setup_test14),
    ("test15", setup_test15),
    ("test16", setup_test16),
    ("test17", setup_test17),
    ("test18", setup_test18),
    ("test19", setup_test19),
    ("test20", setup_test20),
    ("test21", setup_test21),
    ("test22", setup_test22),
    ("test23", setup_test23),
    ("test24", setup_test24),
    ("test25", setup_test25),
]


if __name__ == "__main__":
    update = "--update" in sys.argv
    print("スナップショットテスト" + (" (更新モード)" if update else ""))
    passed = 0
    failed = 0
    for name, fn in ALL_TESTS:
        if run_test(name, fn, update=update):
            passed += 1
        else:
            failed += 1
    print(f"\n結果: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
