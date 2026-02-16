from scriptvedit import *

# タイトル画面下部: ソースコード → 動画プレーヤーのモーフィング
src = Object("computer_screen_programming.png")
tgt = Object("video_frame_32.png")

src.time(5) <= morph_to(tgt) \
    & -scale(0.25) \
    & move(
        x=lambda u: 0.15 + 0.7 * u,
        y=0.82,
        anchor="center",
    ) & -fade(sequence_param(
        (0, 0.2, lambda t: t.smooth()),
        (0.8, 1, lambda t: t.smooth().invert()),
        default=1,
    ))
