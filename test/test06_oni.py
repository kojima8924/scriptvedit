from scriptvedit import *

oni = Object("../onigiri_tenmusu.png")
oni <= resize(sx=0.4, sy=0.4)
oni.time(3) <= move(x=0.5, y=0.5, anchor="center") & scale(3.0)
