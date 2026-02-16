# scriptvedit

Pythonスクリプトで動画を構成するDSL。ffmpegによるレンダリング。

## 設計思想

### 1ファイル = 1レイヤー

動画の各レイヤーを独立したPythonファイルとして管理する。
`main.py` は構成定義のみを担い、各レイヤーファイルの読み込み順序・重ね順を宣言する。

```
main.py        ... 構成定義（設定・レイヤー順序・レンダリング）
bg.py          ... 背景レイヤー
onigiri.py     ... 素材レイヤー
```

### 演算子によるDSL

- `|` (パイプ) ... Transform同士を連結して TransformChain を生成
- `&` (アンド) ... Effect同士を連結して EffectChain を生成
- `<=` (適用) ... Object に TransformChain / EffectChain を適用
- `~` (チルダ) ... quality="fast"（低品質で高速キャッシュ）
- `+` (プラス) ... policy="force"（キャッシュを強制再生成）
- `-` (マイナス) ... policy="off"（キャッシュ対象から除外）
- 無印 ... policy="auto", quality="final"（右端のbakeable opを自動キャッシュ）

```python
obj <= resize(sx=0.3, sy=0.3)     # 無印: autoポリシーで自動キャッシュ対象
obj <= +resize(sx=0.3, sy=0.3)    # force: 常に再生成
obj <= ~resize(sx=0.3, sy=0.3)    # fast: 低品質で高速キャッシュ
obj <= -resize(sx=0.3, sy=0.3)    # off: キャッシュ対象から除外
obj.time(6) <= move(x=0.5, y=0.5, anchor="center") \
               & scale(lambda u: lerp(0.5, 1, u)) \
               & fade(lambda u: u)
```

### パーセント記法

`P` を使って 0〜1 の正規化値をパーセントで書ける。

```python
move(x=50%P, y=75%P)  # x=0.5, y=0.75
```

### Transformは静的、Effectは定数またはアニメーション

- **Transform** (`|` で連結、`<=` で適用): 1回だけ適用される空間変換
  - `resize(sx, sy)` ... サイズ変更
  - `rotate(deg=N)` / `rotate(rad=N)` ... 回転（静的）
  - `crop(x, y, w, h)` ... 切り抜き
  - `pad(w, h, x, y, color)` ... パディング
  - `blur(radius)` ... ぼかし
  - `eq(brightness, contrast, saturation, gamma)` ... 色調補正

- **Effect** (`&` で連結、`<=` で適用): float で定数、lambda(u) でアニメーション
  - `move(x, y, anchor)` ... 配置位置（固定 or from/toアニメーション）
  - `scale(0.5)` ... 定数0.5倍
  - `scale(lambda u: lerp(0.5, 1, u))` ... 0.5倍 → 等倍にアニメーション
  - `fade(0.5)` ... 定数 半透明
  - `fade(lambda u: u)` ... 透明 → 不透明にアニメーション
  - `zoom(to_value=2)` ... ズーム（scale のエイリアス、from/to指定可）
  - `rotate_to(from_deg, to_deg)` ... 回転アニメーション（bakeable）
  - `wipe(direction)` ... ワイプ表示（"left"/"right"/"top"/"bottom"）
  - `color_shift(hue, saturation, brightness)` ... 色相/彩度/明度シフト
  - `shake(amplitude, frequency)` ... 振動（live、overlay座標変調）
  - `trim(duration)` ... 先頭からduration秒にカット（時間影響あり）
  - `delete()` ... 映像をレンダリングから除外（音声のみ残す）
  - `morph_to(target_obj)` ... 画像→画像モーフィング（bakeable、重い。bakeable opsの末尾に配置必須）

`u` は正規化時間（0〜1）。Effectの表示開始から終了まで線形に変化する。

### zoom（scale エイリアス）

`zoom` は `scale` の便利ラッパー。from/to 指定でアニメーションを簡潔に書ける。

```python
zoom(to_value=2)                      # 1.0 → 2.0 ズーム
zoom(from_value=0.5, to_value=2)      # 0.5 → 2.0 ズーム
zoom(value=1.5)                       # 固定1.5倍ズーム
```

### Effect分類（bakeable / live）

checkpointで焼き込まれるか、レンダリング時にoverlay座標で解釈されるかの分類。

