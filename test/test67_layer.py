from scriptvedit import *

# 出力形式テスト用の最小レイヤー（bakeable無し=チェックポイント無しでクリーンなcmd）
oni = Object("../onigiri_tenmusu.png")
oni.time(3) <= move(x=0.5, y=0.5, anchor="center")
