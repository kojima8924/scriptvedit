# scriptvedit

Python DSL で動画編集スクリプトを記述し、FFmpeg でレンダリングするライブラリ。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FFmpeg](https://img.shields.io/badge/FFmpeg-required-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 必要条件

- Python 3.10+
- FFmpeg / ffprobe（PATH に追加されていること）
- PySide6（GUI を使用する場合）

## インストール

```bash
# 基本インストール
pip install -e .

# GUI を使用する場合
pip install -e ".[gui]"

# 開発用（テスト含む）
pip install -e ".[dev]"

# GUI + 開発用
pip install -e ".[gui,dev]"
```

## 基本的な使い方

v0.3.0 では `Project` クラスを使用します。

```python
from scriptvedit import Project, fade

# プロジェクト作成
p = Project()
p.configure(width=1920, height=1080, fps=30)

# 画像を開いてリサイズ・配置
bg = p.clip("background.jpg")
bg.resize(sx=1.0, sy=1.0).pos(x=0.5, y=0.5)
bg.show(p.timeline, time=5, start=0)

# テキストを追加
p.text("Hello World").pos(x=0.5, y=0.5).show(p.timeline, time=3, start=1, effects=[fade(alpha=lambda u: u)])

# レンダリング
from scriptvedit.renderer import render
render(p.timeline, "output.mp4")
```

## CLI

```bash
# プロジェクトJSONをレンダリング
scriptvedit render project.json -o output.mp4

# プレビュー生成（低解像度・短時間）
scriptvedit preview project.json -t 5.0 --pre 2 --post 2

# GUIエディタを起動
scriptvedit gui
scriptvedit gui project.json
```

## JSON シリアライゼーション

プロジェクトを JSON で保存・読み込みできます。

```python
from scriptvedit import Project

# 保存
p = Project()
p.configure(width=1920, height=1080, fps=30)
# ... クリップを追加 ...
p.save("project.json")

# 読み込み
p = Project.load("project.json")
```

## エフェクト

### fade（透明度エフェクト）

`fade(alpha=...)` で透明度を制御します。

- **float**: 固定透明度（0.0=完全透明, 1.0=不透明）
- **callable**: 時間変化する透明度（u: 0→1 を受け取る関数）

```python
# 固定透明度（常に50%透明）
fade(alpha=0.5)

# フェードイン（透明→不透明）
fade(alpha=lambda u: u)

# フェードアウト（不透明→透明）
fade(alpha=lambda u: 1 - u)

# カスタムカーブ（イーズイン）
fade(alpha=lambda u: u * u)
```

### その他のエフェクト

```python
# 移動
move(x=0.8, y=0.5)  # 終了位置を指定（線形補間）
move(x=lambda u: 0.5 + 0.3 * u, y=0.5)  # カスタム軌道

# 回転
rotate_to(angle=360)  # 1回転
rotate_to(angle=lambda u: 360 * u * u)  # イーズイン回転

# スケール
scale(sx=1.5)  # 1.5倍に拡大
scale(sx=lambda u: 1 + 0.5 * u)  # 徐々に拡大

# ブラー
blur(amount=10)  # 最終的にブラー10
blur(amount=lambda u: 20 * (1 - u))  # ブラーが解除されていく

# 振動
shake(intensity=0.02, speed=10)  # 2%の振幅、10Hz
```

## レイヤーとオフセット

```python
# レイヤー（大きいほど手前）
img.show(p.timeline, time=3, start=0, layer=2)

# オフセット（動画の途中から再生）
video.show(p.timeline, time=2, start=1, offset=0.5)  # 動画の0.5秒目から開始
```

## テキストオーバーレイ

画像ファイル不要でテキストを画面に表示できます。

```python
from scriptvedit import Project

p = Project()
p.configure(width=1920, height=1080, fps=30)

# 基本的なテキスト表示
p.text("Hello World").pos(x=0.5, y=0.5, anchor="center").show(p.timeline, time=3, start=0)

# スタイル設定
p.text("字幕テキスト").pos(x=0.5, y=0.9, anchor="center").font(size=48, color="white").box(color="black@0.7").show(p.timeline, time=2, start=1, layer=10)

# 透明度設定
p.text("透明テキスト").opacity(0.5).show(p.timeline, time=2, start=0)

from scriptvedit.renderer import render
render(p.timeline, "output.mp4")
```

### テキストスタイル

```python
# フォント設定
p.text("Sample").font(file="path/to/font.ttf", size=72, color="yellow")

# 背景ボックス
p.text("Sample").box(enable=True, color="black@0.5", borderw=10)

# 縁取り
p.text("Sample").border(width=2, color="black")

# 影
p.text("Sample").shadow(x=2, y=2, color="gray")
```

### subtitle() プリセット

よく使う字幕スタイルを簡単に作成できます。

```python
# subtitle() は以下と同等:
# text(...).font(size=48, color="white").border(width=2, color="black")
#          .shadow(x=2, y=2, color="black@0.6").pos(x=0.5, y=0.9, anchor="center")
p.subtitle("字幕テキスト").show(p.timeline, time=3, start=0)
```

### 改行

`\n` で改行できます。

```python
p.text("1行目\n2行目\n3行目").show(p.timeline, time=3, start=0)
```

### テキストにエフェクトを適用

テキストにも `fade()` エフェクトを適用できます。

```python
from scriptvedit import fade, ease

# フェードイン
p.text("Hello").show(p.timeline, time=2, start=0, effects=[fade(alpha=lambda u: u)])

# イーズイン付きフェードアウト
p.text("Goodbye").show(p.timeline, time=2, start=0, effects=[fade(alpha=ease.lerp(1, 0, ease.out_quad))])
```

## イージング

`ease` モジュールでアニメーションカーブを簡単に指定できます。

```python
from scriptvedit import ease, fade, rotate_to, scale

# イーズインフェードイン
fade(alpha=ease.lerp(0, 1, ease.in_quad))

# イーズインアウト回転
rotate_to(angle=ease.lerp(0, 360, ease.in_out_cubic))

# イーズアウトフェードアウト
fade(alpha=ease.lerp(1, 0, ease.out_quad))

# スケールアニメーション
scale(sx=ease.lerp(0.5, 1.0, ease.in_out_sine))
```

### 利用可能なイージング関数

| 関数 | 説明 |
|------|------|
| `linear` | 線形（デフォルト） |
| `in_quad` / `out_quad` / `in_out_quad` | 二次関数 |
| `in_cubic` / `out_cubic` / `in_out_cubic` | 三次関数 |
| `in_quart` / `out_quart` / `in_out_quart` | 四次関数 |
| `in_sine` / `out_sine` / `in_out_sine` | サイン |
| `in_expo` / `out_expo` / `in_out_expo` | 指数関数 |

### ユーティリティ

```python
# lerp: a から b への補間
ease.lerp(0, 100, ease.in_quad)  # 0→100 をイーズイン

# inv: in系 → out系 に反転
ease.inv(ease.in_quad)  # out_quad と同等
```

## プレビュー API

GUI やプログラムから低解像度プレビューを生成できます。

```python
from scriptvedit import Project
from scriptvedit.renderer import render_preview, compile_filtergraph, spawn_ffmpeg

p = Project.load("project.json")

# 簡単なプレビュー生成
actual_start, actual_end = render_preview(
    p.timeline,
    "preview.mp4",
    center_time=5.0,  # 中心時刻
    pre=2.0,          # 前
    post=2.0,         # 後
    out_width=640,
    out_height=360,
    out_fps=15
)

# より細かい制御が必要な場合
compiled = compile_filtergraph(
    p.timeline,
    start=3.0,
    duration=4.0,
    out_width=640,
    out_height=360,
    out_fps=15
)

# 非同期でFFmpegを起動（キャンセル可能）
process = spawn_ffmpeg(compiled, "preview.mp4")
# ... 後でキャンセルする場合 ...
process.terminate()
```

## Breaking Changes

### v0.3.0

#### グローバルタイムラインの廃止

**変更前**:
```python
from scriptvedit import *
configure(width=1920, height=1080, fps=30)
clip("bg.jpg").show(time=5, start=0)
render("output.mp4")
```

**変更後**:
```python
from scriptvedit import Project
from scriptvedit.renderer import render

p = Project()
p.configure(width=1920, height=1080, fps=30)
p.clip("bg.jpg").show(p.timeline, time=5, start=0)
render(p.timeline, "output.mp4")
```

**移行のポイント**:
- `configure()`, `clear()` → `Project.configure()`, `Project.clear()`
- `show(time, ...)` → `show(timeline, time, ...)`
- `play(time, ...)` → `play(timeline, time, ...)`
- `render("out.mp4")` → `render(timeline, "out.mp4")`

### v0.2.0

#### fade(alpha=0) の挙動変更

**変更前**: `fade(alpha=0)` は「フェードアウト」として特別扱いされ、FFmpeg の `fade=t=out` フィルタを使用していました。

**変更後**: `fade(alpha=0)` は「固定透明度 0（完全透明）」として扱われ、`colorchannelmixer=aa=0` を使用します。

**移行方法**:
```python
# 旧: フェードアウトの意図で alpha=0 を使っていた場合
fade(alpha=0)

# 新: callable を使ってフェードアウトを明示
fade(alpha=lambda u: 1 - u)
```

この変更により、`fade(alpha=...)` の意味が統一されました：
- float → 常に固定透明度
- callable → 時間変化する透明度

## ライセンス

MIT
