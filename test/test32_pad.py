from scriptvedit import *

# pad Transform: パディングで640x480に拡張 + resize + move
img = Object("../onigiri_tenmusu.png")
img <= resize(sx=0.5, sy=0.5)
img <= pad(w=640, h=480, color="navy")
img.time(2) <= move(x=0.5, y=0.5, anchor="center")
