from scriptvedit import *

# おにぎりを右下に小さく表示（diagramの上に重ねる）
oni = Object("../onigiri_tenmusu.png")
oni <= resize(sx=0.25, sy=0.25)
oni.time(3) <= move(x=0.85, y=0.8, anchor="center") & fade(lambda u: lerp(0.3, 1.0, u))
