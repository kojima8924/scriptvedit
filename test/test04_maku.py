from scriptvedit import *

maku = Object("../pattern_teishiki_maku.png")
maku <= resize(sx=3, sy=3)
maku.time(3) <= move(x=0.5, y=0.5, anchor="center")
