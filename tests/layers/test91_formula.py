from scriptvedit import *
# formula: KaTeX 同梱の数式レンダ（透過PNG化した画像Objectにアニメがそのまま効く）
eq = formula(r"\sum_{k=1}^{n} k = \frac{n(n+1)}{2}", size=64, color="white")
eq.time(4) <= fade(lambda u: u) & move(x=0.5, y=0.4, anchor="center")

# インライン数式（display=False）+ 色指定
inl = formula(r"x^2 + y^2 = r^2", size=36, color="#ffcc00", display=False, duration=3)
inl <= move(x=0.5, y=0.75, anchor="center")

# formula_lines: 複数行を縦積み（式変形の提示）
proof = formula_lines([
    r"a^2 + b^2 = c^2",
    r"c = \sqrt{a^2 + b^2}",
], size=40, gap=16, align="center")
proof.time(3) <= move(x=0.2, y=0.2, anchor="center")
