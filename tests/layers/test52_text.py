from scriptvedit import *
# text: エスケープ(%, :, ')=textfile方式 + x/y/alpha アニメーション + box
t = text("値: 100% 'テスト'", x=0.5, y=lambda u: 0.2+0.6*u, size=48,
         color="yellow", box=True, box_color="black@0.6",
         alpha=lambda u: clip(u*2,0,1))
t.time(3) <= fade(lambda u: 1-abs(2*u-1))
