from scriptvedit import *

# Percent + ~disable テスト
oni = Object("../onigiri_tenmusu.png")
oni <= resize(sx=50%P, sy=50%P)
oni.time(3) <= move(x=50%P, y=50%P, anchor="center") & ~fade(lambda u: u) & scale(lambda u: lerp(0.5, 1, u))
