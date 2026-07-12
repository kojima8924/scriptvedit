from scriptvedit import *
obj = Object(here("test19_scene.html"), duration=2.0, size=(640, 360), data={"opacity": 0.8})
obj <= move(x=0.5, y=0.5, anchor="center")
