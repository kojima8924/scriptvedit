from scriptvedit import *

# reverse: trim(2)で短くしてから逆再生（30秒ガード内）
fox = Object(asset("video/fox_noaudio.mp4"))
fox.time(2) <= trim(2) & reverse() & move(x=0.3, y=0.5, anchor="center")

# freeze_frame: t=1のフレームで1秒静止（trim(2) → 総尺3s）
guitar = Object(asset("video/guitar_noaudio.mp4"))
guitar.time(3) <= (trim(2) & freeze_frame(at=1.0, duration=1.0)
                   & move(x=0.7, y=0.5, anchor="center"))
