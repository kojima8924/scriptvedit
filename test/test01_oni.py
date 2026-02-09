from scriptvedit import *

oni = Object("../onigiri_tenmusu.png")
oni <= resize(sx=0.25, sy=0.25)
oni.time(5) <= move(from_x=0.1, from_y=0.1, to_x=0.9, to_y=0.9, anchor="center") & fade(alpha=0)
