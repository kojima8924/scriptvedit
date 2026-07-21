from scriptvedit import *

# vignette Effect: 時間とともに強くなるビネット（strength=Expr → eval=frame）
img = Object(asset("images/bg_pattern_tiles.jpg"))
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= vignette(strength=lambda u: u) & move(x=0.5, y=0.5, anchor="center")
