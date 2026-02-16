from scriptvedit import *

# スライド構成: (ファイル, 表示秒数)
SLIDES = [
    ("slides/slide_01_title.png",    5),
    ("slides/slide_02_syntax.png",   5),
    ("slides/slide_03_features.png", 5),
    ("slides/slide_04_closing.png",  3),
]

for path, dur in SLIDES:
    s = Object(path)
    fi = 0.8 / dur   # フェードイン比率
    fo = 0.8 / dur   # フェードアウト比率
    # ゆっくりズーム + フェードイン/アウト
    s.time(dur) <= move(x=0.5, y=0.5, anchor="center") \
        & scale(lambda u: 1.0 + 0.03 * u) \
        & fade(lambda u, _fi=fi, _fo=fo:
            clip(u / _fi, 0, 1) * clip((1 - u) / _fo, 0, 1))
