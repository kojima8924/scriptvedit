from scriptvedit import *

# 本編: おにぎり2秒 → カフェ2秒
oni = Object(asset("images/onigiri_tenmusu.png"))
oni.time(2) <= move(x=0.5, y=0.5, anchor="center")
cafe = Object(asset("images/figure_cafe.png"))
cafe.time(2) <= move(x=0.5, y=0.5, anchor="center")

# progress_bar: 動画全体の進行バー（duration不要・全体に重なる）
progress_bar(height=8, color="orange", bg="white@0.15", y=1.0)
