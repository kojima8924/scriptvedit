from scriptvedit import *

bg = Object(asset("images/bg_pattern_tiles.jpg"))
bg <= resize(sx=2, sy=2)
bg.time(2) <= move(x=0.5, y=0.5, anchor="center")
