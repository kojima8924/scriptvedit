"""
morph.py - 最適輸送 + ワープ場によるモーフィング動画生成

アルゴリズム:
  1. 両画像の不透明ピクセルをサブサンプリング
  2. ハンガリアン法で最適輸送（ピクセルの対応関係）を計算
  3. 対応関係からRBF（薄板スプライン）補間で滑らかなワープ場（変位場）を構成
  4. ワープ場で両画像を変形 → クロスディゾルブで全ピクセル合成

使い方:
    python morph.py a.png b.png -o output.mp4

必要ライブラリ:
    pip install numpy pillow scipy opencv-python tqdm
"""

import argparse
import inspect
import os
import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment
from scipy.interpolate import RBFInterpolator
import cv2
from tqdm import tqdm


# ============================================================
# 定数
# ============================================================

# MORPH_PARAM_KEYS（**params の既知キー）は _prepare_morph のシグネチャから
# 導出する（定義は _prepare_morph の直後）。二重管理を避けるため手書きしない

# 実効サンプル数 Na+Nb の警告閾値。コスト行列が (Na+Nb)^2 float32、
# ハンガリアン法が O(N^3) のため、これを超えるとメモリ・時間が急増する
MORPH_SAMPLES_WARN = 16000

# RBF の smoothing 下限（0 だと補間行列が特異になり得る）
MIN_SMOOTHING = 1e-6


# ============================================================
# 画像読み込み・ピクセル抽出
# ============================================================

def load_images(path_a: str, path_b: str):
    """2つの画像を読み込み、同じキャンバスサイズに中央配置する"""
    img_a = Image.open(path_a).convert("RGBA")
    img_b = Image.open(path_b).convert("RGBA")

    w = max(img_a.width, img_b.width)
    h = max(img_a.height, img_b.height)

    def center_on_canvas(img, cw, ch):
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ox = (cw - img.width) // 2
        oy = (ch - img.height) // 2
        canvas.paste(img, (ox, oy))
        return np.array(canvas)

    return center_on_canvas(img_a, w, h), center_on_canvas(img_b, w, h), (w, h)


def extract_pixels(img_array: np.ndarray):
    """不透明ピクセルの座標(x,y)と色(RGBA)を抽出"""
    mask = img_array[:, :, 3] > 0
    ys, xs = np.where(mask)
    return np.column_stack([xs, ys]).astype(np.float64), img_array[mask].astype(np.float64)


def subsample(positions, colors, max_n, rng):
    """ピクセル数がmax_nを超える場合、ランダムにサブサンプリング"""
    if len(positions) <= max_n:
        return positions, colors
    idx = rng.choice(len(positions), size=max_n, replace=False)
    return positions[idx], colors[idx]


# ============================================================
# 最適輸送（ハンガリアン法）
# ============================================================

def solve_transport(pos_a, col_a, pos_b, col_b, canvas_size,
                    w_move=1.0, w_color=0.3, w_vanish=1.5):
    """
    拡張コスト行列 (Na+Nb) x (Na+Nb) でハンガリアン法を解く

    返値: src_pos, dst_pos, src_col, dst_col
      - 移動: src→dst に位置・色が変化
      - 消滅: src_pos=dst_pos, dst_col のα=0（フェードアウト）
      - 出現: src_pos=dst_pos, src_col のα=0（フェードイン）
    """
    na, nb = len(pos_a), len(pos_b)
    if na == 0 and nb == 0:
        return (np.empty((0, 2)), np.empty((0, 2)),
                np.empty((0, 4)), np.empty((0, 4)))

    max_dim = float(max(canvas_size))
    N = na + nb
    print(f"  コスト行列: {N}x{N}（{na} → {nb}）")

    cost = np.zeros((N, N), dtype=np.float32)
    if na > 0 and nb > 0:
        dx = pos_a[:, 0:1] - pos_b[:, 0:1].T
        dy = pos_a[:, 1:2] - pos_b[:, 1:2].T
        spatial = np.sqrt(dx**2 + dy**2, dtype=np.float32) / max_dim

        ca = (col_a / 255.0).astype(np.float32)
        cb = (col_b / 255.0).astype(np.float32)
        color_sq = np.zeros((na, nb), dtype=np.float32)
        for c in range(4):
            dc = ca[:, c:c+1] - cb[:, c:c+1].T
            color_sq += dc * dc
        cost[:na, :nb] = w_move * spatial + w_color * np.sqrt(color_sq)

    cost[:na, nb:] = w_vanish
    cost[na:, :nb] = w_vanish

    print("  ハンガリアン法で計算中...")
    row_ind, col_ind = linear_sum_assignment(cost)

    out_sp, out_dp, out_sc, out_dc = [], [], [], []
    n_move = n_vanish = n_appear = 0

    for r, c in zip(row_ind, col_ind):
        if r < na and c < nb:
            out_sp.append(pos_a[r]); out_dp.append(pos_b[c])
            out_sc.append(col_a[r]); out_dc.append(col_b[c])
            n_move += 1
        elif r < na:
            out_sp.append(pos_a[r]); out_dp.append(pos_a[r])
            out_sc.append(col_a[r])
            f = col_a[r].copy(); f[3] = 0.0; out_dc.append(f)
            n_vanish += 1
        elif c < nb:
            out_sp.append(pos_b[c]); out_dp.append(pos_b[c])
            g = col_b[c].copy(); g[3] = 0.0; out_sc.append(g)
            out_dc.append(col_b[c])
            n_appear += 1

    print(f"  結果: 移動={n_move}, 消滅={n_vanish}, 出現={n_appear}")
    return (np.array(out_sp), np.array(out_dp),
            np.array(out_sc), np.array(out_dc))


