from scriptvedit import *

img1 = Object(asset("images/shape_badge.png"))
img2 = Object(asset("images/shape_figure.png"))
img1.time(3) <= morph_to(img2)
