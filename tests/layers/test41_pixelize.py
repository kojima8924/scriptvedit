from scriptvedit import *

# pixelize Effect: モザイク（定数サイズ）
img = Object(asset("images/shape_badge.png"))
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= pixelize(24) & move(x=0.5, y=0.5, anchor="center")
