# テスト10: 画像キャッシュ + 動画合成（cache機能テスト）
import sys; sys.path.insert(0, "..")
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="purple")
p.layer("test10_maku.py", priority=0)
p.layer("test10_cache_layer.py", priority=1)
p.render("test10.mp4")
