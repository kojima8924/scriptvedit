# 素材台帳（assets/）

**同梱素材はすべて自作物です。** 第三者の著作物は含みません。
`scripts/generate_test_assets.py` が図形描画（Pillow）と合成音・合成映像（FFmpeg の
lavfi）だけで生成しており、生成手順そのものがリポジトリに入っています。

- ライセンス: リポジトリの **MIT ライセンスが素材にも適用されます**
  （コードと素材で条件が分かれません）。
- 用途: ライブラリのテスト用フィクスチャです。寸法・尺・ストリーム構成に
  テストが依存しているため、差し替えるときはテストも合わせて確認してください。
- 再生成: `pip install Pillow` の上で `python scripts/generate_test_assets.py`。

## 一覧

| ファイル | 仕様 | 内容 | 主な用途 |
|---|---|---|---|
| `images/shape_badge.png` | 644×800 RGBA | 角丸三角のバッジ | 汎用の被写体（最多使用）・morph の入力 |
| `images/shape_figure.png` | 1130×1130 RGBA | 緑背景の人型アイコン | morph の相手役・`chroma_key`（緑を抜く） |
| `images/shape_dots.png` | 412×356 RGBA | 水玉の楕円 | 小さめの被写体 |
| `images/shape_portrait.png` | 812×849 RGBA | 積み木風の顔 | 縦長の被写体 |
| `images/shape_starburst.png` | 845×771 RGBA | 集中線バースト | 登場演出の被写体 |
| `images/banner_wide.png` | 1573×647 RGBA | 横長バナー | 横幅の大きい素材 |
| `images/pattern_curtain.png` | 700×690 RGB | 縦縞（不透明） | 幕・背景（アルファ無し素材の代表） |
| `images/bg_pattern_tiles.jpg` | 800×450 JPEG | タイル模様 | 背景（唯一の JPEG 素材） |
| `images/mask_circle.png` | 320×240 グレー | 円マスク | `mask()` |
| `images/mask_gradient.png` | 320×240 グレー | 横グラデーション | `mask_wipe()` |
| `audio/bgm_loop.mp3` | 31.56秒 44.1kHz ステレオ | 3和音の合成音 | BGM・ループ・ダッキング |
| `audio/効果音.mp3` | 1.36秒 44.1kHz ステレオ | 減衰する打撃音 | 効果音・**非ASCIIパスの検証** |
| `video/clip_with_audio.mp4` | 5.545秒 640×360 29.97fps + AAC | 矩形が往復する映像 | 動画素材全般（映像と音声で実効尺が異なる検証を含む） |

合計 685KB。

## 注意

- `audio/効果音.mp3` の日本語ファイル名は意図的です。フィルタ文字列や
  コマンドラインでの非ASCIIパスの取り扱いをテストが検証しています。
- `video/clip_with_audio.mp4` は**音声ストリームを持ちます**。映像と音声で
  実効尺が違う場合の `length()` の挙動をテストが検証しているためです。
- 大容量の検証用動画（`assets/video/flowerbg_noaudio.mp4` 等）は git 管理外です。
  無い環境では該当テストが `pytest.skip` されます。

## 素材を追加・差し替えるとき

1. `scripts/generate_test_assets.py` に生成処理を追加して再生成する
   （第三者の素材を持ち込まない。持ち込む場合は出典・ライセンス・帰属を
   本表へ必ず記録する）
2. 内容が変わると内容ハッシュ＝キャッシュ鍵が変わるため、スナップショットを
   再生成する（`pytest tests/test_snapshot.py --snapshot-update`。差分が
   鍵ハッシュのみであることを確認してから）
