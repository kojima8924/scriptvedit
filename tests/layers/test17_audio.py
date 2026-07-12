from scriptvedit import *
bgm = Object(asset("audio/Impact-38.mp3"))
v, a = bgm.split()
# v is None（音声のみ）
a <= again(0.6) & afade(lambda u: lerp(0, 1, u))
bgm.time(4)
