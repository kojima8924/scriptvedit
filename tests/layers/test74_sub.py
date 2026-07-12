from scriptvedit import *

# from_project のサブProject用レイヤー: おにぎりが左→右へ移動
oni = Object(asset("images/onigiri_tenmusu.png"))
oni <= resize(sx=0.5, sy=0.5)
oni.time(2) <= move(from_x=0.2, to_x=0.8, y=0.5, anchor="center")
