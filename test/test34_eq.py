from scriptvedit import *

# eq Transform: 色調補正 + move
img = Object("../onigiri_tenmusu.png")
img <= resize(sx=0.5, sy=0.5)
img <= eq(brightness=0.2, contrast=1.2)
img.time(2) <= move(x=0.5, y=0.5, anchor="center")