| 種類 | 名前 | 分類 | 備考 |
|------|------|------|------|
| Transform | resize, rotate, crop, pad, blur, eq | bakeable | 全Transform は bakeable |
| Effect | scale (zoom) | bakeable | zoom は scale のエイリアス |
| Effect | fade | bakeable | |
| Effect | trim | bakeable | 時間影響あり |
| Effect | rotate_to | bakeable | |
| Effect | wipe | bakeable | |
| Effect | color_shift | bakeable | |
| Effect | morph_to | bakeable | 生成系。bakeable ops の末尾に配置必須 |
| Effect | move | live | overlay座標で解釈 |
| Effect | delete | live | overlay除外 |
| Effect | shake | live | overlay座標にsin/cosオフセット加算 |

**重要**: live Effect は checkpoint で焼かれないため、checkpoint 生成後もレンダリング時に必ず残る。

morph_to は bakeable ops の末尾に配置する必要がある（違反時は ValueError）。
shake は overlay 座標の変調として実装されており live 分類。将来 bakeable に変更する場合は ENGINE_VER 更新が必要。

### 音声エフェクト

動画・音声ファイルの音声トラックを制御する。`&` で連結可能。`~` で無効化。

- `again(value)` ... 音量倍率（デフォルト 1.0）
- `afade(alpha)` ... 音量フェード
- `atrim(duration)` ... 音声トリム（時間影響あり）
- `atempo(rate)` ... テンポ変更（時間影響あり）
- `adelete()` ... 音声をミックスから除外

```python
clip = Object("video.mp4")
clip.time(5) <= move(x=0.5, y=0.5, anchor="center") \
              & fade(lambda u: u) \
              & again(0.6) \
              & atrim(3)
```

### 映像/音声分離（split）

`split()` で映像と音声を個別に制御できる。

```python
clip = Object("video.mp4")
v, a = clip.split()
v <= resize(sx=0.5, sy=0.5)     # 映像のみ変換
a <= again(0.3)                  # 音声のみ音量調整
clip.time(5) <= move(x=0.5, y=0.5, anchor="center")
```

### Expr式ビルダー

lambda内で使える数学関数を多数提供。ffmpegのフィルタ式に自動コンパイルされる。

```python
# sin波フェード（フェードイン→フェードアウト）
fade(lambda u: sin(u * PI))

# 加速するスケール
scale(lambda u: lerp(0.5, 1, smoothstep(0, 1, u)))

# 円運動
move(x=lambda u: 0.5 + 0.3 * cos(u * 2 * PI),
     y=lambda u: 0.5 + 0.3 * sin(u * 2 * PI),
     anchor="center")
```

使用可能な関数:
- 三角: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`
- 双曲線: `sinh`, `cosh`, `tanh`
- 指数/対数: `exp`, `log`, `sqrt`, `log10`, `cbrt`
- 丸め: `floor`, `ceil`, `trunc`
- 補間: `lerp(a, b, t)`
- クランプ: `clip(x, lo, hi)`, `clamp`
- ステップ: `step(edge, x)`, `smoothstep(edge0, edge1, x)`
- その他: `mod`, `frac`, `deg2rad`, `rad2deg`
- 組み込み互換: `abs`, `min`, `max`, `round`, `pow`
- 定数: `PI`, `E`

### move（位置・移動）

`move` は Effect として overlay の座標を制御する。

```python
# 固定位置
move(x=0.5, y=0.5, anchor="center")

# from/to 移動アニメーション
move(from_x=0.0, from_y=0.5, to_x=1.0, to_y=0.5, anchor="center")

# lambda 移動
move(x=lambda u: lerp(0.2, 0.8, u), y=0.5, anchor="center")
```

### チェックポイントキャッシュ（policy/quality方式）

bakeable ops（Transform全般 + scale/fade/trim Effect）の中間結果を自動保存・復元する仕組み。
signatureベースでキャッシュの安全性を保証。保存点はRAA+FSPで最小化。

**policy（キャッシュ制御）:**
- `auto`（無印） ... キャッシュが存在すれば再利用、なければ生成。最右のbakeable opがRAA保存点
- `force`（`+`） ... 常に再生成。FSP保存点
- `off`（`-`） ... キャッシュ対象から除外

**quality（品質制御）:**
- `final`（無印） ... 通常品質（crf=30）
- `fast`（`~`） ... 低品質で高速（crf=40）

```python
# 無印（auto+final）: 自動的に最右bakeableとしてキャッシュ
obj <= resize(sx=0.3, sy=0.3)

# force: 常に再生成
obj <= +resize(sx=0.3, sy=0.3)

# fast品質: 低品質で高速
obj <= ~resize(sx=0.3, sy=0.3)

# off: キャッシュ対象外
obj <= -resize(sx=0.3, sy=0.3)

