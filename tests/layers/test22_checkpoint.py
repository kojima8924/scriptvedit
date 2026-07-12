from scriptvedit import *

obj = Object(asset("images/onigiri_tenmusu.png"))
obj <= +resize(sx=0.3, sy=0.3)
obj.time(3) <= move(x=0.5, y=0.5, anchor="center") & scale(lambda u: lerp(0.8, 1, u))
