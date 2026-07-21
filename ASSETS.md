# 素材台帳（assets/ の追跡バイナリの出典・利用条件）

リポジトリの **MIT ライセンスはソースコードにのみ適用**され、`assets/` 配下の
画像・音声・動画素材には**適用されない**。各素材は下表の出典元の利用条件に従う。

これらの素材はライブラリの**テスト用フィクスチャ**としてのみ同梱している
（スナップショットテストが内容ハッシュを参照するため差し替えにくい）。
自分の動画制作にはこの素材を使わず、各自の `assets/` / 共有素材ライブラリを使うこと。

## 台帳

状態の凡例: ✅=出典・条件確認済み / ⚠=推定出典あり・**要確認** / ❓=出典不明・**要確認**

| ファイル | 種別 | 推定出典 | 状態 | 備考 |
|---|---|---|---|---|
| `assets/images/onigiri_tenmusu.png` | 画像 | いらすとや | ⚠ | ファイル名の命名様式より推定 |
| `assets/images/mushi_tentoumushi.png` | 画像 | いらすとや | ⚠ | 同上 |
| `assets/images/nigaoe_franz_kafka.png` | 画像 | いらすとや | ⚠ | 同上 |
| `assets/images/virus_message_fuyoufukyu_gaisyutsu.png` | 画像 | いらすとや | ⚠ | 同上 |
| `assets/images/pop_shinsyakaijin_ganbare.png` | 画像 | いらすとや | ⚠ | 同上 |
| `assets/images/figure_cafe.png` | 画像 | いらすとや | ⚠ | 同上 |
| `assets/images/pattern_teishiki_maku.png` | 画像 | いらすとや | ⚠ | 同上 |
| `assets/images/bg_pattern_ishigaki.jpg` | 画像 | フリー背景素材サイト | ❓ | 取得元URL不明 |
| `assets/images/mask_circle.png` | 画像 | 自作（プログラム生成） | ⚠ | マスク用の単純図形 |
| `assets/images/mask_gradient.png` | 画像 | 自作（プログラム生成） | ⚠ | マスク用グラデーション |
| `assets/audio/Impact-38.mp3` | 音声 | OtoLogic（フリー効果音） | ⚠ | ファイル名の命名様式より推定。CC BY 4.0（クレジット必須）の可能性 |
| `assets/audio/ビックリ音.mp3` | 音声 | フリー効果音サイト | ❓ | 取得元不明。再配布不可の規約が多い分野なので優先的に確認 |
| `assets/video/fox_noaudio.mp4` | 動画 | フリー動画素材サイト | ❓ | 取得元URL不明 |

※ `assets/images/computer_screen_programming.png` と `assets/audio/nc*.mp3` は
ライセンス未確認のため **git 管理外**（`.gitignore` 済み。ローカルテスト専用）。

## 未確認素材の扱い（TODO）

- [ ] ⚠/❓ の各素材について、取得元URL・作者・利用条件を確認して本表を更新する
- [ ] 再配布根拠を確認できない素材は、明確な許諾のある素材
      （自作・CC0 等）へ差し替える（差し替え時はスナップショットの
      内容ハッシュ更新が必要: `pytest tests/test_snapshot.py --snapshot-update`）
- [ ] いらすとや素材は規約（商用条件・「素材の再配布」の解釈）を確認する

## 素材を追加・差し替えるとき

1. 本表へ行を追加する（出典URL・ライセンス・改変内容を必ず記録）
2. 再配布根拠を文書で確認できない素材はコミットしない
   （ローカル限定にする場合は `.gitignore` へ追加して理由を書く）
