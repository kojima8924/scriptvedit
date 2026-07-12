from scriptvedit import *

# time()省略 → auto duration（加工後長で自動決定）
# trim(3) が付いた後の length() = 3 が duration に反映されることを検証
obj = Object(asset("video/fox_noaudio.mp4"))
obj <= resize(sx=0.5, sy=0.5)
obj.time() <= move(x=0.5, y=0.5, anchor="center") & trim(3)
