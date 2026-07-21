from scriptvedit import *

badge = Object(asset("images/shape_badge.png"))
badge <= resize(sx=0.3, sy=0.3)
badge.time(6) <= move(x=0.3, y=0.7, anchor="center") & scale(lambda u: lerp(0.5, 1, u)) & fade(lambda u: u)
