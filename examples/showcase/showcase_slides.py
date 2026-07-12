from scriptvedit import *

# スライド構成: HTMLベースのレンダリング (ファイル, 表示秒数)
SLIDES = [
    ("slides/slide_01_title.html",    7.5),
    ("slides/slide_02_syntax.html",   7.5),
    ("slides/slide_03_features.html", 7.5),
    ("slides/slide_04_closing.html",  4.5),
]

for path, dur in SLIDES:
    s = Object(here(path), duration=dur, size=(1920, 1080))
    fi = 0.8 / dur   # フェードイン比率
    fo = 0.8 / dur   # フェードアウト比率
    # ゆっくりズーム + フェードイン/アウト
    s.time(dur) <= move(x=0.5, y=0.5, anchor="center") \
        & scale(lambda u: 1.0 + 0.03 * u) \
        & fade(lambda u, _fi=fi, _fo=fo:
            clip(u / _fi, 0, 1) * clip((1 - u) / _fo, 0, 1))
