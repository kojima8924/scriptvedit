"""
FFmpegを使用したレンダリングモジュール
"""

import subprocess
import shutil
import math
from pathlib import Path
from typing import Optional

from .timeline import get_timeline, VideoEntry, AudioEntry
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


def _build_video_filter(timeline, video_entries) -> tuple[list[str], list[str], str]:
    """映像用filter_complexを構築する"""
    inputs = []
    filters = []
    overlay_chain = "[base]"

    # 背景を作成
    filters.append(
        f"color=c={timeline.background_color}:s={timeline.width}x{timeline.height}:"
        f"d={timeline.total_duration}:r={timeline.fps}[base]"
    )

    for i, entry in enumerate(video_entries):
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

        # 1. クロップ
        if tf.crop_x != 0 or tf.crop_y != 0 or tf.crop_w != 1 or tf.crop_h != 1:
            filter_chain.append(
                f"crop=w=iw*{tf.crop_w}:h=ih*{tf.crop_h}:x=iw*{tf.crop_x}:y=ih*{tf.crop_y}"
            )

        # 2. 反転
        if tf.flip_h:
            filter_chain.append("hflip")
        if tf.flip_v:
            filter_chain.append("vflip")

        # 3. スケール
        if tf.scale_x is not None and tf.scale_y is not None:
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

        # 6. クロマキー
        if tf.chromakey_color:
            filter_chain.append(
                f"colorkey={tf.chromakey_color}:{tf.chromakey_similarity}:{tf.chromakey_blend}"
            )

        filter_chain.append("setpts=PTS-STARTPTS")

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

        t_norm_stream = f"t/{entry.duration}"
        t_norm_overlay = f"(t-{entry.start_time})/{entry.duration}"
        enable = f"between(t,{entry.start_time},{entry.start_time + entry.duration})"

        # 回転アニメーション
        if rotate_effect:
            start_rad = tf.rotation * math.pi / 180
            end_rad = rotate_effect.angle * math.pi / 180
            angle_expr = f"{start_rad}+({end_rad}-{start_rad})*({t_norm_stream})"
            new_label = next_label()
            filters.append(
                f"{out_label}format=rgba,rotate='{angle_expr}':c=0x00000000:ow=rotw({end_rad}):oh=roth({end_rad})"
                f"{new_label}"
            )
            out_label = new_label

        # スケールアニメーション
        if scale_effect:
            start_sx = tf.scale_x if tf.scale_x is not None else scale_effect.sx
            start_sy = tf.scale_y if tf.scale_y is not None else scale_effect.sy
            start_w = int(timeline.width * start_sx)
            start_h = int(timeline.height * start_sy)
            end_w = int(timeline.width * scale_effect.sx)
            end_h = int(timeline.height * scale_effect.sy)
            w_expr = f"{start_w}+({end_w}-{start_w})*({t_norm_stream})"
            h_expr = f"{start_h}+({end_h}-{start_h})*({t_norm_stream})"
            new_label = next_label()
            filters.append(
                f"{out_label}scale=w='{w_expr}':h='{h_expr}':eval=frame"
                f"{new_label}"
            )
            out_label = new_label

        # ブラーアニメーション
        if blur_effect:
            blur_expr = f"{blur_effect.amount}*({t_norm_stream})"
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
                    f"fade=t=out:st=0:d={entry.duration}:alpha=1"
                    f"{new_label}"
                )
            elif fade_effect.alpha == 0:
                filters.append(
                    f"{out_label}format=rgba,"
                    f"fade=t=out:st=0:d={entry.duration}:alpha=1"
                    f"{new_label}"
                )
            else:
                filters.append(
                    f"{out_label}format=rgba,"
                    f"colorchannelmixer=aa={fade_effect.alpha}"
                    f"{new_label}"
                )
            out_label = new_label

        # オーバーレイ位置
        pos_x = tf.pos_x
        pos_y = tf.pos_y
        ax, ay = _get_anchor_offset(tf.anchor)
        base_x = f"{pos_x}*{timeline.width}"
        base_y = f"{pos_y}*{timeline.height}"

        if move_effect:
            end_x = f"{move_effect.x}*{timeline.width}"
            end_y = f"{move_effect.y}*{timeline.height}"
            x_expr = f"({base_x})+({end_x}-({base_x}))*({t_norm_overlay})+({ax})"
            y_expr = f"({base_y})+({end_y}-({base_y}))*({t_norm_overlay})+({ay})"
        else:
            x_expr = f"({base_x})+({ax})"
            y_expr = f"({base_y})+({ay})"

        if shake_effect:
            intensity_px = shake_effect.intensity * timeline.width
            shake_x = f"{intensity_px}*sin({shake_effect.speed}*2*PI*t)"
            shake_y = f"{intensity_px}*cos({shake_effect.speed}*2*PI*t*1.3)"
            x_expr = f"({x_expr})+({shake_x})"
            y_expr = f"({y_expr})+({shake_y})"

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
    if video_entries:
        filters[-1] = filters[-1].rsplit("[", 1)[0] + "[vout]"
        final_label = "[vout]"
    else:
        final_label = "[base]"

    return inputs, filters, final_label


