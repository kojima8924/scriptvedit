# 部分レンダ（時間窓）用のシンプルなレイヤー
from scriptvedit import *

oni = Object("../onigiri_tenmusu.png")
oni.time(6) <= move(from_x=0.1, to_x=0.9, y=0.5, anchor="center")
