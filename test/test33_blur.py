from scriptvedit import *

# blur Transform: ぼかし + resize + move
img = Object("../onigiri_tenmusu.png")
img <= resize(sx=0.5, sy=0.5)
img <= blur(10)
img.time(2) <= move(x=0.5, y=0.5, anchor="center")