def _build_audio_filter(timeline, audio_entries, video_input_count) -> tuple[list[str], list[str], str]:
    """音声用フィルタを構築する"""
    inputs = []
    filters = []
    audio_streams = []

    for i, entry in enumerate(audio_entries):
        audio = entry.audio
        input_idx = video_input_count + i
        inputs.extend(["-i", str(audio.path)])

        stream = f"[{input_idx}:a]"
        out_label = f"[a{i}]"

        audio_filter_parts = []

        # トリム（開始位置と長さ）
        audio_filter_parts.append(f"atrim=0:{entry.duration}")
        audio_filter_parts.append("asetpts=PTS-STARTPTS")

        # 音量
        if audio.volume != 1.0:
            audio_filter_parts.append(f"volume={audio.volume}")

        # フェードイン/アウト
        if audio.fade_in > 0:
            audio_filter_parts.append(f"afade=t=in:st=0:d={audio.fade_in}")
        if audio.fade_out > 0:
            fade_out_start = entry.duration - audio.fade_out
            audio_filter_parts.append(f"afade=t=out:st={fade_out_start}:d={audio.fade_out}")

        # 開始時間のディレイ
        if entry.start_time > 0:
            delay_ms = int(entry.start_time * 1000)
            audio_filter_parts.append(f"adelay={delay_ms}|{delay_ms}")

        filters.append(f"{stream}{','.join(audio_filter_parts)}{out_label}")
        audio_streams.append(out_label)

    # 複数音声をミックス
    if len(audio_streams) > 1:
        mix_input = "".join(audio_streams)
        filters.append(f"{mix_input}amix=inputs={len(audio_streams)}:duration=longest[aout]")
        final_audio = "[aout]"
    elif len(audio_streams) == 1:
        # 1つだけの場合はラベルを変更
        filters[-1] = filters[-1].rsplit("[", 1)[0] + "[aout]"
        final_audio = "[aout]"
    else:
        final_audio = None

    return inputs, filters, final_audio


def render(output: str, verbose: bool = False) -> None:
    """
    タイムラインを動画にレンダリングする

    Args:
        output: 出力ファイルパス
        verbose: 詳細出力を表示するか
    """
    ffmpeg = _check_ffmpeg()
    timeline = get_timeline()

    if not timeline.video_entries and not timeline.audio_entries:
        raise ValueError("タイムラインが空です。show()またはplay()でメディアを追加してください。")

    # 映像フィルタ構築
    video_inputs, video_filters, video_out = _build_video_filter(timeline, timeline.video_entries)

    # 音声フィルタ構築
    audio_inputs, audio_filters, audio_out = _build_audio_filter(
        timeline, timeline.audio_entries, len(timeline.video_entries)
    )

    # フィルタ結合
    all_filters = video_filters + audio_filters
    filter_complex = ";".join(all_filters)

    # コマンド構築
    cmd = [
        ffmpeg,
        "-y",
        *video_inputs,
        *audio_inputs,
        "-filter_complex", filter_complex,
        "-map", video_out,
    ]

    if audio_out:
        cmd.extend(["-map", audio_out, "-c:a", "aac", "-b:a", "192k"])

    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-t", str(timeline.total_duration),
        output
    ])

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
