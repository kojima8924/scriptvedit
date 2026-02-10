# 全テスト動画の実レンダリング
# 出力先: test/output/ ディレクトリ
import sys, os, time, shutil
sys.path.insert(0, "..")
from scriptvedit import *

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def out(name):
    return os.path.join(OUTPUT_DIR, name)


def render_test01():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkred")
    p.layer("test01_bg.py", priority=0)
    p.layer("test01_oni.py", priority=1)
    p.render(out("test01.mp4"))


def render_test02():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test02_maku.py", priority=0)
    p.layer("test02_cafe.py", priority=1)
    p.render(out("test02.mp4"))


def render_test03():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test03_bg.py", priority=0)
    p.layer("test03_oni.py", priority=1)
    p.layer("test03_virus.py", priority=2)
    p.render(out("test03.mp4"))


def render_test04():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="white")
    p.layer("test04_maku.py", priority=0)
    p.layer("test04_cache_layer.py", priority=1)
    p.render(out("test04.mp4"))


def render_test05():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="green")
    p.layer("test05_bg.py", priority=0)
    p.layer("test05_pop.py", priority=1)
    p.render(out("test05.mp4"))


def render_test06():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="olive")
    p.layer("test06_oni.py", priority=0)
    p.render(out("test06.mp4"))


def render_test07():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="navy")
    p.layer("test07_oni.py", priority=0)
    p.layer("test07_cafe.py", priority=1)
    p.layer("test07_virus.py", priority=2)
    p.render(out("test07.mp4"))


def render_test08():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkgreen")
    p.layer("test08_bg.py", priority=0)
    p.layer("test08_pop.py", priority=1)
    p.render(out("test08.mp4"))


def render_test09():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="gray")
    p.layer("test09_oni.py", priority=0)
    p.layer("test09_cafe.py", priority=1)
    p.layer("test09_virus.py", priority=2)
    p.layer("test09_pop.py", priority=3)
    p.render(out("test09.mp4"))


def render_test10():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="purple")
    p.layer("test10_maku.py", priority=0)
    p.layer("test10_cache_layer.py", priority=1)
    p.render(out("test10.mp4"))


def render_test11():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkblue")
    p.layer("test11_maku.py", priority=0)
    p.layer("test11_oni.py", priority=1)
    p.render(out("test11.mp4"))


def render_test12():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkslategray")
    p.layer("test12_sin_fade.py", priority=0)
    p.layer("test12_lambda_scale.py", priority=1)
    p.layer("test12_lambda_move.py", priority=2)
    p.render(out("test12.mp4"))


def render_test13():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test13_percent.py", priority=0)
    p.render(out("test13.mp4"))


def render_test14():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkblue")
    p.layer("test14_maku.py", priority=0, cache="make")
    p.layer("test14_oni.py", priority=1)
    p.render(out("test14.mp4"))


def render_test15():
    """test14のキャッシュを利用して描画"""
    # test14で生成されたキャッシュがあるはず
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkblue")
    p.layer("test14_maku.py", priority=0, cache="use")
    p.layer("test14_oni.py", priority=1)
    p.render(out("test15.mp4"))


def render_test16():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test16_bgm.py", priority=0)
    p.layer("test16_oni.py", priority=1)
    p.render(out("test16.mp4"))


def render_test17():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkgreen")
    p.layer("test17_video_split.py", priority=0)
    p.layer("test17_audio.py", priority=1)
    p.render(out("test17.mp4"))


def render_test18():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="gray")
    p.layer("test18_length.py", priority=0)
    p.render(out("test18.mp4"))


def render_test19():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test19_web.py", priority=0)
    p.render(out("test19.mp4"))


def render_test20():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test20_bg.py", priority=0)
    p.layer("test20_subtitles.py", priority=1)
    p.layer("test20_bubble.py", priority=2)
    p.render(out("test20.mp4"))


def render_test21():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="darkslategray")
    p.layer("test21_diagram.py", priority=0)
    p.layer("test21_overlay.py", priority=1)
    p.render(out("test21.mp4"))


ALL_RENDERS = [
    ("test01", render_test01),
    ("test02", render_test02),
    ("test03", render_test03),
    ("test04", render_test04),
    ("test05", render_test05),
    ("test06", render_test06),
    ("test07", render_test07),
    ("test08", render_test08),
    ("test09", render_test09),
    ("test10", render_test10),
    ("test11", render_test11),
    ("test12", render_test12),
    ("test13", render_test13),
    ("test14", render_test14),
    ("test15", render_test15),
    ("test16", render_test16),
    ("test17", render_test17),
    ("test18", render_test18),
    ("test19", render_test19),
    ("test20", render_test20),
    ("test21", render_test21),
]


if __name__ == "__main__":
    # 引数で特定テストだけ実行可能: python render_all.py test19 test20 test21
    targets = sys.argv[1:] if len(sys.argv) > 1 else None
    print(f"=== 動画レンダリング → {OUTPUT_DIR} ===\n")
    ok = 0
    fail = 0
    for name, fn in ALL_RENDERS:
        if targets and name not in targets:
            continue
        t0 = time.time()
        try:
            print(f"--- {name} ---")
            fn()
            elapsed = time.time() - t0
            print(f"  OK ({elapsed:.1f}s)\n")
            ok += 1
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  FAIL ({elapsed:.1f}s): {e}\n")
            fail += 1
    print(f"=== 結果: {ok} OK, {fail} FAIL ===")
    if fail:
        sys.exit(1)
