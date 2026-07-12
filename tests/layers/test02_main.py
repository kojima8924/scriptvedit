# テスト02: 定式幕+カフェ（scale+fade）
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="black")
p.layer("test02_maku.py", priority=0)
p.layer("test02_cafe.py", priority=1)
p.render("test02.mp4")
