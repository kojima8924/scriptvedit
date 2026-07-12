# テスト01: 背景+おにぎり斜め移動
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="darkred")
p.layer("test01_bg.py", priority=0)
p.layer("test01_oni.py", priority=1)
p.render("test01.mp4")
