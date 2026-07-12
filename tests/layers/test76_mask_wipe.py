from scriptvedit import *

# mask_wipe: グラデーション輝度をしきい値に使うワイプ（既定は線形進行）
oni = Object(asset("images/onigiri_tenmusu.png"))
oni.time(3) <= mask_wipe(asset("images/mask_gradient.png")) & move(x=0.35, y=0.5, anchor="center")

# 円形マスク + イージング進行（Expr/lambda live）
cafe = Object(asset("images/figure_cafe.png"))
cafe.show(3) <= (mask_wipe(asset("images/mask_circle.png"), progress=lambda u: u * u)
                 & move(x=0.7, y=0.5, anchor="center"))
