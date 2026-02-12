from scriptvedit import *

# subtitle_box: ボックス型字幕 + 背景
bg = Object("../bg_pattern_ishigaki.jpg")
bg <= resize(sx=2, sy=2)
bg.time(3) <= move(x=0.5, y=0.5, anchor="center")

sub = subtitle_box("テスト字幕", duration=3)
sub.time(3) <= move(x=0.5, y=0.5, anchor="center")
