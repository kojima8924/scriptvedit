from scriptvedit import *

# lambda move: x座標を0.2→0.8にアニメーション、y固定
pop = Object(asset("images/shape_starburst.png"))
pop <= resize(sx=0.3, sy=0.3)
pop.time(4) <= move(x=lambda u: lerp(0.2, 0.8, u), y=0.5, anchor="center")
