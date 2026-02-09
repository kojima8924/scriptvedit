# テスト03: 3レイヤーmoveアニメ（おにぎり左→右、ウイルス右→左）
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="black")
p.layer("test03_bg.py", priority=0)
p.layer("test03_oni.py", priority=1)
p.layer("test03_virus.py", priority=2)
p.render("test03.mp4")
