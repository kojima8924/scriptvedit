from scriptvedit import *

oni = Object("../onigiri_tenmusu.png")
oni <= resize(sx=0.15, sy=0.15)
oni.time(4) <= move(from_x=0.1, from_y=0.1, to_x=0.5, to_y=0.5, anchor="center") & scale(lambda u: lerp(0.5, 1, u))
