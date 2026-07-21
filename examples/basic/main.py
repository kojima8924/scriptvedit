"""基本サンプル: 背景 + おにぎりの2レイヤー合成

どのディレクトリからでも実行できる（レイヤー・素材のパスは cwd 非依存で解決される）:
    python examples/basic/main.py
"""
import os

from scriptvedit import *

if __name__ == "__main__":
    p = Project()
    p.configure(width=1280, height=720, fps=30, background_color="black")

    # レイヤーファイルはこのスクリプトからの相対でも解決される
    p.layer("bg.py", priority=0)
    p.layer("badge.py", priority=1)

    p.render(os.path.join(os.path.dirname(os.path.abspath(__file__)), "output.mp4"))
