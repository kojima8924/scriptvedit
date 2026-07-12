from scriptvedit import *

# speed: 2倍速（実効尺 5.545/2 ≈ 2.77s、time()省略で自動決定）
fox = Object(asset("video/fox_noaudio.mp4"))
fox.time() <= speed(2.0) & move(x=0.3, y=0.5, anchor="center")

# speed + trim: trim(2)後に0.5倍速 → 実効尺4s（明示time）
guitar = Object(asset("video/guitar_noaudio.mp4"))
guitar.time(4) <= trim(2) & speed(0.5) & move(x=0.7, y=0.5, anchor="center")
