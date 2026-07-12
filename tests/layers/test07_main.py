# テスト07: 3レイヤー横並び（プリセット的に同じEffect）
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="navy")
p.layer("test07_oni.py", priority=0)
p.layer("test07_cafe.py", priority=1)
p.layer("test07_virus.py", priority=2)
p.render("test07.mp4")
