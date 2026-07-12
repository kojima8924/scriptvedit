from scriptvedit import *
# slide: ページ切替規約テスト（window.showSlide版 / id="page-N"フォールバック版）
s0 = slide(here("test87_slide_showfn.html"), page=0, duration=1.0, width=640, height=360)
s0.time(1.0)
s1 = slide(here("test87_slide_divs.html"), page=1, duration=1.0, width=640, height=360)
s1.time(1.0)
