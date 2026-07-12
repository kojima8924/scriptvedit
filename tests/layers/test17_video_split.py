from scriptvedit import *
clip = Object(asset("video/fox_noaudio.mp4"))
v, a = clip.split()
# a is None（音声なし動画）
v <= resize(sx=0.5, sy=0.5)
clip.time(3) <= move(x=0.5, y=0.5, anchor="center") & scale(lambda u: lerp(0.8, 1, u))
