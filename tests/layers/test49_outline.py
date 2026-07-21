from scriptvedit import *

# outline Effect: alpha膨張（dilation×3）ベースの縁取り
img = Object(asset("images/shape_badge.png"))
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= outline(width=3, color="white") & move(x=0.5, y=0.5, anchor="center")
