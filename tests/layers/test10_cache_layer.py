from scriptvedit import *

oni = Object(asset("images/onigiri_tenmusu.png"))
oni <= +resize(sx=0.4, sy=0.4)
oni.time(5) <= move(x=0.5, y=0.5, anchor="center") & scale(lambda u: lerp(0.8, 1, u)) & fade(lambda u: u)
