from scriptvedit import *
oni = Object(asset("images/onigiri_tenmusu.png"))
oni <= resize(sx=0.4, sy=0.4)
oni.time(3) <= move(x=0.5, y=0.5, anchor="center") & fade(lambda u: u)
anchor("oni_done")

se = Object(asset("audio/ビックリ音.mp3"))
se.time(1) <= again(0.5)
