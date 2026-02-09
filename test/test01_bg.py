from scriptvedit import *

bg = Object("../bg_pattern_ishigaki.jpg")
bg <= resize(sx=2, sy=2)
bg.time(5) <= move(x=0.5, y=0.5, anchor="center") & scale(1.3)
