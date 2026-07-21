from scriptvedit import *

# glow Effect: split→gblur→blend=screen の発光合成
img = Object(asset("images/shape_starburst.png"))
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= glow(radius=8, intensity=0.8) & move(x=0.5, y=0.5, anchor="center")
