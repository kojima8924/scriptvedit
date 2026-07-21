from scriptvedit import *

pop = Object(asset("images/shape_starburst.png"))
pop <= resize(sx=0.3, sy=0.3)
pop.time(5) <= move(from_x=0.0, from_y=0.5, to_x=1.0, to_y=0.5, anchor="center") & fade(lambda u: u)
