import math
from scriptvedit import Project, fade, move, scale, rotate_to
from scriptvedit.renderer import render
p = Project()
p.configure(width=1920, height=1080, fps=30, background_color="black")
bg = p.clip("bg_pattern_ishigaki.jpg")
bg.resize(sx=1, sy=1).pos(x=0.5, y=0.5, anchor="center")
bg.show(p.timeline, time=6, start=0, layer=0, effects=[
    scale(lambda u: 1.0 + u),
    fade(alpha=lambda u: 1-u/2),
])
cafe = p.clip("figure_cafe.png")
cafe.resize(sy=0.5).pos(x=0.15, y=0.5, anchor="center")
cafe.show(p.timeline, time=6, start=0, layer=1, effects=[
    move(x=lambda u: 0.9*u, y=lambda u: 0.5+0.2*math.sin(u * 4 * math.pi))
])
onigiri = p.clip("onigiri_tenmusu.png")
onigiri.resize(sy=0.3).pos(x=0.85, y=0.15, anchor="center")
onigiri.show(p.timeline, time=6, start=0, layer=2, effects=[
    move(
        x=lambda u: 0.9*u-0.3*(1-u),
        y=lambda u: 0.5+0.2*math.sin(u * 4 * math.pi) - 0.3*(1-u)
    ),
    scale(sy=lambda u: 0.3* (1-u**0.5)+0.1),
    rotate_to(angle=lambda u: u * 360 * 4),
])
render(p.timeline, "output.mp4", verbose=True)
