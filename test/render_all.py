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


def render_test22():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test22_checkpoint.py", priority=0)
    p.render(out("test22.mp4"))


def render_test23():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test23_move_preserve.py", priority=0)
    p.render(out("test23.mp4"))


def render_test24():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test24_video_checkpoint.py", priority=0)
    p.render(out("test24.mp4"))


def render_test25():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test25_video_no_time.py", priority=0)
    p.render(out("test25.mp4"))


def render_test26():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test26_morph.py", priority=0)
    p.render(out("test26.mp4"))


def render_test27():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test27_rotate.py", priority=0)
    p.render(out("test27.mp4"))


def render_test28():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test28_rotate_to.py", priority=0)
    p.render(out("test28.mp4"))


def render_test29():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test29_web_bakeable.py", priority=0)
    p.render(out("test29.mp4"))


def render_test30():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test30_sin_scale.py", priority=0)
    p.render(out("test30.mp4"))


def render_test31():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test31_crop.py", priority=0)
    p.render(out("test31.mp4"))


def render_test32():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test32_pad.py", priority=0)
    p.render(out("test32.mp4"))


def render_test33():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test33_blur.py", priority=0)
    p.render(out("test33.mp4"))


def render_test34():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test34_eq.py", priority=0)
    p.render(out("test34.mp4"))


def render_test35():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test35_wipe.py", priority=0)
    p.render(out("test35.mp4"))


def render_test36():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test36_zoom.py", priority=0)
    p.render(out("test36.mp4"))


def render_test37():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test37_color_shift.py", priority=0)
    p.render(out("test37.mp4"))


def render_test38():
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")
    p.layer("test38_subtitle_box.py", priority=0)
    p.render(out("test38.mp4"))


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
    ("test22", render_test22),
    ("test23", render_test23),
    ("test24", render_test24),
    ("test25", render_test25),
    ("test26", render_test26),
    ("test27", render_test27),
    ("test28", render_test28),
    ("test29", render_test29),
    ("test30", render_test30),
    ("test31", render_test31),
    ("test32", render_test32),
    ("test33", render_test33),
    ("test34", render_test34),
    ("test35", render_test35),
    ("test36", render_test36),
    ("test37", render_test37),
    ("test38", render_test38),
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
