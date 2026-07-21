# -*- coding: utf-8 -*-
"""テスト用素材(assets/)を生成する。

同梱素材はすべてこのスクリプトの出力＝自作物で、第三者の権利が一切絡まない
（ASSETS.md 参照）。素材を差し替えたくなったらここを直して再実行する。

    pip install Pillow          # 画像生成に必要
    python scripts/generate_test_assets.py

生成物の寸法・尺・ストリーム構成はテスト（スナップショットの scale/pad 計算、
length() の期待値など）が依存しているため、変更するときはテストも合わせて直す。
再実行するとエンコーダ由来のバイト差が出ることがあり、その場合は内容ハッシュ＝
キャッシュ鍵が変わるのでスナップショットの再生成が必要
（pytest tests/test_snapshot.py --snapshot-update）。
"""
import math
import os
import subprocess
import sys

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    sys.exit("Pillow が必要です: pip install Pillow")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "assets", "images")
AUDIO = os.path.join(ROOT, "assets", "audio")
VIDEO = os.path.join(ROOT, "assets", "video")

# 素材の色（テスト時に目視・画素検証しやすい彩度の高い組み合わせ）
INK = (28, 36, 58, 255)
CREAM = (243, 236, 220, 255)
CORAL = (226, 92, 74, 255)
TEAL = (44, 158, 158, 255)
GOLD = (232, 178, 58, 255)
GREEN = (46, 174, 92, 255)
PLUM = (118, 74, 140, 255)


def _save_png(img, name):
    path = os.path.join(IMAGES, name)
    img.save(path, "PNG", optimize=True)
    print(f"  {name}  {img.size[0]}x{img.size[1]} {img.mode}")


def gen_shape_badge():
    """644x800 RGBA — 汎用の被写体。角丸三角形のバッジに図形を重ねる。

    最も多くのテストで「1つの画像素材」として使われる。morph の入力にも
    なるため、不透明領域がまとまって存在し、内部に濃淡の差がある構図にする。
    """
    w, h = 644, 800
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 角丸三角形の本体
    cx, cy, r = w / 2, h * 0.55, w * 0.42
    pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
           for a in (-90, 30, 150)]
    d.polygon(pts, fill=CORAL)
    d.line(pts + [pts[0]], fill=INK, width=18, joint="curve")
    # 内側の円と帯
    d.ellipse([cx - r * 0.34, cy - r * 0.18, cx + r * 0.34, cy + r * 0.5],
              fill=CREAM, outline=INK, width=12)
    d.rectangle([w * 0.18, h * 0.80, w * 0.82, h * 0.88], fill=TEAL, outline=INK,
                width=10)
    _save_png(img, "shape_badge.png")


def gen_shape_figure():
    """1130x1130 RGBA — 人型の抽象アイコン。morph/合成の相手役。

    chroma_key テストの被写体でもあるため、背景側に緑の面を持たせる。
    """
    s = 1130
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([s * 0.06, s * 0.06, s * 0.94, s * 0.94], radius=int(s * 0.08),
                        fill=GREEN)          # 緑背景（chroma_key の対象）
    d.ellipse([s * 0.36, s * 0.16, s * 0.64, s * 0.44], fill=CREAM, outline=INK,
              width=14)                       # 頭
    d.rounded_rectangle([s * 0.28, s * 0.48, s * 0.72, s * 0.86], radius=int(s * 0.10),
                        fill=PLUM, outline=INK, width=14)   # 胴
    d.ellipse([s * 0.44, s * 0.58, s * 0.56, s * 0.70], fill=GOLD)
    _save_png(img, "shape_figure.png")


