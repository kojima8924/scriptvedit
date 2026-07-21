from scriptvedit import *
# audio_viz: showwaves で音声を可視化した映像Object（キャッシュ生成物）
av = audio_viz(asset("audio/bgm_loop.mp3"), kind="waves", color="cyan", size=(640, 200))
av.time(3) <= move(x=0.5, y=0.8, anchor="center")
