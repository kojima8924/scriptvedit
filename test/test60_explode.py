# explode_to: 対象自身が粒子化して飛散
from scriptvedit import *

oni = Object("../onigiri_tenmusu.png")
oni.time(2) <= resize(sx=0.5, sy=0.5)
oni <= explode_to(speed=180, gravity=250, max_pixels=800, seed=7)
oni <= move(x=0.5, y=0.5, anchor="center")