def gen_shape_dots():
    """412x356 RGBA — 小さめの被写体（水玉の楕円）"""
    w, h = 412, 356
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([10, 10, w - 10, h - 10], fill=CORAL, outline=INK, width=12)
    d.line([w / 2, 12, w / 2, h - 12], fill=INK, width=10)
    for i, (fx, fy) in enumerate([(0.28, 0.32), (0.70, 0.30), (0.34, 0.66),
                                  (0.66, 0.68), (0.50, 0.48)]):
        rr = 26 if i % 2 == 0 else 20
        d.ellipse([w * fx - rr, h * fy - rr, w * fx + rr, h * fy + rr], fill=INK)
    _save_png(img, "shape_dots.png")


def gen_shape_portrait():
    """812x849 RGBA — 縦長の被写体（積み木の肖像）"""
    w, h = 812, 849
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([w * 0.18, h * 0.10, w * 0.82, h * 0.62], radius=40,
                        fill=CREAM, outline=INK, width=14)
    for fx in (0.36, 0.64):                    # 目
        d.ellipse([w * fx - 34, h * 0.30 - 34, w * fx + 34, h * 0.30 + 34], fill=INK)
    d.arc([w * 0.34, h * 0.38, w * 0.66, h * 0.54], start=10, end=170,
          fill=INK, width=14)                  # 口
    d.rectangle([w * 0.26, h * 0.64, w * 0.74, h * 0.92], fill=TEAL, outline=INK,
                width=14)                      # 肩
    _save_png(img, "shape_portrait.png")


def gen_shape_starburst():
    """845x771 RGBA — 集中線バースト（登場演出の被写体）"""
    w, h = 845, 771
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = w / 2, h / 2
    outer, inner = min(w, h) * 0.48, min(w, h) * 0.24
    pts = []
    for i in range(24):
        a = math.radians(i * 15)
        rr = outer if i % 2 == 0 else inner
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=GOLD, outline=INK)
    d.ellipse([cx - inner * 0.7, cy - inner * 0.7, cx + inner * 0.7, cy + inner * 0.7],
              fill=CORAL, outline=INK, width=12)
    _save_png(img, "shape_starburst.png")


def gen_banner_wide():
    """1573x647 RGBA — 横長のバナー（横幅の大きい素材の代表）"""
    w, h = 1573, 647
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, w - 8, h - 8], radius=48, fill=PLUM, outline=INK,
                        width=14)
    d.rectangle([w * 0.05, h * 0.40, w * 0.95, h * 0.60], fill=CREAM)
    for i in range(9):                          # 目盛り状のブロック
        x = w * (0.07 + i * 0.098)
        d.rectangle([x, h * 0.18, x + w * 0.055, h * 0.32], fill=GOLD)
    _save_png(img, "banner_wide.png")


def gen_pattern_curtain():
    """700x690 RGB(不透明) — 幕・背景に使う縦縞パターン"""
    w, h = 700, 690
    img = Image.new("RGB", (w, h), INK[:3])
    d = ImageDraw.Draw(img)
    for i in range(14):
        x = w * i / 14
        color = CORAL[:3] if i % 2 == 0 else PLUM[:3]
        d.rectangle([x, 0, x + w / 14 - 6, h], fill=color)
    d.rectangle([0, 0, w, h * 0.06], fill=GOLD[:3])
    _save_png(img, "pattern_curtain.png")


