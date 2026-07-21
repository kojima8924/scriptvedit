# サンプル動画レンダリング (旧scriptvedit sample.py のSVE2移植)
import os

from scriptvedit import *

p = Project()
p.configure(width=1920, height=1080, fps=30, background_color="black")
p.layer("sample_bg.py", priority=0)
p.layer("sample_figure.py", priority=1)
p.layer("sample_badge.py", priority=2)
p.render(os.path.join(os.path.dirname(__file__), "output.mp4"))
