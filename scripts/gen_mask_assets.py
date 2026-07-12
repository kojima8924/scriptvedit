# mask/mask_wipe テスト用のマスク画像を生成するスクリプト（再現可能）
# 実行: python scripts/gen_mask_assets.py
# 生成物: assets/images/mask_gradient.png（左→右の線形グラデーション 320x240）
#         assets/images/mask_circle.png（中心が黒・外周が白の放射グラデーション 320x240）
import os
from PIL import Image

# scripts/ の1つ上がリポジトリルート
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "assets", "images")


def gen_gradient(path, w=320, h=240):
    """左(黒)→右(白)の線形グラデーション"""
    im = Image.new("L", (w, h))
    px = im.load()
    for x in range(w):
        v = round(255 * x / (w - 1))
        for y in range(h):
            px[x, y] = v
    im.save(path)
    print(f"生成: {path}")


def gen_circle(path, w=320, h=240):
    """中心(黒)→外周(白)の放射グラデーション（円形ワイプ用）"""
    im = Image.new("L", (w, h))
    px = im.load()
    cx, cy = (w - 1) / 2, (h - 1) / 2
    max_d = (cx ** 2 + cy ** 2) ** 0.5
    for x in range(w):
        for y in range(h):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            px[x, y] = round(255 * d / max_d)
    im.save(path)
    print(f"生成: {path}")


if __name__ == "__main__":
    gen_gradient(os.path.join(HERE, "mask_gradient.png"))
    gen_circle(os.path.join(HERE, "mask_circle.png"))
