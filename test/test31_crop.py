from scriptvedit import *

# crop Transform: 画像の一部を切り出し + move
img = Object("../onigiri_tenmusu.png")
img <= crop(x=100, y=50, w=400, h=300)
img.time(2) <= move(x=0.5, y=0.5, anchor="center")
