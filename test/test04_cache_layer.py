from scriptvedit import *

cafe = Object("../figure_cafe.png")
cafe <= resize(sx=0.3, sy=0.3)
cached = cafe.cache("test04_cafe_cache.png")
cached.time(3) <= move(x=0.5, y=0.5, anchor="center") & scale(0.8)
