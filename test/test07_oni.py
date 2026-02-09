from scriptvedit import *

oni = Object("../onigiri_tenmusu.png")
oni <= resize(sx=0.2, sy=0.2)
oni.time(4) <= move(x=0.2, y=0.5, anchor="center") & scale(0.5) & fade(alpha=0)
