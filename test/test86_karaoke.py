from scriptvedit import *
# karaoke: ASS \k タグによるカラオケ風ハイライト字幕（均等割り + word_durations明示）
sub = karaoke([
    (0.0, 2.0, "こんにちは世界"),
    (2.0, 4.5, "今日も良い天気ですね",
     [0.4, 0.3, 0.3, 0.5, 0.3, 0.3, 0.4, 0.3, 0.4, 0.2]),
], style={"primary": "yellow", "secondary": "white", "size": 44})
sub.time(5)
