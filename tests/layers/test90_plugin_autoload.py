from scriptvedit import *

# test/plugins/ の自動読込で使えるようになったプラグイン（tint_wash / test_live_only）
oni = Object(asset("images/onigiri_tenmusu.png"))
oni <= resize(sx=0.5, sy=0.5)
oni.time(2) <= (move(x=0.5, y=0.5, anchor="center")
                & tint_wash(color="blue", amount=lambda u: u * 0.8)
                & test_live_only(mode="hard", gamma=1.2))
