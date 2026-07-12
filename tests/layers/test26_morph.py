from scriptvedit import *

img1 = Object(asset("images/onigiri_tenmusu.png"))
img2 = Object(asset("images/figure_cafe.png"))
img1.time(3) <= morph_to(img2)
