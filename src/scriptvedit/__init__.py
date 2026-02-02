"""
scriptvedit - スクリプトベースの動画編集ライブラリ

v0.3.0 で破壊的変更:
- グローバルタイムライン (configure/clear) を廃止
- Project クラスを導入
- Media.show(), TextClip.show(), Audio.play() に timeline 引数が必須

使用例:
    from scriptvedit import Project, fade

    p = Project()
    p.configure(width=1920, height=1080, fps=30)

    bg = p.clip("background.jpg").resize(sx=1.0)
    bg.show(p.timeline, time=5, start=0)

    p.text("Hello").pos(x=0.5, y=0.5).show(p.timeline, time=3, start=1, effects=[fade(alpha=lambda u: u)])

    from scriptvedit.renderer import render
    render(p.timeline, "output.mp4")
"""

from .project import Project
from .media import clip, audio
from .text import text, subtitle
from .effects import move, fade, rotate_to, scale, blur, shake
from . import ease

__version__ = "0.3.0"
__all__ = [
    "Project",
    "clip", "audio", "text", "subtitle",
    "move", "fade", "rotate_to", "scale", "blur", "shake",
    "ease"
]