# チェーン: ~chainで全opがfast品質、+chainで末尾がforce
obj <= ~(resize(sx=0.5, sy=0.5) | resize(sx=0.3, sy=0.3))
obj <= +(resize(sx=0.5, sy=0.5) | resize(sx=0.3, sy=0.3))
```

キャッシュは `__cache__/artifacts/checkpoint/{src_hash}/{signature}.{ext}` に保存。
AudioEffectの `~` は従来通り無効化として動作する。

### Object.cache()（非推奨）

`Object.cache(path)` は非推奨です。policy/qualityベースのチェックポイントを使用してください。

### 方針: genchain は提供しない

生成系（morph_to等）のチェーン化は行わない。生成系Effectは単体でのみ使用する。

### anchor / pause / until（クロスレイヤー同期）

レイヤー間でタイミングを同期する仕組み。

```python
# レイヤーA: 幕を3秒表示してアンカーを打つ
maku = Object("maku.png")
maku.time(3) <= move(x=0.5, y=0.5, anchor="center")
anchor("curtain_done")

# レイヤーB: 幕が終わるまで待ってから登場
pause.until("curtain_done")
oni = Object("oni.png")
oni.time(3) <= move(x=0.5, y=0.5, anchor="center")
```

- `anchor(name)` ... 現在のタイムライン位置に名前付きマーカーを登録
- `pause.time(N)` ... N秒間の非描画待機
- `pause.until(name)` ... アンカー時刻まで非描画待機
- `pause.until(name, offset=N)` ... アンカー時刻+offset秒まで待機
- `obj.until(name)` ... durationをアンカー時刻まで伸長
- `obj.until(name, offset=N)` ... durationをアンカー時刻+offset秒まで伸長

```python
# offset例: アンカーから0.5秒後まで待機
pause.until("curtain_done", offset=0.5)

# 負offset: アンカーの0.1秒前まで
obj.until("curtain_done", offset=-0.1)
```

### time(name=...)（自動 start/end アンカー）

`time()` に `name` を指定すると `X.start` と `X.end` アンカーが自動生成される。

```python
obj.time(3, name="scene1")  # scene1.start=開始時刻, scene1.end=終了時刻
pause.until("scene1.end")    # scene1の終了を待つ
```

### show / show_until（同時表示）

`show()` と `show_until()` は `current_time` を進めずにオブジェクトを表示する。
複数素材を同一時刻から重ねて表示したい場合に使用する。

```python
bg.time(6) <= move(x=0.5, y=0.5, anchor="center")
overlay_a.show(6) <= move(x=0.3, y=0.3, anchor="center")  # current_time非進行
overlay_b.show_until("scene1.end") <= move(x=0.7, y=0.7)   # アンカーまで同時表示
overlay_c.show(3, priority=10) <= move(x=0.5, y=0.5)       # priority指定可
```

- `obj.show(duration)` ... current_timeを進めずにduration秒表示
- `obj.show(duration, priority=N)` ... priority指定付き
- `obj.show_until(name)` ... current_timeを進めずにアンカーまで表示
- `obj.show_until(name, offset=N)` ... offset秒ずらし

### compute（タイムライン外素材生成）

Transform/bakeable Effectを適用した中間素材をタイムライン外で生成する。
キャッシュ対応（checkpoint方式）。live Effect（move等）は使用不可。

```python
processed = Object("source.png")
processed <= resize(sx=0.5, sy=0.5) | blur(radius=3)
processed.compute()  # タイムライン外でPNG生成

# 生成した素材を通常通り配置
processed.time(3) <= move(x=0.5, y=0.5, anchor="center")

# 動画生成（duration指定）
clip = Object("source.png")
clip <= resize(sx=0.5, sy=0.5)
clip.compute(duration=3)  # WebM動画として生成
```

### テンプレート機能

字幕・吹き出し・図解をPython関数1行で生成。内部でweb Object (HTML→Playwright→webm) パイプラインを利用。

```python
# 字幕（画面下部テロップ）
s = subtitle("こんにちは！", who="Alice", duration=2.5)

# 字幕ボックス（中央配置ボックス型）
sb = subtitle_box("タイトルテキスト", duration=3.0)

# 吹き出し
b = bubble("ここがポイント！", duration=1.0, anchor=(0.6, 0.75))

