from scriptvedit import *

cafe = Object("../figure_cafe.png")
cafe <= resize(sx=0.15, sy=0.15)
cafe.time(4) <= move(from_x=0.9, from_y=0.1, to_x=0.5, to_y=0.5, anchor="center") & scale(0.5)
