"""
scriptvedit 複合サンプル

実行時間: 約2分14秒 (1920x1080, 6秒, 30fps)

新機能のデモ:
- Project クラスによる状態管理
- レイヤー（layer）による重なり順制御
- 素材内開始位置（offset）による動画トリム
- 各種エフェクト（fade, move, scale, rotate）
- クロマキー合成
- 複数音声トラック
"""

from scriptvedit import Project, fade, move, scale, rotate_to
from scriptvedit.renderer import render

# プロジェクト作成
p = Project()

# 出力設定（6秒の動画）
# curve_samples を減らしてコマンド長を抑える
p.configure(width=1920, height=1080, fps=30, background_color="#0a0a1a", curve_samples=15)

# ============================================================
# 音声トラック
# ============================================================

# BGM: Impact-38（全体に流れる）
bgm = p.audio("Impact-38.mp3")
bgm.set_volume(0.5).set_fade(fade_in=1.0, fade_out=1.5)
bgm.play(p.timeline, time=6, start=0)

# SE: じゃけん夜行きましょうね（3秒から）
se = p.audio("じゃけん夜行きましょうね.wav")
se.set_volume(0.8)
se.play(p.timeline, time=2, start=3)

# ============================================================
# レイヤー0: 背景
# ============================================================

# 石垣パターン（背景、ゆっくりズーム＋フェードイン）
bg = p.clip("bg_pattern_ishigaki.jpg")
bg.resize(sx=1.2, sy=1.2).pos(x=0.5, y=0.5)
bg.show(p.timeline, time=6, start=0, layer=0, effects=[
    scale(sx=1.3),  # 1.2 → 1.3 にゆっくりズーム
    fade(alpha=lambda u: u)  # フェードイン（0→1）
])

# ============================================================
# レイヤー1: 動画素材（offset使用）
# ============================================================

# 煽り動画（0.5秒目から1.5秒間だけ切り出し、左下に配置）
video = p.clip("yj_めっちゃ煽ってくる.mp4")
video.resize(sy=0.3).pos(x=0.2, y=0.75, anchor="center")
video.show(p.timeline, time=1.5, start=1, layer=1, offset=0.5)  # 動画の0.5秒目から開始

# 同じ動画を別の位置（右上、3.5秒から）
video2 = p.clip("yj_めっちゃ煽ってくる.mp4")
video2.resize(sy=0.25).pos(x=0.85, y=0.2, anchor="center")
video2.opacity(0.8)
video2.show(p.timeline, time=1.5, start=3.5, layer=1, offset=1.0, effects=[
    rotate_to(angle=10)  # 10度傾ける
])

# ============================================================
# レイヤー2: メイン素材（クロマキー）
# ============================================================

# iPhone先輩（クロマキー合成、中央から右へ移動）
senpai = p.clip("iPhone13先輩BB静止画版.png")
senpai.resize(sy=0.7).pos(x=0.5, y=0.55, anchor="center")
senpai.chromakey(similarity=0.3, blend=0.15)
senpai.show(p.timeline, time=3, start=0, layer=2, effects=[
    move(x=0.65, y=0.55),  # 中央から右へ移動
])

# iPhone先輩（後半、左から登場して拡大＋フェードアウト）
senpai2 = p.clip("iPhone13先輩BB静止画版.png")
senpai2.resize(sy=0.5).pos(x=0.25, y=0.5, anchor="center")
senpai2.chromakey(similarity=0.3, blend=0.15)
senpai2.show(p.timeline, time=3, start=3, layer=2, effects=[
    scale(sx=0.7),  # 拡大アニメーション
    fade(alpha=lambda u: 1 - u)  # フェードアウト（1→0）
])

# ============================================================
# レイヤー3: 前景装飾
# ============================================================

# おにぎり1（回転しながら登場）
onigiri1 = p.clip("onigiri_tenmusu.png")
onigiri1.resize(sy=0.2).pos(x=0.15, y=0.3, anchor="center")
onigiri1.show(p.timeline, time=2, start=0.5, layer=3, effects=[
    rotate_to(angle=360),  # 1回転
    scale(sx=0.3),  # 少し拡大
])

# おにぎり2（移動）
onigiri2 = p.clip("onigiri_tenmusu.png")
onigiri2.resize(sy=0.15).pos(x=0.85, y=0.7, anchor="center")
onigiri2.show(p.timeline, time=2, start=2.5, layer=3, effects=[
    move(x=0.6, y=0.5)  # 右下から中央へ
])

# ============================================================
# レイヤー4: 最前面オーバーレイ
# ============================================================

# 4色画像（フラッシュ効果、一瞬だけ表示）
flash = p.clip("yj_4色.jpg")
flash.resize(sx=1.0, sy=1.0).pos(x=0.5, y=0.5)
flash.opacity(0.0)  # 初期は透明
flash.show(p.timeline, time=0.3, start=3, layer=4, effects=[
    fade(alpha=0.6)  # 少し透明なフラッシュ
])

# ============================================================
# レンダリング
# ============================================================

render(p.timeline, "output_complex.mp4", verbose=True)
