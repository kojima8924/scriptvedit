from scriptvedit import *

# プラグインEffect: neon_glow(複合サブグラフ) + scanline(liveアニメ)
oni = Object(asset("images/shape_badge.png"))
oni <= resize(sx=0.5, sy=0.5)
oni.time(2) <= (move(x=0.5, y=0.5, anchor="center")
                & neon_glow(radius=8, color="cyan", strength=lambda u: 0.5 + u)
                & scanline(spacing=6, darkness=lambda u: u, speed=30))
