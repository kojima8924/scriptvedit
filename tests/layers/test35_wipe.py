from scriptvedit import *

# wipe Effect: 左→右ワイプ + move
img = Object(asset("images/shape_badge.png"))
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= wipe("left") & move(x=0.5, y=0.5, anchor="center")
