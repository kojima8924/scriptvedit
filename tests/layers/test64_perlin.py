# perlin ノイズによる手ブレカメラ風の揺れ（move の x/y に加算）
from scriptvedit import *

oni = Object(asset("images/onigiri_tenmusu.png"))
oni.time(4) <= resize(sx=0.5, sy=0.5)
# 中央 + perlin ノイズで微小な揺れ
oni <= move(
    x=lambda u: 0.5 + perlin(u, octaves=3, seed=11, amplitude=0.03),
    y=lambda u: 0.5 + perlin(u, octaves=3, seed=22, amplitude=0.03),
    anchor="center",
)
