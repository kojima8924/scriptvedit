from scriptvedit import *

# 背景: 石垣パターン
bg = Object(asset("images/bg_pattern_tiles.jpg"))
bg.show(3) <= move(x=0.5, y=0.5, anchor="center")

# blend_mode: screen合成（maskedmerge経路）
oni = Object(asset("images/shape_badge.png"))
oni.show(3) <= blend_mode("screen") & move(x=0.35, y=0.5, anchor="center")

# blend_mode: multiply合成 + エイリアス 'add' → addition の検証は test_errors 側
cafe = Object(asset("images/shape_figure.png"))
cafe.time(3) <= blend_mode("multiply") & move(x=0.7, y=0.5, anchor="center")
