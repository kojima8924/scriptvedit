from scriptvedit import *

# --- slide 2 (5-10s): カフェイラスト、右側で移動デモ ---
pause.time(5)

cafe = Object("figure_cafe.png")
cafe <= resize(sx=0.35, sy=0.35)
cafe.time(5) <= move(
    x=keyframes((0, 1.15), (0.25, 0.78), (1.0, 0.78)),
    y=keyframes((0, 0.5), (0.3, 0.45), (0.7, 0.65), (1.0, 0.5)),
    anchor="center",
) & scale(apply_easing(ease_in_out_back, 0.4, 1.0)) \
  & fade(sequence_param(
      (0, 0.15, lambda t: t.smooth()),
      (0.85, 1, lambda t: t.smooth().invert()),
      default=1,
  ))

# --- slide 3 (10-15s): おにぎり、イージングデモ ---
oni = Object("onigiri_tenmusu.png")
oni <= resize(sx=0.35, sy=0.35)
oni.time(5) <= move(
    x=lambda u: u.smooth().map(0.78, 0.78),
    y=phase(0, 0.4, lambda u: u.smooth().map(1.15, 0.5)),
    anchor="center",
) & scale(apply_easing(ease_out_bounce, 0.6, 1.0)) \
  & rotate_to(from_deg=-30, to_deg=15) \
  & fade(sequence_param(
      (0, 0.15, lambda t: t.smooth()),
      (0.85, 1, lambda t: t.smooth().invert()),
      default=1,
  ))
