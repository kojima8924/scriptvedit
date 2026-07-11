from scriptvedit import *
# loop（aloop） + duck_under（sidechaincompress、narration再生中にBGMを下げる）
narr = Object("../ビックリ音.mp3")
narr.time(2)
bgm = Object("../Impact-38.mp3")
bgm.time(5) <= loop() & again(0.7) & duck_under(narr, ratio=6, threshold=0.03)
