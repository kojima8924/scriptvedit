from scriptvedit import *

# video_sequence: 動画クリップをxfadeで連結した1本の合成Object
# fox(5.545s) + flower(10.01s) → 合成尺 5.545 + 10.01 - 0.5 = 15.055s
seq = video_sequence(asset("video/clip_with_audio.mp4"), asset("video/flowerbg_noaudio.mp4"),
                     transition="wipeleft", t_dur=0.5)
seq.time(15.055) <= move(x=0.5, y=0.5, anchor="center")
