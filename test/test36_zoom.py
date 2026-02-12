from scriptvedit import *

# zoom Effect: 0.5倍→1.5倍ズーム + move
img = Object("../onigiri_tenmusu.png")
img <= resize(sx=0.3, sy=0.3)
img.time(2) <= zoom(from_value=0.5, to_value=1.5) & move(x=0.5, y=0.5, anchor="center")
