from scriptvedit import *

# transition: 2つのObjectをxfade(dissolve)で1本に連結
a = Object(asset("images/shape_badge.png")).time(2)
b = Object(asset("images/shape_figure.png")).time(2)
tr = transition(a, b, kind="dissolve", duration=0.5)
tr.time(3.5) <= move(x=0.5, y=0.5, anchor="center")
