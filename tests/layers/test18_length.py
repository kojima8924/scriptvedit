from scriptvedit import *
clip = Object(asset("video/clip_with_audio.mp4"))
clip.time(clip.length())
clip <= resize(sx=0.3, sy=0.3)
clip <= move(x=0.5, y=0.5, anchor="center")
