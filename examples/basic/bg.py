from scriptvedit import *

bg = Object(asset("images/bg_pattern_tiles.jpg"))
bg <= resize(sx=1, sy=1)
bg.time(6) <= move(x=0.5, y=0.5, anchor="center") & scale(lambda u: lerp(1.5, 1, u)) & fade(lambda u: u)
