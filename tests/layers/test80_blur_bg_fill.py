from scriptvedit import *

# blur_background_fill: ぼかした自分自身を背景に敷く（縦横変換の定番）
fox = Object(asset("video/clip_with_audio.mp4"))
fox.time(3) <= blur_background_fill(blur=24)
