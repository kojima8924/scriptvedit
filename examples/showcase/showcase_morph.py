from scriptvedit import *

# タイトル画面下部: カフカ → テントウムシのモーフィング
src = Object(asset("images/nigaoe_franz_kafka.png"))
tgt = Object(asset("images/mushi_tentoumushi.png"))

src.time(7.5) <= morph_to(tgt, max_pixels=4000) \
    & -scale(0.5) \
    & move(
        x=apply_easing(ease_out_cubic, 0.35, 0.65),
        y=0.82,
        anchor="center",
    ) & -fade(sequence_param(
        (0, 0.2, lambda t: t.smooth()),
        (0.8, 1, lambda t: t.smooth().invert()),
        default=1,
    ))
