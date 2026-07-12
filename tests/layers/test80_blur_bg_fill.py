from scriptvedit import *

# blur_background_fill: ぼかした自分自身を背景に敷く（縦横変換の定番）
fox = Object(asset("video/fox_noaudio.mp4"))
fox.time(3) <= blur_background_fill(blur=24)