# 図解
d = diagram([
    rect(0.05, 0.1, 0.4, 0.25, fill="none", stroke="#fff"),
    label(0.25, 0.22, "Step 1", fill="#fff"),
    circle(0.7, 0.3, 0.06, fill="#ff6644"),
    arrow(0.45, 0.22, 0.62, 0.3, stroke="#ffcc00"),
    spotlight(0.5, 0.5, 0.15),
], duration=3.0)
```

テンプレート共通オプション: `style={}`, `size=(w,h)`, `name=`, `debug_frames=`, `deps=[]`

diagram 図形要素:
- `rect(x, y, w, h, **kw)` ... 矩形
- `circle(x, y, r, **kw)` ... 円
- `arrow(x1, y1, x2, y2, **kw)` ... 矢印
- `label(x, y, text, **kw)` ... テキスト
- `spotlight(x, y, r, **kw)` ... スポットライト（暗幕くり抜き）

### web Object（HTML直接指定）

HTMLファイルをPlaywright経由でフレーム描画し、WebM動画として生成する。

```python
web_obj = Object("template.html",
                 duration=5.0,
                 size=(1280, 720),
                 data={"message": "Hello"},
                 deps=["style.css"])
web_obj.time(5) <= move(x=0.5, y=0.5, anchor="center")
```

- `duration` (必須) ... 表示秒数
- `size` (必須) ... キャンバスサイズ `(width, height)`
- `fps` ... フレームレート（デフォルト: Project.fps）
- `data` ... HTML/JSに渡すデータ辞書
- `name` ... 内部名称（自動生成）
- `debug_frames` ... フレーム出力デバッグ
- `deps` ... 依存ファイルリスト（変更検出用）

HTML内で `window.renderFrame(state)` 関数を定義する。
`state`: `{frame, t, u, fps, duration, width, height, data, seed}`

### 2パスアーキテクチャ

`render()` は2段階で実行される:

1. **Plan pass** ... アンカーを固定点反復で解決（cache は no-op）
2. **Render pass** ... アンカー確定済みの状態で本実行、ffmpegコマンドを構築・実行

### レイヤーの独立タイムライン

各レイヤーは0秒から独立したタイムラインを持つ。
動画全体のdurationは全レイヤーの最大値から自動算出される。

### priority による z-order 制御

`p.layer(filename, priority=N)` の `priority` で重ね順を制御する。
値が大きいほど手前に表示。記述順に依存しない。

## Object メソッド一覧

| メソッド | シグネチャ | 説明 |
|---------|----------|------|
| `time` | `time(duration=None, *, name=None)` | 表示時間設定（動画/音声は省略で自動duration） |
| `until` | `until(name, offset=0.0)` | durationをアンカー時刻+offset秒まで伸長 |
| `show` | `show(duration, *, priority=None)` | current_timeを進めずに表示 |
| `show_until` | `show_until(name, offset=0.0, *, priority=None)` | current_timeを進めずにアンカーまで表示 |
| `compute` | `compute(duration=None)` | タイムライン外で素材生成（PNG or WebM） |
| `length` | `length()` | 加工後の再生時間を返す（trim/atempo反映） |
| `split` | `split()` | `(VideoView, AudioView)` を返す |

プロパティ: `has_video`, `has_audio`, `source`, `duration`, `start_time`, `priority`

## 使い方

### main.py（構成定義）

```python
from scriptvedit import *

p = Project()
p.configure(width=1280, height=720, fps=30, background_color="black")

p.layer("bg.py", priority=0)
p.layer("onigiri.py", priority=1)

p.render("output.mp4")
```

### レイヤーファイル（例: bg.py）

```python
from scriptvedit import *

bg = Object("bg_pattern_ishigaki.jpg")
bg <= resize(sx=1, sy=1)
bg.time(6) <= move(x=0.5, y=0.5, anchor="center") \
              & scale(lambda u: lerp(1.5, 1, u)) \
              & fade(lambda u: u)
```

### time() の省略（auto duration）

動画/音声では `time()` の引数を省略すると、加工後の長さ `length()` で duration を自動決定する。
ただし呼び出し時に即 `length()` はせず、layer exec 後に確定されるため、
同じ行で `trim` 等を付けても正しく反映される。

```python
clip.time() <= trim(3)                     # duration=3（加工後長）
bgm.time() <= atrim(2) & again(0.6)       # duration=2
img.time()                                 # TypeError（画像は length を持たない）
```

### 実行

```
python main.py
```

### dry_run（コマンド確認のみ）

```python
cmd = p.render("output.mp4", dry_run=True)
# ffmpegを実行せず、コマンドリスト（list[str]）を返す
# チェックポイント/キャッシュがある場合は {"main": [...], "cache": {...}} 形式
```

### テスト

```
cd test
python test_snapshot.py        # スナップショットテスト（38テスト）
python test_snapshot.py --update  # スナップショット更新
python test_errors.py          # エラーケーステスト（66テスト）
python test01_main.py          # 個別テスト（MP4生成）
```

## 依存

- Python 3.10+
- ffmpeg（PATHに必要）
- Playwright + Chromium（テンプレート/web Object使用時）
