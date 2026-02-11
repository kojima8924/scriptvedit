from scriptvedit import *

# video + transform-only + time未指定 → duration=None
# checkpoint生成時にobj.length()で補完されるべき
obj = Object("../fox_noaudio.mp4")
obj <= resize(sx=0.5, sy=0.5)
obj <= move(x=0.5, y=0.5, anchor="center")
