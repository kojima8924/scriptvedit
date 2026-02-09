# テスト11: anchor/pause/until テスト（クロスレイヤー同期）
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="darkblue")
p.layer("test11_maku.py", priority=0)
p.layer("test11_oni.py", priority=1)
p.render("test11.mp4")
