# テスト09: 4レイヤー 四隅から中央へ集合
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="gray")
p.layer("test09_oni.py", priority=0)
p.layer("test09_cafe.py", priority=1)
p.layer("test09_virus.py", priority=2)
p.layer("test09_pop.py", priority=3)
p.render("test09.mp4")
