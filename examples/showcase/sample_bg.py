from scriptvedit import *

# 背景画像: 画面全体を覆うようにリサイズ、徐々に拡大、半分までフェードアウト
# 元画像800x450 → 画面1920x1080 に合わせて2.4倍
bg = Object(asset("images/bg_pattern_ishigaki.jpg"))
bg <= resize(sx=2.4, sy=2.4)
bg.time(6) <= move(x=0.5, y=0.5, anchor="center") & scale(lambda u: 1.0 + u) & fade(lambda u: 1 - u / 2)
