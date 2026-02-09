from scriptvedit import *

bg = Object("../bg_pattern_ishigaki.jpg")
bg <= resize(sx=1, sy=1)
bg.time(5) <= move(x=0.5, y=0.5, anchor="center") & scale(1.2) & fade(alpha=0)
