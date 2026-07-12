# テスト08: from/toアニメーション（左から右へ移動）
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="darkgreen")
p.layer("test08_bg.py", priority=0)
p.layer("test08_pop.py", priority=1)
p.render("test08.mp4")
