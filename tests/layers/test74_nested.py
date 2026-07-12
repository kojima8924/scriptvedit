from scriptvedit import *

# from_project: サブProjectを透過webm素材化して親タイムラインに配置
sub = Project()
sub.configure(width=640, height=360, fps=30, background_color="black")
sub.layer("test74_sub.py", priority=0)

comp = Object.from_project(sub)
comp.time(2) <= move(x=0.5, y=0.5, anchor="center")
