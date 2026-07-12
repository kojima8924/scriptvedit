# テスト12: Expr機能検証（sin波フェード、lambda scale/move）
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="darkslategray")
p.layer("test12_sin_fade.py", priority=0)
p.layer("test12_lambda_scale.py", priority=1)
p.layer("test12_lambda_move.py", priority=2)
p.render("test12.mp4")
