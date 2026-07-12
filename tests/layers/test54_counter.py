from scriptvedit import *
# counter: 数値カウントアップ %{eif} + format(%03d) + 前後リテラル
c = counter(0, 100, format="スコア: %03d点", x=0.5, y=0.4, size=56,
            color="white", font="C:/Windows/Fonts/meiryo.ttc")
c.time(4)
