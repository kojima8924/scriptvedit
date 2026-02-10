from scriptvedit import *

# 複数図形+from/toアニメ+spotlight
d = diagram([
    # 枠線付き矩形
    rect(0.05, 0.1, 0.4, 0.25, rx=0.02, fill="none", stroke="#ffffff", strokeWidth=3),
    # ラベル
    label(0.25, 0.22, "Step 1", fill="#ffffff", fontSize=42),
    # 円（フェードインアニメ）
    circle(0.7, 0.3, 0.06, fill="#ff6644", stroke="#ffffff", strokeWidth=2,
           opacity={"from": 0.0, "to": 1.0}),
    # 矢印（x2がアニメで伸びる）
    arrow(0.45, 0.22, {"from": 0.45, "to": 0.62}, 0.3,
          stroke="#ffcc00", strokeWidth=4),
    # 2番目の矩形
    rect(0.55, 0.1, 0.4, 0.25, rx=0.02, fill="none", stroke="#88ff88", strokeWidth=3),
    label(0.75, 0.22, "Step 2", fill="#88ff88", fontSize=42),
    # 下部にスポットライト
    spotlight(0.5, 0.7, 0.2, dim=0.5),
    # スポットライト内のテキスト
    label(0.5, 0.7, "Focus!", fill="#ffff00", fontSize=48,
          stroke="#000000", strokeWidth=2),
], duration=3.0)
d <= move(x=0.5, y=0.5, anchor="center")
