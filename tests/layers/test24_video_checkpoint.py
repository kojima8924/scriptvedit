from scriptvedit import *

obj = Object(asset("video/fox_noaudio.mp4"))
obj <= resize(sx=0.5, sy=0.5)
obj.time(3) <= move(x=0.5, y=0.5, anchor="center")
