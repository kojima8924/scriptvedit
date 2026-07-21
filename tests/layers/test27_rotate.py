from scriptvedit import *

# rotate Transform: 画像を30度回転（静的）
img = Object(asset("images/shape_badge.png"))
img <= rotate(deg=30)
img.time(2) <= move(x=0.5, y=0.5, anchor="center")
