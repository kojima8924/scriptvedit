from scriptvedit import *

# 背景: 花畑動画
bg = Object(asset("video/flowerbg_noaudio.mp4"))
bg.show(4) <= move(x=0.5, y=0.5, anchor="center")

# pip プリセット: scale + rounded + outline + drop_shadow + move の合成
fox = Object(asset("video/clip_with_audio.mp4"))
fox.show(4) <= pip(x=0.75, y=0.75, scale=0.3, radius=16, border=2,
                   border_color="white", shadow=True)

# rounded 単体
oni = Object(asset("images/shape_badge.png"))
oni.time(4) <= rounded(40) & move(x=0.25, y=0.3, anchor="center")
