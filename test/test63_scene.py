# scene: シーンを時間軸上に順次配置（シーン相対時刻）
from scriptvedit import *

with scene("intro", 3):
    oni = Object("../onigiri_tenmusu.png")
    oni.time(2) <= move(x=0.5, y=0.5, anchor="center")

with scene("main", 4):
    cafe = Object("../figure_cafe.png")
    cafe.time(3) <= resize(sx=0.5, sy=0.5)
    cafe <= move(x=0.5, y=0.5, anchor="center")

# main シーンは intro(3s) の後に開始するため cafe.start は 3.0 になる
