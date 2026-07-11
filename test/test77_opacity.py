from scriptvedit import *

# opacity 定数: colorchannelmixer（高速経路）
oni = Object("../onigiri_tenmusu.png")
oni.time(2) <= opacity(0.5) & move(x=0.3, y=0.5, anchor="center")

# opacity Expr: geq による live アニメーション
cafe = Object("../figure_cafe.png")
cafe.show(2) <= (opacity(lambda u: 0.2 + 0.8 * u)
                 & move(x=0.7, y=0.5, anchor="center"))
