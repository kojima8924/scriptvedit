from scriptvedit import *

# タイトル画面下部: カフカ → テントウムシのモーフィング
src = Object("nigaoe_franz_kafka.png")
tgt = Object("mushi_tentoumushi.png")

src.time(5) <= morph_to(tgt) \
    & -scale(0.25) \
    & move(
        x=apply_easing(ease_out_cubic, 0.35, 0.65),
        y=0.82,
        anchor="center",
    ) & -fade(sequence_param(
        (0, 0.2, lambda t: t.smooth()),
        (0.8, 1, lambda t: t.smooth().invert()),
        default=1,
    ))