def gen_bg_tiles():
    """800x450 JPEG — 背景用のタイル模様（唯一のJPEG素材）"""
    w, h = 800, 450
    img = Image.new("RGB", (w, h), CREAM[:3])
    d = ImageDraw.Draw(img)
    tile = 50
    for row in range(h // tile + 1):
        for col in range(w // tile + 1):
            if (row + col) % 2 == 0:
                continue
            x, y = col * tile, row * tile
            shade = 200 - (row * 7 + col * 3) % 60
            d.rectangle([x + 3, y + 3, x + tile - 3, y + tile - 3],
                        fill=(shade, shade - 25, shade - 60))
    path = os.path.join(IMAGES, "bg_pattern_tiles.jpg")
    img.save(path, "JPEG", quality=88, subsampling=0)
    print(f"  bg_pattern_tiles.jpg  {w}x{h} JPEG")


def gen_masks():
    """320x240 グレースケール — mask()/mask_wipe() 用（白=不透明）"""
    w, h = 320, 240
    circle = Image.new("L", (w, h), 0)
    ImageDraw.Draw(circle).ellipse([w * 0.18, h * 0.06, w * 0.82, h * 0.94], fill=255)
    circle = circle.filter(ImageFilter.GaussianBlur(2))
    _save_png(circle, "mask_circle.png")

    grad = Image.new("L", (w, h))
    grad.putdata([int(255 * (x / (w - 1))) for _ in range(h) for x in range(w)])
    _save_png(grad, "mask_gradient.png")


def _ffmpeg(args, out):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args, out], check=True)
    print(f"  {os.path.basename(out)}")


def gen_audio():
    """BGM相当(31.6秒)と効果音(1.36秒)。lavfi の合成音なので完全に自作物。

    非ASCIIパスの取り扱い（drawtext/フィルタのエスケープ）をテストが検証して
    いるため、効果音は日本語ファイル名のままにする。
    """
    os.makedirs(AUDIO, exist_ok=True)
    # BGM: 3和音のゆるやかなループ（長さは旧素材と揃える）
    _ffmpeg([
        "-f", "lavfi", "-i",
        "aevalsrc='0.28*sin(2*PI*220*t)+0.20*sin(2*PI*330*t)+0.14*sin(2*PI*440*t)'"
        ":d=31.556:s=44100:c=stereo",
        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100",
        "-ac", "2", "-t", "31.556",
    ], os.path.join(AUDIO, "bgm_loop.mp3"))
    # 効果音: 減衰する打撃音
    _ffmpeg([
        "-f", "lavfi", "-i",
        "aevalsrc='0.9*exp(-6*t)*sin(2*PI*(900-500*t)*t)':d=1.358:s=44100:c=stereo",
        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-t", "1.358",
    ], os.path.join(AUDIO, "効果音.mp3"))


def gen_video():
    """640x360 / 29.97fps / 5.545秒 / 映像+AAC音声のクリップ。

    尺 5.545 は length() 系テストが期待値に使う。音声ストリームを持つのも
    仕様（映像と音声で実効尺が違う場合の挙動をテストが検証している）。
    """
    os.makedirs(VIDEO, exist_ok=True)
    _ffmpeg([
        "-f", "lavfi", "-i",
        "color=c=0x1C243A:s=640x360:r=30000/1001:d=5.545",
        "-f", "lavfi", "-i",
        "sine=frequency=330:sample_rate=48000:duration=5.545",
        "-filter_complex",
        # 左右に往復する矩形 + 中央の円（フレームごとに絵が変わる素材にする）
        "[0:v]drawbox=x='(w-120)*abs(sin(t))':y=120:w=120:h=120:color=0xE25C4A@1:t=fill,"
        "drawbox=x=260:y=40:w=120:h=60:color=0xE8B23A@1:t=fill,format=yuv420p[v]",
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-threads", "1",
        "-c:a", "aac", "-b:a", "96k", "-t", "5.545",
    ], os.path.join(VIDEO, "clip_with_audio.mp4"))


def main():
    os.makedirs(IMAGES, exist_ok=True)
    print("画像:")
    gen_shape_badge()
    gen_shape_figure()
    gen_shape_dots()
    gen_shape_portrait()
    gen_shape_starburst()
    gen_banner_wide()
    gen_pattern_curtain()
    gen_bg_tiles()
    gen_masks()
    print("音声:")
    gen_audio()
    print("動画:")
    gen_video()
    print("完了。テストを回して寸法・尺の前提が保たれているか確認すること:")
    print("  python -m scriptvedit cache --clear && pytest tests/ -q")


if __name__ == "__main__":
    main()
