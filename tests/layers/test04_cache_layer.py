from scriptvedit import *

cafe = Object(asset("images/shape_figure.png"))
cafe <= +resize(sx=0.3, sy=0.3)
cafe.time(3) <= move(x=0.5, y=0.5, anchor="center") & scale(lambda u: lerp(0.8, 1, u))
