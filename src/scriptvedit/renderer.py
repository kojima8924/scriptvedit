"""
FFmpegを使用したレンダリングモジュール
"""

import subprocess
import shutil
import math
from pathlib import Path
from typing import Optional

from .timeline import get_timeline, TimelineEntry
from .effects import MoveEffect, FadeEffect, RotateToEffect, ScaleEffect, BlurEffect, ShakeEffect


def _check_ffmpeg() -> str:
    """FFmpegの存在確認"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpegが見つかりません。インストールしてPATHに追加してください。")
    return ffmpeg


def _get_anchor_offset(anchor: str) -> tuple[str, str]:
    """アンカーポイントからオフセット計算式を返す"""
    x_offsets = {"l": "0", "c": "-overlay_w/2", "r": "-overlay_w"}
    y_offsets = {"t": "0", "c": "-overlay_h/2", "b": "-overlay_h"}

    if anchor == "center":
        return "-overlay_w/2", "-overlay_h/2"

    if len(anchor) == 2:
        v, h = anchor[0], anchor[1]
        return x_offsets.get(h, "0"), y_offsets.get(v, "0")

    return "0", "0"


def _build_filter_complex(timeline) -> tuple[list[str], str]:
    """filter_complexを構築する"""
    inputs = []
    filters = []
    overlay_chain = "[base]"

    # 背景を作成
    filters.append(
        f"color=c={timeline.background_color}:s={timeline.width}x{timeline.height}:"
        f"d={timeline.total_duration}:r={timeline.fps}[base]"
    )

    for i, entry in enumerate(timeline.entries):
        media = entry.media
        tf = media.transform
        input_idx = i
        inputs.extend(["-loop", "1", "-i", str(media.path)])

        stream = f"[{input_idx}:v]"
        label_idx = 0

        def next_label():
            nonlocal label_idx
            lbl = f"[m{i}_{label_idx}]"
            label_idx += 1
            return lbl

        filter_chain = []

        # 1. クロップ（元画像に対する相対値）
        if tf.crop_x != 0 or tf.crop_y != 0 or tf.crop_w != 1 or tf.crop_h != 1:
            filter_chain.append(
                f"crop=w=iw*{tf.crop_w}:h=ih*{tf.crop_h}:x=iw*{tf.crop_x}:y=ih*{tf.crop_y}"
            )

        # 2. 反転
        if tf.flip_h:
            filter_chain.append("hflip")
        if tf.flip_v:
            filter_chain.append("vflip")

        # 3. スケール（画面サイズに対する相対値）
        w = int(timeline.width * tf.scale_x)
        h = int(timeline.height * tf.scale_y)
        filter_chain.append(f"scale={w}:{h}")

        # 4. 回転（静的）
        if tf.rotation != 0:
            angle_rad = tf.rotation * math.pi / 180
            filter_chain.append(f"format=rgba,rotate={angle_rad}:c=0x00000000:ow=rotw({angle_rad}):oh=roth({angle_rad})")

        # 5. 初期透明度
        if tf.alpha < 1.0:
            filter_chain.append(f"format=rgba,colorchannelmixer=aa={tf.alpha}")

        # 表示時間設定
        filter_chain.append("setpts=PTS-STARTPTS")

        # フィルタチェーン結合
        out_label = next_label()
        filters.append(f"{stream}{','.join(filter_chain)}{out_label}")

        # エフェクト収集
        move_effect = None
        fade_effect = None
        rotate_effect = None
        scale_effect = None
        blur_effect = None
        shake_effect = None

        for effect in entry.effects:
            if isinstance(effect, MoveEffect):
                move_effect = effect
            elif isinstance(effect, FadeEffect):
                fade_effect = effect
            elif isinstance(effect, RotateToEffect):
                rotate_effect = effect
            elif isinstance(effect, ScaleEffect):
                scale_effect = effect
            elif isinstance(effect, BlurEffect):
                blur_effect = effect
            elif isinstance(effect, ShakeEffect):
                shake_effect = effect

        # 時間正規化式
        t_norm = f"(t-{entry.start_time})/{entry.duration}"
        enable = f"between(t,{entry.start_time},{entry.start_time + entry.duration})"

        # 回転アニメーション
        if rotate_effect:
            start_rad = tf.rotation * math.pi / 180
            end_rad = rotate_effect.angle * math.pi / 180
            angle_expr = f"{start_rad}+({end_rad}-{start_rad})*({t_norm})"
            new_label = next_label()
            filters.append(
                f"{out_label}format=rgba,rotate='{angle_expr}':c=0x00000000:ow=rotw({end_rad}):oh=roth({end_rad})"
                f"{new_label}"
            )
            out_label = new_label

        # スケールアニメーション
        if scale_effect:
            start_w = int(timeline.width * tf.scale_x)
            start_h = int(timeline.height * tf.scale_y)
            end_w = int(timeline.width * scale_effect.sx)
            end_h = int(timeline.height * scale_effect.sy)
            w_expr = f"{start_w}+({end_w}-{start_w})*({t_norm})"
            h_expr = f"{start_h}+({end_h}-{start_h})*({t_norm})"
            new_label = next_label()
            filters.append(
                f"{out_label}scale=w='{w_expr}':h='{h_expr}':eval=frame"
                f"{new_label}"
            )
            out_label = new_label

        # ブラーアニメーション
        if blur_effect:
            blur_expr = f"{blur_effect.amount}*({t_norm})"
            new_label = next_label()
            filters.append(
                f"{out_label}gblur=sigma='{blur_expr}'"
                f"{new_label}"
            )
            out_label = new_label

        # フェード
        if fade_effect:
            new_label = next_label()
            if callable(fade_effect.alpha):
                filters.append(
                    f"{out_label}format=rgba,"
                    f"fade=t=out:st={entry.start_time}:d={entry.duration}:alpha=1"
                    f"{new_label}"
                )
            elif fade_effect.alpha == 0:
                filters.append(
                    f"{out_label}format=rgba,"
                    f"fade=t=out:st={entry.start_time}:d={entry.duration}:alpha=1"
                    f"{new_label}"
                )
            else:
                filters.append(
                    f"{out_label}format=rgba,"
                    f"colorchannelmixer=aa={fade_effect.alpha}"
                    f"{new_label}"
                )
            out_label = new_label

        # オーバーレイ位置計算
        pos_x = tf.pos_x
        pos_y = tf.pos_y
        ax, ay = _get_anchor_offset(tf.anchor)

        base_x = f"{pos_x}*{timeline.width}"
        base_y = f"{pos_y}*{timeline.height}"

        # 移動エフェクト
        if move_effect:
            end_x = f"{move_effect.x}*{timeline.width}"
            end_y = f"{move_effect.y}*{timeline.height}"
            x_expr = f"({base_x})+({end_x}-({base_x}))*({t_norm})+({ax})"
            y_expr = f"({base_y})+({end_y}-({base_y}))*({t_norm})+({ay})"
        else:
            x_expr = f"({base_x})+({ax})"
            y_expr = f"({base_y})+({ay})"

        # シェイクエフェクト
        if shake_effect:
            intensity_px = shake_effect.intensity * timeline.width
            shake_x = f"{intensity_px}*sin({shake_effect.speed}*2*PI*t)"
            shake_y = f"{intensity_px}*cos({shake_effect.speed}*2*PI*t*1.3)"
            x_expr = f"({x_expr})+({shake_x})"
            y_expr = f"({y_expr})+({shake_y})"

        # オーバーレイ
        next_overlay = f"[tmp{i}]"
        overlay_filter = (
            f"{overlay_chain}{out_label}overlay="
            f"x='{x_expr}':y='{y_expr}':"
            f"enable='{enable}'"
            f"{next_overlay}"
        )
        filters.append(overlay_filter)
        overlay_chain = next_overlay

    # 最終出力ラベル
    if timeline.entries:
        filters[-1] = filters[-1].rsplit("[", 1)[0] + "[out]"
        final_label = "[out]"
    else:
        final_label = "[base]"

    return inputs, ";".join(filters), final_label


def render(output: str, verbose: bool = False) -> None:
    """
    タイムラインを動画にレンダリングする

    Args:
        output: 出力ファイルパス
        verbose: 詳細出力を表示するか
    """
    ffmpeg = _check_ffmpeg()
    timeline = get_timeline()

    if not timeline.entries:
        raise ValueError("タイムラインが空です。show()でメディアを追加してください。")

    inputs, filter_complex, final_label = _build_filter_complex(timeline)

    cmd = [
        ffmpeg,
        "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", final_label,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-t", str(timeline.total_duration),
        output
    ]

    if verbose:
        print("FFmpeg command:")
        print(" ".join(cmd))
        print()

    result = subprocess.run(
        cmd,
        capture_output=not verbose,
        text=True
    )

    if result.returncode != 0:
        error_msg = result.stderr if result.stderr else "不明なエラー"
        raise RuntimeError(f"FFmpegエラー:\n{error_msg}")

    print(f"レンダリング完了: {output}")
