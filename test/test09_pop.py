from scriptvedit import *

pop = Object("../pop_shinsyakaijin_ganbare.png")
pop <= resize(sx=0.15, sy=0.15)
pop.time(4) <= move(from_x=0.9, from_y=0.9, to_x=0.5, to_y=0.5, anchor="center") & scale(0.5)
