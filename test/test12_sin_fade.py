from scriptvedit import *

# sin波フェード: フェードイン→フェードアウト
oni = Object("../onigiri_tenmusu.png")
oni <= resize(sx=0.3, sy=0.3)
oni.time(4) <= move(x=0.5, y=0.5, anchor="center") & fade(lambda u: sin(u * PI))
