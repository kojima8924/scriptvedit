from scriptvedit import *

cafe = Object("../figure_cafe.png")
cafe <= resize(sx=0.2, sy=0.2)
cafe.time(4) <= move(x=0.5, y=0.5, anchor="center") & scale(0.5) & fade(alpha=0)
