from scriptvedit import *

# perspective_warp Effect: 4隅指定の透視変形（sense=destination）
img = Object(asset("images/shape_badge.png"))
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= perspective_warp(0, 0, 300, 50, 0, 200, 300, 180) & move(x=0.5, y=0.5, anchor="center")
