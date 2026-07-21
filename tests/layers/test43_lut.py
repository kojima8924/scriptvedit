from scriptvedit import *

# lut Effect: 3D LUT（恒等LUTファイル）
img = Object(asset("images/shape_badge.png"))
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= lut(here("test43_identity.cube")) & move(x=0.5, y=0.5, anchor="center")
