from scriptvedit import *

# lens Effect: レンズ歪み補正（樽型）
img = Object(asset("images/bg_pattern_tiles.jpg"))
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= lens(k1=-0.3, k2=0.1) & move(x=0.5, y=0.5, anchor="center")
