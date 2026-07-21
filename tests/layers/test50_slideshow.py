from scriptvedit import *

# slideshow: 3枚の画像をxfade(slideleft)で連結した合成Object
sl = slideshow(
    [asset("images/shape_badge.png"), asset("images/shape_figure.png"), asset("images/shape_starburst.png")],
    each=2.0, transition="slideleft", t_dur=0.5)
sl.time(6) <= move(x=0.5, y=0.5, anchor="center")
