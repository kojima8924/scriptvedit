from scriptvedit import *

onigiri = Object("onigiri_tenmusu.png")
onigiri <= resize(sx=0.3, sy=0.3)
onigiri.time(6) <= move(x=0.3, y=0.7, anchor="center") & scale(lambda u: lerp(0.5, 1, u)) & fade(lambda u: u)
