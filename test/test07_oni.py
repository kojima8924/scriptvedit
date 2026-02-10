from scriptvedit import *

oni = Object("../onigiri_tenmusu.png")
oni <= resize(sx=0.2, sy=0.2)
oni.time(4) <= move(x=0.2, y=0.5, anchor="center") & scale(lambda u: lerp(0.5, 1, u)) & fade(lambda u: u)
