from scriptvedit import *

# rotate_to Effect: 0度→180度の回転アニメーション + move保持確認
img = Object(asset("images/onigiri_tenmusu.png"))
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= rotate_to(from_deg=0, to_deg=180)
img <= move(x=0.5, y=0.5, anchor="center")
