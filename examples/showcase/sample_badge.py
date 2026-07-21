from scriptvedit import *

# おにぎり: 斜め移動+正弦波、縮小、4回転
oni = Object(asset("images/shape_badge.png"))
oni.time(6) <= move(
    x=lambda u: 0.9 * u - 0.3 * (1 - u),
    y=lambda u: 0.5 + 0.2 * sin(u * 4 * PI) - 0.3 * (1 - u),
    anchor="center",
# 旧API: scale(sy=...)は画面基準 → SVE2画像基準に変換: 1080/800=1.35倍
) & scale(lambda u: 1.35 * (0.3 * (1 - u ** 0.5) + 0.1)) & rotate_to(from_deg=0, to_deg=1440)
