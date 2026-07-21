from scriptvedit import *

# glitch Effect: rgbashift + noise（interval指定で間欠発動）
img = Object(asset("images/shape_figure.png"))
img <= resize(sx=0.5, sy=0.5)
img.time(2) <= glitch(strength=1.5, interval=1.0) & move(x=0.5, y=0.5, anchor="center")
