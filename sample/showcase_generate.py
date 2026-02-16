"""ポートフォリオ用ショーケーススライド生成（PIL）"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slides")
os.makedirs(OUT, exist_ok=True)

# --- 色 ---
BG = (18, 18, 30)
BG_CODE = (30, 30, 50)
ACCENT = (100, 140, 255)
ACCENT2 = (255, 140, 80)
WHITE = (240, 240, 245)
DIM = (160, 165, 180)
GREEN = (120, 220, 140)
YELLOW = (240, 220, 100)
CYAN = (100, 220, 240)
PINK = (240, 130, 180)

# --- フォント ---
_FONTS = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")

def _jp(size, bold=False):
    try:
        return ImageFont.truetype(os.path.join(_FONTS, "meiryo.ttc"), size, index=1 if bold else 0)
    except Exception:
        return ImageFont.load_default()

def _mono(size):
    try:
        return ImageFont.truetype(os.path.join(_FONTS, "consola.ttf"), size)
    except Exception:
        return _jp(size)

# --- 描画ヘルパー ---
def _center(draw, y, text, font, fill=WHITE):
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(((W - (bbox[2] - bbox[0])) // 2, y), text, fill=fill, font=font)

def _accent_line(draw, y, w=280):
    x0 = (W - w) // 2
    draw.line([(x0, y), (x0 + w, y)], fill=ACCENT, width=3)

def _code_block(draw, x, y, w, h, lines, mono, line_h=28):
    """コードブロック描画。linesは [(text, color), ...] のリストか文字列"""
    jp_fallback = _jp(mono.size)  # 日本語フォールバック
    draw.rounded_rectangle([x, y, x + w, y + h], radius=12, fill=BG_CODE)
    py = y + 18
    for line in lines:
        if isinstance(line, list):
            px = x + 24
            for seg_text, seg_color in line:
                font = jp_fallback if any(ord(c) > 127 for c in seg_text) else mono
                draw.text((px, py), seg_text, fill=seg_color, font=font)
                bbox = draw.textbbox((0, 0), seg_text, font=font)
                px += bbox[2] - bbox[0]
        else:
            font = jp_fallback if any(ord(c) > 127 for c in line) else mono
            draw.text((x + 24, py), line, fill=DIM, font=font)
        py += line_h

def _feature_bullet(draw, x, y, text, font, icon_color=ACCENT):
    draw.ellipse([x, y + 6, x + 10, y + 16], fill=icon_color)
    draw.text((x + 20, y), text, fill=WHITE, font=font)


# ============================================================
# スライド1: タイトル
# ============================================================
def slide_title():
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    _center(draw, 250, "scriptvedit", _jp(80, bold=True), ACCENT)
    _accent_line(draw, 355, 360)
    _center(draw, 400, "Python DSL for Video Editing", _jp(36), DIM)
    _center(draw, 480, "FFmpeg backend  /  Expr compiler  /  27 Easings", _jp(22), DIM)

    img.save(os.path.join(OUT, "slide_01_title.png"))
    print("  slide_01_title.png")


# ============================================================
# スライド2: DSL構文（左側にコード、右側は空けてオブジェクト配置用）
# ============================================================
def slide_syntax():
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    mono = _mono(22)
    h1 = _jp(38, bold=True)
    body = _jp(22)

    draw.text((80, 50), "直感的な DSL 構文", font=h1, fill=ACCENT)
    draw.line([(80, 105), (400, 105)], fill=ACCENT, width=2)

    # 演算子説明
    ops = [
        ("obj <= transform", "Transform 適用", ACCENT2),
        ("t1 | t2", "Transform 連結", ACCENT2),
        ("e1 & e2", "Effect 合成", GREEN),
        ("obj.time(N) <= effect", "時間付きEffect", GREEN),
    ]
    for i, (code, desc, color) in enumerate(ops):
        y = 140 + i * 42
        draw.text((100, y), code, fill=color, font=mono)
        draw.text((500, y), desc, fill=DIM, font=body)

    # コードブロック
    code_lines = [
        [("# Transform chain", DIM)],
        [("obj", WHITE), (" <= ", ACCENT2), ("resize", GREEN), ("(sx=", WHITE),
         ("0.5", CYAN), (") | ", ACCENT2), ("rotate", GREEN), ("(deg=", WHITE), ("45", CYAN), (")", WHITE)],
        [],
        [("# 時間変化する Effect", DIM)],
        [("obj", WHITE), (".time(", WHITE), ("6", CYAN), (") <= ", ACCENT2), ("move", GREEN), ("(", WHITE)],
        [("    x=", WHITE), ("lambda", PINK), (" u: ", WHITE), ("0.5", CYAN),
         (" + ", WHITE), ("0.3", CYAN), (" * ", WHITE), ("sin", GREEN), ("(u * PI)", WHITE), (",", WHITE)],
        [("    y=", WHITE), ("0.5", CYAN), (", anchor=", WHITE), ('"center"', YELLOW), (",", WHITE)],
        [(")", WHITE), (" & ", GREEN), ("fade", GREEN), ("(", WHITE),
         ("lambda", PINK), (" u: ", WHITE), ("1", CYAN), (" - u * ", WHITE), ("0.3", CYAN), (")", WHITE)],
    ]
    _code_block(draw, 60, 340, 1060, 290, code_lines, mono)

    # 右側ラベル（オブジェクトが来る場所の上）
    draw.text((1220, 340), "実行結果 ->", font=_jp(20), fill=DIM)

    img.save(os.path.join(OUT, "slide_02_syntax.png"))
    print("  slide_02_syntax.png")


# ============================================================
# スライド3: 新機能（左側にコード/リスト、右側にオブジェクト配置用）
# ============================================================
def slide_features():
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    mono = _mono(22)
    h1 = _jp(38, bold=True)
    body = _jp(22)

    draw.text((80, 50), "高度なアニメーション機能", font=h1, fill=ACCENT)
    draw.line([(80, 105), (480, 105)], fill=ACCENT, width=2)

    # 機能リスト
    features = [
        "27種のイージング関数",
        "キーフレーム補間",
        "シーケンス制御 (phase / repeat / bounce)",
        "Expr チェーンメソッド (.smooth / .map)",
        "定数畳み込み最適化",
        "字幕・吹き出し Web テンプレート",
    ]
    for i, feat in enumerate(features):
        _feature_bullet(draw, 100, 140 + i * 40, feat, body)

    # コードブロック
    code_lines = [
        [("# イージング + キーフレーム", DIM)],
        [("obj", WHITE), (".time(", WHITE), ("6", CYAN), (") <= ", ACCENT2), ("move", GREEN), ("(", WHITE)],
        [("    x=", WHITE), ("keyframes", GREEN), ("(", WHITE)],
        [("        (", WHITE), ("0", CYAN), (", ", WHITE), ("0.1", CYAN),
         ("), (", WHITE), ("0.5", CYAN), (", ", WHITE), ("0.5", CYAN),
         ("), (", WHITE), ("1", CYAN), (", ", WHITE), ("0.9", CYAN), (")", WHITE)],
        [("    ), anchor=", WHITE), ('"center"', YELLOW), (",", WHITE)],
        [(")", WHITE), (" & ", GREEN), ("scale", GREEN), ("(", WHITE),
         ("apply_easing", GREEN), ("(", WHITE)],
        [("    ", WHITE), ("ease_in_out_back", CYAN), (", ", WHITE), ("0.3", CYAN),
         (", ", WHITE), ("1.0", CYAN), (")", WHITE)],
        [(")", WHITE)],
    ]
    _code_block(draw, 60, 410, 1060, 290, code_lines, mono)

    # 右側ラベル
    draw.text((1220, 410), "実行結果 ->", font=_jp(20), fill=DIM)

    img.save(os.path.join(OUT, "slide_03_features.png"))
    print("  slide_03_features.png")


# ============================================================
# スライド4: クロージング
# ============================================================
def slide_closing():
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    _center(draw, 300, "scriptvedit", _jp(64, bold=True), ACCENT)
    _accent_line(draw, 385, 320)

    # テックスタック
    techs = ["Python 3.10+", "FFmpeg 7/8", "Playwright", "MIT License"]
    total_w = sum(draw.textbbox((0, 0), t, font=_jp(22))[2] for t in techs) + 60 * (len(techs) - 1)
    sx = (W - total_w) // 2
    for t in techs:
        bbox = draw.textbbox((0, 0), t, font=_jp(22))
        tw = bbox[2] - bbox[0]
        draw.rounded_rectangle([sx - 12, 430, sx + tw + 12, 470], radius=8, outline=ACCENT, width=1)
        draw.text((sx, 436), t, fill=DIM, font=_jp(22))
        sx += tw + 60

    _center(draw, 540, "github.com/kojima8924/scriptvedit", _jp(24), DIM)

    img.save(os.path.join(OUT, "slide_04_closing.png"))
    print("  slide_04_closing.png")


# ============================================================
# ウォーターマーク (透過PNG)
# ============================================================
def watermark():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _jp(20)
    text = "Made with scriptvedit"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    # 右下に半透明テキスト
    draw.text((W - tw - 30, H - 45), text, fill=(200, 200, 220, 160), font=font)
    img.save(os.path.join(OUT, "watermark.png"))
    print("  watermark.png")


if __name__ == "__main__":
    print("スライド生成中...")
    slide_title()
    slide_syntax()
    slide_features()
    slide_closing()
    watermark()
    print("完了")
