from scriptvedit import *

# mask: グラデーション画像の輝度をアルファとして乗算
oni = Object("../onigiri_tenmusu.png")
oni.time(2) <= mask("mask_gradient.png") & move(x=0.5, y=0.5, anchor="center")
