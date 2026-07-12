# テスト04: 画像キャッシュ透過（定式幕背景+キャッシュカフェ）
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="white")
p.layer("test04_maku.py", priority=0)
p.layer("test04_cache_layer.py", priority=1)
p.render("test04.mp4")
