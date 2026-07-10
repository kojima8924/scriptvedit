import os

from scriptvedit import *

if __name__ == "__main__":
    # レイヤーファイルと素材（bg_pattern_ishigaki.jpg 等）は cwd 相対で解決されるため、
    # cwd をスクリプト位置に合わせてどこから実行しても動くようにする
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")

    p.layer("bg.py", priority=0)
    p.layer("onigiri.py", priority=1)

    p.render("output.mp4")