# ============================================================
# ワープ場の構築（RBF 薄板スプライン補間）
# ============================================================

def build_warp_fields(src_pos, dst_pos, src_col, dst_col,
                      canvas_size, grid_step=8, smoothing=10.0):
    """
    スパースな制御点の対応関係から、画像全体の滑らかな変位場を構築する

    1. ソース側制御点（移動+消滅）→ ソース変位場 (dx_s, dy_s)
       移動点: 変位 = dst - src,  消滅点: 変位 = 0
    2. ターゲット側制御点（移動+出現）→ ターゲット変位場 (dx_t, dy_t)
       移動点: 変位 = src - dst,  出現点: 変位 = 0

    RBF補間で粗いグリッド上に変位を求め、バイリニアで全解像度に拡大
    """
    w, h = canvas_size
    delta = dst_pos - src_pos

    # ソース側: src_col の α > 0 の点（移動＋消滅）
    src_mask = src_col[:, 3] > 0
    src_ctrl = src_pos[src_mask]
    src_disp = delta[src_mask]

    # ターゲット側: dst_col の α > 0 の点（移動＋出現）
    tgt_mask = dst_col[:, 3] > 0
    tgt_ctrl = dst_pos[tgt_mask]
    tgt_disp = -delta[tgt_mask]

    # 境界アンカー（変位0で固定、ワープの発散を防止）
    n_edge = 14
    anchors = []
    for v in np.linspace(0, w - 1, n_edge):
        anchors.extend([[v, 0], [v, h - 1]])
    for v in np.linspace(0, h - 1, n_edge):
        anchors.extend([[0, v], [w - 1, v]])
    anchors = np.array(anchors)
    anchor_d = np.zeros((len(anchors), 2))

    # 評価グリッド（粗い格子点）
    gw = max(w // grid_step, 4)
    gh = max(h // grid_step, 4)
    gx, gy = np.meshgrid(np.linspace(0, w - 1, gw),
                          np.linspace(0, h - 1, gh))
    grid_pts = np.column_stack([gx.ravel(), gy.ravel()])

    # smoothing=0 は RBF の補間行列が特異になり得るため下限を設ける
    if smoothing < MIN_SMOOTHING:
        print(f"  警告: smoothing={smoothing} は小さすぎるため "
              f"{MIN_SMOOTHING} に引き上げます（特異行列の防止）")
        smoothing = MIN_SMOOTHING

    def interpolate_field(ctrl, disp, label):
        """制御点+境界アンカー → RBF補間 → フル解像度変位場"""
        ctrl_all = np.vstack([ctrl, anchors])
        disp_all = np.vstack([disp, anchor_d])

        print(f"    {label}: 制御点{len(ctrl)}個 + アンカー{len(anchors)}個")
        rbf = RBFInterpolator(
            ctrl_all, disp_all,
            kernel="thin_plate_spline",
            smoothing=smoothing,
        )
        vals = rbf(grid_pts)  # (gw*gh, 2)
        dx = vals[:, 0].reshape(gh, gw).astype(np.float32)
        dy = vals[:, 1].reshape(gh, gw).astype(np.float32)
        # バイリニア補間でフル解像度に拡大
        dx_full = cv2.resize(dx, (w, h), interpolation=cv2.INTER_LINEAR)
        dy_full = cv2.resize(dy, (w, h), interpolation=cv2.INTER_LINEAR)
        return dx_full, dy_full

    dx_s, dy_s = interpolate_field(src_ctrl, src_disp, "ソース側")
    dx_t, dy_t = interpolate_field(tgt_ctrl, tgt_disp, "ターゲット側")

    return dx_s, dy_s, dx_t, dy_t


# ============================================================
# レンダリング
# ============================================================

def premultiply_alpha(rgba: np.ndarray) -> np.ndarray:
    """アルファ事前乗算（ワープ時の境界ハロー防止）"""
    f = rgba.astype(np.float32)
    a = f[:, :, 3:4] / 255.0
    f[:, :, :3] *= a
    return f


def ease_in_out(t: float) -> float:
    """Hermite 補間によるスムーズなイージング"""
    return t * t * (3.0 - 2.0 * t)


def _prepare_morph(path_a, path_b, *,
                   max_pixels=2000, w_move=1.0, w_color=0.3, w_vanish=1.5,
                   grid_step=8, smoothing=10.0):
    """手順1〜4（画像読み込み→ピクセル抽出→最適輸送→ワープ場構築）の共通処理

    返値: arr_a, arr_b, canvas, dx_s, dy_s, dx_t, dy_t
    """
    # --- 1. 画像読み込み ---
    print("[1/5] 画像読み込み...")
    arr_a, arr_b, canvas = load_images(path_a, path_b)

    # --- 2. ピクセル抽出 + サブサンプリング ---
    print("[2/5] ピクセル抽出...")
    pos_a, col_a = extract_pixels(arr_a)
    pos_b, col_b = extract_pixels(arr_b)
    print(f"  A: {len(pos_a):,}px,  B: {len(pos_b):,}px")

    rng = np.random.default_rng(42)
    pos_a_s, col_a_s = subsample(pos_a, col_a, max_pixels, rng)
    pos_b_s, col_b_s = subsample(pos_b, col_b, max_pixels, rng)
    print(f"  サンプリング後: A={len(pos_a_s):,}, B={len(pos_b_s):,}")

    # 実効サンプル数（max_pixels の指定値でなく実際の N）で計算量を警告する。
    # ハードエラーにはしない（遅くても完走させ、既存スクリプトを壊さない）
    n_total = len(pos_a_s) + len(pos_b_s)
    if n_total > MORPH_SAMPLES_WARN:
        est_gb = (n_total * n_total * 4) / (1024 ** 3)
        print(f"  警告: サンプル数 {n_total:,} は推奨上限 {MORPH_SAMPLES_WARN:,} を超えています"
              f"（コスト行列 約{est_gb:.1f}GB + O(N^3) の最適輸送計算で数十分かかる可能性）。"
              f" max_pixels を下げることを推奨します")

    # --- 3. 最適輸送 ---
    print("[3/5] 最適輸送...")
    sp, dp, sc, dc = solve_transport(
        pos_a_s, col_a_s, pos_b_s, col_b_s, canvas,
        w_move=w_move, w_color=w_color, w_vanish=w_vanish,
    )

    # --- 4. ワープ場構築 ---
    print("[4/5] ワープ場構築（RBF補間）...")
    dx_s, dy_s, dx_t, dy_t = build_warp_fields(
        sp, dp, sc, dc, canvas,
        grid_step=grid_step, smoothing=smoothing,
    )

    return arr_a, arr_b, canvas, dx_s, dy_s, dx_t, dy_t


# **params で受け付ける既知キー（タイポ検出用）。
# _prepare_morph のキーワード専用引数から導出し、二重管理を避ける
MORPH_PARAM_KEYS = frozenset(
    inspect.signature(_prepare_morph).parameters) - {"path_a", "path_b"}


# ============================================================
# RGBA フレーム生成（scriptvedit統合用）
# ============================================================

def generate_rgba_frames(path_a, path_b, out_dir, n_frames, blend_fn=None, **params):
    """RGBA PNG連番を生成（背景合成なし、透明保持）

    Args:
        path_a: ソース画像パス
        path_b: ターゲット画像パス
        out_dir: 出力ディレクトリ（frame_00000.png 〜）
        n_frames: フレーム数
        blend_fn: ブレンド関数 t→et（Noneでease_in_out）
        **params: max_pixels, w_move, w_color, w_vanish, grid_step, smoothing
    """
    if blend_fn is None:
        blend_fn = ease_in_out

    # 未知キーはタイポの可能性が高いため明示的にエラーにする
    unknown = set(params) - MORPH_PARAM_KEYS
    if unknown:
        raise ValueError(
            f"未知のパラメータ: {sorted(unknown)}"
            f"（有効なキー: {sorted(MORPH_PARAM_KEYS)}）"
        )

    # --- 1〜4. 読み込み→抽出→最適輸送→ワープ場構築（共通処理） ---
    arr_a, arr_b, canvas, dx_s, dy_s, dx_t, dy_t = _prepare_morph(
        path_a, path_b, **params)
    w, h = canvas

    # --- 5. RGBAフレーム生成 ---
    src_pm = premultiply_alpha(arr_a)
    tgt_pm = premultiply_alpha(arr_b)
    ident_x, ident_y = np.meshgrid(
        np.arange(w, dtype=np.float32),
        np.arange(h, dtype=np.float32),
    )

    os.makedirs(out_dir, exist_ok=True)
    print(f"[5/5] RGBAフレーム生成: {n_frames}フレーム, {w}x{h}")
    for i in tqdm(range(n_frames), desc="フレーム生成"):
        t = i / max(n_frames - 1, 1)
        # ワープ変位には未クランプの et を使い、ease_out_back / elastic 等の
        # overshoot（et>1 の行き過ぎ変形）を意図どおり表現する。
        # remap は範囲外座標を BORDER_CONSTANT で安全に扱うためクランプ不要。
        # 一方クロスディゾルブの重みは負アルファを生まないよう [0,1] にクランプする
        et_raw = blend_fn(t)
        et = min(max(et_raw, 0.0), 1.0)

        # 注意: 後方ワープ（出力座標基準の参照）に、ソース点で評価した
        # 前方基準の変位場をそのまま流用する近似。変位が大きい場合は
        # 参照位置がずれ、にじみ・ゴーストが出ることがある。

        # ソース画像をワープ
        mx_s = ident_x - et_raw * dx_s
        my_s = ident_y - et_raw * dy_s
        ws = cv2.remap(src_pm, mx_s, my_s, cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

        # ターゲット画像を逆ワープ
        mx_t = ident_x - (1.0 - et_raw) * dx_t
        my_t = ident_y - (1.0 - et_raw) * dy_t
        wt = cv2.remap(tgt_pm, mx_t, my_t, cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

        # クロスディゾルブ（事前乗算済み空間で線形ブレンド）
        blended = (1.0 - et) * ws + et * wt

        # unpremultiply → RGBA保存
        # 除数に下限1.0を設け、低アルファ画素で色ノイズが増幅されるのを防ぐ
        alpha = blended[:, :, 3:4]
        safe_alpha = np.maximum(alpha, 1.0)
        rgb = blended[:, :, :3] / safe_alpha * 255.0
        a_out = alpha
        rgba = np.dstack([rgb, a_out])
        rgba = np.clip(rgba, 0, 255).astype(np.uint8)

        frame_path = os.path.join(out_dir, f"frame_{i:05d}.png")
        Image.fromarray(rgba, "RGBA").save(frame_path)

    print(f"完了: {out_dir} ({n_frames}フレーム)")


# ============================================================
# メイン処理
# ============================================================

def create_video(path_a, path_b, output_path, *,
                 max_pixels=2000, fps=30, duration=3.0,
                 w_move=1.0, w_color=0.3, w_vanish=1.5,
                 grid_step=8, smoothing=10.0,
                 bg_color=(0, 0, 0)):
    """モーフィング動画を生成"""

    # --- 1〜4. 読み込み→抽出→最適輸送→ワープ場構築（共通処理） ---
    arr_a, arr_b, canvas, dx_s, dy_s, dx_t, dy_t = _prepare_morph(
        path_a, path_b,
        max_pixels=max_pixels, w_move=w_move, w_color=w_color,
        w_vanish=w_vanish, grid_step=grid_step, smoothing=smoothing,
    )
    w, h = canvas

    # --- 5. 動画レンダリング ---
    # 事前計算
    src_pm = premultiply_alpha(arr_a)
    tgt_pm = premultiply_alpha(arr_b)
    ident_x, ident_y = np.meshgrid(
        np.arange(w, dtype=np.float32),
        np.arange(h, dtype=np.float32),
    )
    bg = np.array(bg_color, dtype=np.float32).reshape(1, 1, 3)

    num_frames = int(fps * duration)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError("VideoWriterを開けません")

    print(f"[5/5] レンダリング: {num_frames}フレーム, {w}x{h}")
    try:
        for i in tqdm(range(num_frames), desc="レンダリング"):
            t = i / max(num_frames - 1, 1)
            et = ease_in_out(t)

            # 注意: 後方ワープ（出力座標基準の参照）に、ソース点で評価した
            # 前方基準の変位場をそのまま流用する近似。変位が大きい場合は
            # 参照位置がずれ、にじみ・ゴーストが出ることがある。

            # ソース画像をワープ（後方写像: 出力(x,y) ← ソース(x-et*dx, y-et*dy)）
            mx_s = ident_x - et * dx_s
            my_s = ident_y - et * dy_s
            ws = cv2.remap(src_pm, mx_s, my_s, cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

            # ターゲット画像を逆ワープ（t=0で最大変形、t=1で元に戻る）
            mx_t = ident_x - (1.0 - et) * dx_t
            my_t = ident_y - (1.0 - et) * dy_t
            wt = cv2.remap(tgt_pm, mx_t, my_t, cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

            # クロスディゾルブ（事前乗算済み空間で線形ブレンド）
            blended = (1.0 - et) * ws + et * wt
            alpha = blended[:, :, 3:4] / 255.0
            rgb = blended[:, :, :3]  # 事前乗算済みRGB

            # 背景合成（over合成: premul_fg + bg * (1 - α)）
            frame = rgb + bg * (1.0 - alpha)
            # RGB → BGR に変換して書き出し
            frame_bgr = np.clip(frame[:, :, ::-1], 0, 255).astype(np.uint8)
            # OpenCVのバージョンにより返値はNone/bool（Falseなら書き込み失敗）
            ok = writer.write(frame_bgr)
            if ok is False:
                raise RuntimeError(f"フレーム{i}の書き込みに失敗しました")
    finally:
        writer.release()
    print(f"完了: {output_path}")


def main():
    p = argparse.ArgumentParser(
        description="最適輸送 + ワープ場によるモーフィング動画生成"
    )
    p.add_argument("image_a", help="入力画像A（PNG）")
    p.add_argument("image_b", help="入力画像B（PNG）")
    p.add_argument("-o", "--output", default="morph.mp4",
                   help="出力動画パス（デフォルト: morph.mp4）")
    p.add_argument("--max-pixels", type=int, default=2000,
                   help="OT計算の最大ピクセル数（デフォルト: 2000）")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--duration", type=float, default=3.0,
                   help="秒数（デフォルト: 3.0）")
    p.add_argument("--w-move", type=float, default=1.0,
                   help="移動コストの重み")
    p.add_argument("--w-color", type=float, default=0.3,
                   help="色変化コストの重み")
    p.add_argument("--w-vanish", type=float, default=1.5,
                   help="消滅/出現コストの重み")
    p.add_argument("--grid-step", type=int, default=8,
                   help="ワープ場グリッド間隔（小さいほど精密、デフォルト: 8）")
    p.add_argument("--smoothing", type=float, default=10.0,
                   help="RBF補間の滑らかさ（大きいほど滑らか、デフォルト: 10）")
    p.add_argument("--bg", type=int, nargs=3, default=[0, 0, 0],
                   metavar=("R", "G", "B"), help="背景色")
    a = p.parse_args()

    create_video(
        a.image_a, a.image_b, a.output,
        max_pixels=a.max_pixels, fps=a.fps, duration=a.duration,
        w_move=a.w_move, w_color=a.w_color, w_vanish=a.w_vanish,
        grid_step=a.grid_step, smoothing=a.smoothing,
        bg_color=tuple(a.bg),
    )


if __name__ == "__main__":
    main()
