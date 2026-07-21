from scriptvedit import *

virus = Object(asset("images/banner_wide.png"))
virus <= resize(sx=0.2, sy=0.2)
virus.time(4) <= move(x=0.8, y=0.5, anchor="center") & scale(lambda u: lerp(0.5, 1, u)) & fade(lambda u: u)
