from scriptvedit import *
# formula + scale/rotate: 数式PNGに動的スケール（+回転）をかけ、
# pad(固定サイズ・中央配置・eval=frame) + copy の SEGV バリア経路を実レンダで踏む。
#
# 注意: dry_run では数式PNGが未生成のため寸法が取れず base_dims=None になり、
# pad が出ないコマンドになる。スナップショットではこの経路を検証できないので、
# **実レンダ（tests/render_all.py の test92）でカバーする**。
eq = formula(r"e^{i\pi} + 1 = 0", size=56, color="#ffcc00")
eq.time(3) <= (scale(lambda u: 1 + 0.5 * sin(2 * PI * u))
               & rotate_to(360)
               & move(x=0.5, y=0.5, anchor="center"))
