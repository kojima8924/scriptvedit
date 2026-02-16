# scriptvedit ショーケース動画（ポートフォリオ用）
import sys, os
sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1920, height=1080, fps=30, background_color="#12121e")

p.layer("showcase_slides.py", priority=0)
p.layer("showcase_morph.py", priority=1)
p.layer("showcase_objects.py", priority=2)
p.layer("showcase_watermark.py", priority=3)

# BGM
p.layer("showcase_bgm.py", priority=4)

out = os.path.join(os.path.dirname(__file__), "output_showcase.mp4")
p.render(out)
print(f"出力: {out}")
