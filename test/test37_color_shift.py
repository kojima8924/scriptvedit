from scriptvedit import *

# color_shift Effect: 色相を0→90度シフト + move
img = Object("../onigiri_tenmusu.png")
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= color_shift(hue=lambda u: u * 90) & move(x=0.5, y=0.5, anchor="center")
