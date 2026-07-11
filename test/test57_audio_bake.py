from scriptvedit import *
# audio_sequence（acrossfade連結） + sfx（adelay+amix合成）
seq = audio_sequence("../Impact-38.mp3", "../ビックリ音.mp3", crossfade=0.5)
seq.time(3)
sx = sfx("../ビックリ音.mp3", at=[0.5, 1.5, 2.5], volume=0.8)
sx.time(4)
