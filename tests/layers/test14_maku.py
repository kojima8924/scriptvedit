from scriptvedit import *

maku = Object(asset("images/pattern_curtain.png"))
maku <= resize(sx=1, sy=1)
maku.time(3) <= move(x=0.5, y=0.5, anchor="center")
anchor("curtain_done")
