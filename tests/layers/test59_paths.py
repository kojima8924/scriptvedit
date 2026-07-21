# move_along / path_bezier / throw / look_at のパスアニメ検証
from scriptvedit import *

# move_along: 座標列に沿った移動 + 進行方向を向く回転
oni = Object(asset("images/shape_badge.png"))
path = move_along([(0.2, 0.2), (0.5, 0.8), (0.8, 0.3)])
oni.time(4) <= path
oni <= look_at(path, offset_deg=90)

# path_bezier: 3次ベジェ曲線パス
cafe = Object(asset("images/shape_figure.png"))
cafe.time(4) <= resize(sx=0.4, sy=0.4)
cafe <= path_bezier((0.1, 0.5), (0.3, 0.0), (0.7, 1.0), (0.9, 0.5))

# throw: 放物運動
pop = Object(asset("images/shape_starburst.png"))
pop.time(4) <= resize(sx=0.3, sy=0.3)
pop <= throw(0.5, -0.6, gravity=1.4, x0=0.1, y0=0.7)
