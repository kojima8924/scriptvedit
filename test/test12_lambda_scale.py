from scriptvedit import *

# lambda scale: 0.5→1.0にスケールアニメーション
cafe = Object("../figure_cafe.png")
cafe <= resize(sx=0.3, sy=0.3)
cafe.time(4) <= move(x=0.5, y=0.5, anchor="center") & scale(lambda u: lerp(0.5, 1, u))
