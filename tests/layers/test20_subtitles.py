from scriptvedit import *

# Alice の字幕
s1 = subtitle("それでは整理していきましょう！", who="Alice", duration=2.5,
              style={"fontSize": 40, "nameColor": "#ffccdd"})
s1 <= fade(lambda u: lerp(0.0, 1.0, u))

# Bob の字幕
s2 = subtitle("了解！ポイントは3つだね", who="Bob", duration=2.0,
              style={"fontSize": 40, "nameColor": "#cceeff"})

# Carol のナレーション（話者なし）
s3 = subtitle("まず最初のステップから見ていきます", duration=2.5,
              style={"fontSize": 36, "barColor": "rgba(0,0,80,0.6)"})
s3 <= move(x=0.5, y=0.5, anchor="center")
