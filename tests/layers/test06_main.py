# テスト06: 大きいscale(3.0→1.0)
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="olive")
p.layer("test06_oni.py", priority=0)
p.render("test06.mp4")
