from scriptvedit import *
# thumbnail()/storyboard() が数式PNGを生成することの検証用（live opsのみ＝ベイク無し）
eq = formula(r"a^2 + b^2 = c^2", size=40, color="white")
eq.time(2) <= move(x=0.5, y=0.5, anchor="center")
