from scriptvedit import *

# mask: グラデーション画像の輝度をアルファとして乗算
oni = Object(asset("images/onigiri_tenmusu.png"))
oni.time(2) <= mask(asset("images/mask_gradient.png")) & move(x=0.5, y=0.5, anchor="center")
