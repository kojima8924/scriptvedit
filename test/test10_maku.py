from scriptvedit import *

maku = Object("../pattern_teishiki_maku.png")
maku <= resize(sx=1, sy=1)
maku.time(5) <= move(x=0.5, y=0.5, anchor="center") & fade(lambda u: u)
