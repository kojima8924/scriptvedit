from scriptvedit import *
obj = Object(here("test19_scene.html"), duration=2.0, size=(640, 360), data={"opacity": 0.8})
obj <= resize(sx=0.5, sy=0.5)
obj.time(2) <= move(x=0.5, y=0.5, anchor="center") & fade(lambda u: u)
