from scriptvedit import *

# カフェイラスト: 左→右へ波打ちながら移動
cafe = Object(asset("images/figure_cafe.png"))
# 旧API: resize(sy=0.5) = 画面高さの50% = 540px, 元1130x1130
cafe <= resize(sx=0.478, sy=0.478)
cafe.time(6) <= move(
    x=lambda u: 0.9 * u,
    y=lambda u: 0.5 + 0.2 * sin(u * 4 * PI),
    anchor="center",
)
