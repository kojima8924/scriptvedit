from scriptvedit import *
bg = Object("../bg_pattern_ishigaki.jpg")
bg.time(8) <= move(x=0.5, y=0.5, anchor="center") & scale(lambda u: lerp(1.0, 1.1, u))
