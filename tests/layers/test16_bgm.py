from scriptvedit import *
bgm = Object(asset("audio/bgm_loop.mp3"))
bgm.time(5) <= again(0.8) & afade(lambda u: u)
