from scriptvedit import *

pop = Object(asset("images/shape_starburst.png"))
pop <= resize(sx=0.5, sy=0.5)
pop.time(2) <= move(x=0.5, y=0.5, anchor="center")
