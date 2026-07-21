from scriptvedit import *

# drop_shadow Effect: split→色付け+gblur→overlay のドロップシャドウ
img = Object(asset("images/shape_badge.png"))
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= drop_shadow(dx=8, dy=8, blur=6, color="black", opacity=0.6) & move(x=0.5, y=0.5, anchor="center")
