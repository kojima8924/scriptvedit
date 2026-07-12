# assemble_from: source の粒子が集合して画像になる
from scriptvedit import *

src = Object(asset("images/figure_cafe.png"))  # 集合元（消費される）
result = Object(asset("images/figure_cafe.png"))
result.time(2) <= assemble_from(src, speed=150, max_pixels=800, seed=3)
result <= move(x=0.5, y=0.5, anchor="center")
