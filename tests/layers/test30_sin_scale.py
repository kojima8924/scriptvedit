from scriptvedit import *
obj = Object(asset("images/shape_badge.png"))
obj <= resize(sx=0.3, sy=0.3)
obj.time(3) <= move(x=0.5, y=0.5, anchor="center") & scale(lambda u: 1 + 0.5 * sin(u * PI))
