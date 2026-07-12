# group（一括適用）+ grid/tile（グリッド複製パターン）
from scriptvedit import *

# grid: 背景パターン生成（3x2 グリッド）
bg = Object(asset("images/pattern_teishiki_maku.png"))
bg.time(3) <= resize(sx=0.2, sy=0.2)
bg.grid(3, 2, gap=4)

# group: 複数Objを一括で同一Effect適用
a = Object(asset("images/onigiri_tenmusu.png"))
b = Object(asset("images/figure_cafe.png"))
a.time(3) <= resize(sx=0.3, sy=0.3)
b.show(3) <= resize(sx=0.3, sy=0.3)
group(a, b) <= fade(keyframes((0, 0), (0.2, 1), (1.0, 1)))
a <= move(x=0.3, y=0.5, anchor="center")
b <= move(x=0.7, y=0.5, anchor="center")
