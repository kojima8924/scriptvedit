from scriptvedit import *

oni = Object("../onigiri_tenmusu.png")
oni <= resize(sx=0.2, sy=0.2)
oni.time(5) <= move(from_x=0.0, from_y=0.5, to_x=1.0, to_y=0.5, anchor="center")
