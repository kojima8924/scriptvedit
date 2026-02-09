# テスト05: 静的表示（Effectなし）
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="green")
p.layer("test05_bg.py", priority=0)
p.layer("test05_pop.py", priority=1)
p.render("test05.mp4")
