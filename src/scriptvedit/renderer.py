"""
FFmpegを使用したレンダリングモジュール
"""

import subprocess
import shutil
import math
from pathlib import Path
from typing import Optional, Callable, Union
from dataclasses import dataclass

from .timeline import get_timeline, VideoEntry, AudioEntry, TextEntry
from .effects import MoveEffect, FadeEffect, RotateToEffect, ScaleEffect, BlurEffect, ShakeEffect
from .media import Transform

# 画像拡張子（-loop 1 を付与する対象）
# 注意: .gif は動画として扱われることが多いため除外（将来 ffprobe 判定を入れる予定）
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"}


def _check_ffmpeg() -> str:
    """FFmpegの存在確認"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpegが見つかりません。インストールしてPATHに追加してください。")
    return ffmpeg


def _resolve_transform_value(value, current: float) -> float:
    """Transform の値を解決する（callable なら現在値を渡して評価）"""
    if callable(value):
        try:
            return float(value(current))
        except Exception as e:
            raise ValueError(f"Transform callable の評価エラー: {e}")
    if value is None:
        return current
    return float(value)


@dataclass
class ResolvedTransform:
    """解決済みの Transform 値"""
    scale_x: Optional[float]
    scale_y: Optional[float]
    pos_x: float
    pos_y: float
    anchor: str
    rotation: float
    alpha: float
    crop_x: float
    crop_y: float
    crop_w: float
    crop_h: float
    chromakey_color: Optional[str]
    chromakey_similarity: float
    chromakey_blend: float
    flip_h: bool
    flip_v: bool


def _resolve_transform(media, timeline) -> ResolvedTransform:
    """Transform の callable を解決して float に変換する"""
    tf = media.transform
    img_w, img_h = media._ensure_dimensions()

    # scale のデフォルト現在値（メディア実寸の画面比）
    default_sx = img_w / timeline.width
    default_sy = img_h / timeline.height

    # scale_x, scale_y の解決
    current_sx = default_sx
    current_sy = default_sy
    if tf.scale_x is not None and not callable(tf.scale_x):
        current_sx = tf.scale_x
    if tf.scale_y is not None and not callable(tf.scale_y):
        current_sy = tf.scale_y

    scale_x = _resolve_transform_value(tf.scale_x, current_sx) if tf.scale_x is not None else None
    scale_y = _resolve_transform_value(tf.scale_y, current_sy) if tf.scale_y is not None else None

    # アスペクト比維持の処理（解決後）
    if scale_x is not None and scale_y is None:
        scale_y = scale_x * (img_h / img_w) * (timeline.width / timeline.height)
    elif scale_y is not None and scale_x is None:
        scale_x = scale_y * (img_w / img_h) * (timeline.height / timeline.width)

    return ResolvedTransform(
        scale_x=scale_x,
        scale_y=scale_y,
        pos_x=_resolve_transform_value(tf.pos_x, 0.0),
        pos_y=_resolve_transform_value(tf.pos_y, 0.0),
        anchor=tf.anchor,
        rotation=_resolve_transform_value(tf.rotation, 0.0),
        alpha=_resolve_transform_value(tf.alpha, 1.0),
        crop_x=_resolve_transform_value(tf.crop_x, 0.0),
        crop_y=_resolve_transform_value(tf.crop_y, 0.0),
        crop_w=_resolve_transform_value(tf.crop_w, 1.0),
        crop_h=_resolve_transform_value(tf.crop_h, 1.0),
        chromakey_color=tf.chromakey_color,
        chromakey_similarity=_resolve_transform_value(tf.chromakey_similarity, 0.1),
        chromakey_blend=_resolve_transform_value(tf.chromakey_blend, 0.1),
        flip_h=tf.flip_h,
        flip_v=tf.flip_v,
    )


def _sample_callable(fn: Callable[[float], float], n_samples: int) -> list[float]:
    """callable を n_samples 個のサンプルでサンプリング"""
    if n_samples < 2:
        n_samples = 2
    samples = []
    for i in range(n_samples):
        u = i / (n_samples - 1)
        try:
            samples.append(float(fn(u)))
        except Exception as e:
            raise ValueError(f"Effect callable の評価エラー (u={u}): {e}")
    return samples


def _piecewise_linear_expr(u_expr: str, values: list[float]) -> str:
    """区分線形のFFmpeg式を生成する

    values[0] は u=0 の値、values[-1] は u=1 の値
    """
    n = len(values)
    if n < 2:
        return str(values[0]) if values else "0"
    if n == 2:
        # 単純な線形補間
        v0, v1 = values
        return f"({v0}+({v1}-{v0})*({u_expr}))"

    # 区分線形: if(lte(u,u1), lerp01, if(lte(u,u2), lerp12, ...))
    # u_i = i / (n-1)
    expr = str(values[-1])  # 最後の値（デフォルト）
    for i in range(n - 2, -1, -1):
        u_i = i / (n - 1)
        u_next = (i + 1) / (n - 1)
        v_i = values[i]
        v_next = values[i + 1]
        # この区間の線形補間: v_i + (v_next - v_i) * (u - u_i) / (u_next - u_i)
        slope = (v_next - v_i) / (u_next - u_i) if u_next != u_i else 0
        lerp = f"({v_i}+{slope}*(({u_expr})-{u_i}))"
        expr = f"if(lte(({u_expr}),{u_next}),{lerp},{expr})"
    return expr


def _clamp_expr(expr: str, lo: float, hi: float) -> str:
    """式をクランプする（clip関数を使用）"""
    return f"clip({expr},{lo},{hi})"


def _clamp_expr_if(expr: str, lo: float, hi: float) -> str:
    """式をクランプする（if/else を使用、geq など clip 非対応フィルタ用）"""
    return f"if(lt({expr},{lo}),{lo},if(gt({expr},{hi}),{hi},{expr}))"


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


def _get_text_anchor_offset(anchor: str) -> tuple[str, str]:
    """テキスト用のアンカーオフセット（text_w, text_h 使用）"""
    x_offsets = {"l": "0", "c": "-text_w/2", "r": "-text_w"}
    y_offsets = {"t": "0", "c": "-text_h/2", "b": "-text_h"}

    if anchor == "center":
        return "-text_w/2", "-text_h/2"

    if len(anchor) == 2:
        v, h = anchor[0], anchor[1]
        return x_offsets.get(h, "0"), y_offsets.get(v, "0")

    return "0", "0"


def _resolve_text_transform(clip, timeline) -> ResolvedTransform:
    """TextClip の Transform を解決する"""
    tf = clip.transform
    return ResolvedTransform(
        scale_x=None,
        scale_y=None,
        pos_x=_resolve_transform_value(tf.pos_x, 0.5),
        pos_y=_resolve_transform_value(tf.pos_y, 0.5),
        anchor=tf.anchor,
        rotation=_resolve_transform_value(tf.rotation, 0.0),
        alpha=_resolve_transform_value(tf.alpha, 1.0),
        crop_x=0.0,
        crop_y=0.0,
        crop_w=1.0,
        crop_h=1.0,
        chromakey_color=None,
        chromakey_similarity=0.0,
        chromakey_blend=0.0,
        flip_h=False,
        flip_v=False,
    )


def _escape_drawtext(text: str) -> str:
    """drawtext 用にテキストをエスケープする

    FFmpeg drawtext フィルタで安全に表示するためのエスケープ処理。
    変換順序が重要: バックスラッシュを最初に処理する。
    """
    # 1. バックスラッシュを最初にエスケープ（\n 以外）
    # 改行文字を一時的に保護
    text = text.replace("\n", "\x00NEWLINE\x00")
    text = text.replace("\\", "\\\\\\\\")
    # 改行を drawtext 形式に変換
    text = text.replace("\x00NEWLINE\x00", "\\n")

    # 2. その他の特殊文字をエスケープ
    text = text.replace("'", "\\\\'")
    text = text.replace(":", "\\\\:")
    text = text.replace("%", "\\\\%")  # 式展開の誤爆防止
    text = text.replace(",", "\\\\,")  # フィルタ引数区切りの誤爆防止

    return text


def _build_video_filter(timeline, video_entries, text_entries=None) -> tuple[list[str], list[str], str]:
    """映像用filter_complexを構築する"""
    if text_entries is None:
        text_entries = []

    inputs = []
    filters = []
    overlay_chain = "[base]"

    # 背景を作成
    filters.append(
        f"color=c={timeline.background_color}:s={timeline.width}x{timeline.height}:"
        f"d={timeline.total_duration}:r={timeline.fps}[base]"
    )

    # video_entries と text_entries を統合してソート
    # (entry, type) のタプルで管理
    all_entries = []
    for entry in video_entries:
        all_entries.append((entry, "video"))
    for entry in text_entries:
        all_entries.append((entry, "text"))

    # レイヤー順にソート（layer昇順、同一layerはorder昇順）
    sorted_entries = sorted(all_entries, key=lambda e: (e[0].layer, e[0].order))

    # video 入力のインデックス管理
    video_input_idx = 0
    overlay_idx = 0

    for entry, entry_type in sorted_entries:
        if entry_type == "text":
            # テキストエントリの処理
            clip = entry.clip
            tf = _resolve_text_transform(clip, timeline)
            style = clip.style

            # enable clause
            enable = f"between(t,{entry.start_time},{entry.start_time + entry.duration})"

            # 座標計算（W/H ではなく数値を使用）
            pos_x = tf.pos_x
            pos_y = tf.pos_y
            ax, ay = _get_text_anchor_offset(tf.anchor)
            base_x = f"{pos_x}*{timeline.width}"
            base_y = f"{pos_y}*{timeline.height}"
            x_expr = f"({base_x})+({ax})"
            y_expr = f"({base_y})+({ay})"

            # エフェクトから FadeEffect を検出
            fade_effect = None
            for effect in entry.effects:
                if isinstance(effect, FadeEffect):
                    fade_effect = effect
                    break

            # drawtext パラメータ構築
            escaped_text = _escape_drawtext(clip.content)
            dt_params = [f"text='{escaped_text}'"]

            if style.fontfile:
                dt_params.append(f"fontfile='{style.fontfile}'")
            dt_params.append(f"fontsize={style.fontsize}")

            # fontcolor は透明度なしで設定（透明度は alpha= で統一）
            dt_params.append(f"fontcolor={style.fontcolor}")

            if style.box:
                dt_params.append("box=1")
                dt_params.append(f"boxcolor={style.boxcolor}")
                dt_params.append(f"boxborderw={style.boxborderw}")

            if style.borderw > 0:
                dt_params.append(f"borderw={style.borderw}")
                dt_params.append(f"bordercolor={style.bordercolor}")

            if style.shadowx != 0 or style.shadowy != 0:
                dt_params.append(f"shadowx={style.shadowx}")
                dt_params.append(f"shadowy={style.shadowy}")
                dt_params.append(f"shadowcolor={style.shadowcolor}")

            # 透明度処理（base_alpha と fade_effect を統合）
            base_alpha = tf.alpha
            if fade_effect:
                if callable(fade_effect.alpha):
                    # callable fade: サンプリングして piecewise_linear_expr
                    n_samples = min(
                        timeline.curve_samples,
                        max(2, int(entry.duration * timeline.fps) + 1)
                    )
                    # drawtext では t が使える（秒単位）
                    u_expr_text = f"clip((t-{entry.start_time})/{entry.duration},0,1)"
                    samples = _sample_callable(fade_effect.alpha, n_samples)
                    alpha_expr = _piecewise_linear_expr(u_expr_text, samples)
                    alpha_expr = _clamp_expr(alpha_expr, 0, 1)
                    # base_alpha と乗算
                    if base_alpha < 1.0:
                        final_alpha_expr = f"({base_alpha})*({alpha_expr})"
                    else:
                        final_alpha_expr = alpha_expr
                    dt_params.append(f"alpha='{final_alpha_expr}'")
                else:
                    # float fade: base_alpha と乗算
                    fade_alpha = max(0.0, min(1.0, fade_effect.alpha))
                    final_alpha = base_alpha * fade_alpha
                    dt_params.append(f"alpha={final_alpha}")
            elif base_alpha < 1.0:
                # fade なしで opacity のみ
                dt_params.append(f"alpha={base_alpha}")

            dt_params.append(f"x='{x_expr}'")
            dt_params.append(f"y='{y_expr}'")
            dt_params.append(f"enable='{enable}'")

            next_overlay = f"[t{overlay_idx}]"
            drawtext_filter = f"{overlay_chain}drawtext={':'.join(dt_params)}{next_overlay}"
            filters.append(drawtext_filter)
            overlay_chain = next_overlay
            overlay_idx += 1
            continue

        # video エントリの処理（既存コード）
        media = entry.media
        input_idx = video_input_idx

        # 画像ファイルのみ -loop 1 を付与（動画には不要）
        if media.path.suffix.lower() in IMAGE_EXTENSIONS:
            inputs.extend(["-loop", "1", "-i", str(media.path)])
        else:
            inputs.extend(["-i", str(media.path)])

        # Transform を解決
        tf = _resolve_transform(media, timeline)

        stream = f"[{input_idx}:v]"
        label_idx = 0
        current_overlay_idx = overlay_idx  # ローカル変数としてキャプチャ

        def next_label():
            nonlocal label_idx
            lbl = f"[v{current_overlay_idx}_{label_idx}]"
            label_idx += 1
            return lbl

        # エフェクト収集（filter_chain 構築前に行い、二重適用を防ぐ）
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

        # 3. スケール（scale_effect がある場合はスキップ、動的適用に任せる）
        if scale_effect is None and tf.scale_x is not None and tf.scale_y is not None:
            w = int(timeline.width * tf.scale_x)
            h = int(timeline.height * tf.scale_y)
            filter_chain.append(f"scale={w}:{h}")

        # 4. 回転（静的）（rotate_effect がある場合はスキップ、動的適用に任せる）
        if rotate_effect is None and tf.rotation != 0:
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

        # 7. トリムと PTS オフセット（start>0 対応、素材内offset対応）
        # ストリームを offset 位置から duration 分だけ切り出し、PTS をタイムライン時刻に合わせる
        filter_chain.append(f"trim=start={entry.offset}:duration={entry.duration}")
        filter_chain.append(f"setpts=PTS-STARTPTS+{entry.start_time}/TB")

        out_label = next_label()
        filters.append(f"{stream}{','.join(filter_chain)}{out_label}")

        # 正規化時間 u = clip((t - start) / duration, 0, 1)
        # setpts で t がタイムライン時刻になっているので、ストリームでも overlay でも同じ式
        u_expr = f"clip((t-{entry.start_time})/{entry.duration},0,1)"
        # geq フィルタは clip 関数非対応＋大文字 T を使用
        u_raw_geq = f"(T-{entry.start_time})/{entry.duration}"
        u_expr_geq = f"if(lt({u_raw_geq},0),0,if(gt({u_raw_geq},1),1,{u_raw_geq}))"
        enable = f"between(t,{entry.start_time},{entry.start_time + entry.duration})"

        # サンプル数をクリップ長に合わせる
        n_samples = min(timeline.curve_samples, max(2, int(entry.duration * timeline.fps) + 1))

        # スケールアニメーション（rotate より前に適用し、適用順序を統一）
        if scale_effect:
            img_w, img_h = media._ensure_dimensions()
            start_sx = tf.scale_x if tf.scale_x is not None else img_w / timeline.width
            start_sy = tf.scale_y if tf.scale_y is not None else img_h / timeline.height

            # sx の処理
            if callable(scale_effect.sx):
                sx_samples = _sample_callable(scale_effect.sx, n_samples)
                sx_expr = _piecewise_linear_expr(u_expr, sx_samples)
            elif scale_effect.sx is not None:
                end_sx = scale_effect.sx
                sx_expr = f"({start_sx}+({end_sx}-{start_sx})*({u_expr}))"
            else:
                sx_expr = None

            # sy の処理
            if callable(scale_effect.sy):
                sy_samples = _sample_callable(scale_effect.sy, n_samples)
                sy_expr = _piecewise_linear_expr(u_expr, sy_samples)
            elif scale_effect.sy is not None:
                end_sy = scale_effect.sy
                sy_expr = f"({start_sy}+({end_sy}-{start_sy})*({u_expr}))"
            else:
                sy_expr = None

            # アスペクト比維持
            aspect = (img_h / img_w) * (timeline.width / timeline.height)
            if sx_expr is not None and sy_expr is None:
                sy_expr = f"(({sx_expr})*{aspect})"
            elif sy_expr is not None and sx_expr is None:
                sx_expr = f"(({sy_expr})/{aspect})"
            elif sx_expr is None and sy_expr is None:
                sx_expr = str(start_sx)
                sy_expr = str(start_sy)

            w_expr = f"({timeline.width}*({sx_expr}))"
            h_expr = f"({timeline.height}*({sy_expr}))"
            new_label = next_label()
            filters.append(
                f"{out_label}scale=w='{w_expr}':h='{h_expr}':eval=frame"
                f"{new_label}"
            )
            out_label = new_label

        # 回転アニメーション（scale の後に適用）
        if rotate_effect:
            if callable(rotate_effect.angle):
                samples = _sample_callable(rotate_effect.angle, n_samples)
                angle_deg_expr = _piecewise_linear_expr(u_expr, samples)
            else:
                # 線形補間
                start_deg = tf.rotation
                end_deg = rotate_effect.angle
                angle_deg_expr = f"({start_deg}+({end_deg}-{start_deg})*({u_expr}))"

            angle_rad_expr = f"(({angle_deg_expr})*{math.pi}/180)"
            # hypot(iw,ih) を使用して、どの角度でもクロップされないようにする
            new_label = next_label()
            filters.append(
                f"{out_label}format=rgba,rotate='{angle_rad_expr}':c=0x00000000:ow='hypot(iw,ih)':oh='hypot(iw,ih)'"
                f"{new_label}"
            )
            out_label = new_label

        # ブラーアニメーション
        if blur_effect:
            if callable(blur_effect.amount):
                samples = _sample_callable(blur_effect.amount, n_samples)
                blur_expr = _piecewise_linear_expr(u_expr, samples)
            else:
                # 0 から amount への線形補間
                blur_expr = f"({blur_effect.amount}*({u_expr}))"
            blur_expr = f"max(0,{blur_expr})"  # 負値防止
            new_label = next_label()
            filters.append(
                f"{out_label}gblur=sigma='{blur_expr}'"
                f"{new_label}"
            )
            out_label = new_label

        # フェード（callable 対応: geq または colorchannelmixer）
        # float は固定透明度、callable は時間変化する透明度
        if fade_effect:
            new_label = next_label()
            if callable(fade_effect.alpha):
                # callable をサンプリングして piecewise_linear_expr で alpha_expr を生成
                samples = _sample_callable(fade_effect.alpha, n_samples)
                alpha_expr = _piecewise_linear_expr(u_expr_geq, samples)
                alpha_expr = _clamp_expr_if(alpha_expr, 0, 1)
                filters.append(
                    f"{out_label}format=rgba,"
                    f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='a(X,Y)*({alpha_expr})'"
                    f"{new_label}"
                )
            else:
                # 固定透明度（0.0〜1.0 にクランプ）
                alpha = max(0.0, min(1.0, fade_effect.alpha))
                filters.append(
                    f"{out_label}format=rgba,"
                    f"colorchannelmixer=aa={alpha}"
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
            x_callable = callable(move_effect.x)
            y_callable = callable(move_effect.y)

            if x_callable:
                x_samples = _sample_callable(move_effect.x, n_samples)
                x_pos_expr = _piecewise_linear_expr(u_expr, x_samples)
                x_expr = f"(({x_pos_expr})*{timeline.width})+({ax})"
            else:
                end_x = f"{move_effect.x}*{timeline.width}"
                x_expr = f"({base_x})+({end_x}-({base_x}))*({u_expr})+({ax})"

            if y_callable:
                y_samples = _sample_callable(move_effect.y, n_samples)
                y_pos_expr = _piecewise_linear_expr(u_expr, y_samples)
                y_expr = f"(({y_pos_expr})*{timeline.height})+({ay})"
            else:
                end_y = f"{move_effect.y}*{timeline.height}"
                y_expr = f"({base_y})+({end_y}-({base_y}))*({u_expr})+({ay})"
        else:
            x_expr = f"({base_x})+({ax})"
            y_expr = f"({base_y})+({ay})"

        if shake_effect:
            if callable(shake_effect.intensity):
                int_samples = _sample_callable(shake_effect.intensity, n_samples)
                int_expr = _piecewise_linear_expr(u_expr, int_samples)
                intensity_px = f"({timeline.width}*({int_expr}))"
            else:
                intensity_px = str(shake_effect.intensity * timeline.width)
            shake_x = f"({intensity_px})*sin({shake_effect.speed}*2*PI*t)"
            shake_y = f"({intensity_px})*cos({shake_effect.speed}*2*PI*t*1.3)"
            x_expr = f"({x_expr})+({shake_x})"
            y_expr = f"({y_expr})+({shake_y})"

        next_overlay = f"[mix{overlay_idx}]"
        overlay_filter = (
            f"{overlay_chain}{out_label}overlay="
            f"x='{x_expr}':y='{y_expr}':"
            f"enable='{enable}'"
            f"{next_overlay}"
        )
        filters.append(overlay_filter)
        overlay_chain = next_overlay
        video_input_idx += 1
        overlay_idx += 1

    # 最終出力ラベル
    if video_entries or text_entries:
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


def render(output: str, verbose: bool = False, dump_graph: Optional[str] = None) -> None:
    """
    タイムラインを動画にレンダリングする

    Args:
        output: 出力ファイルパス
        verbose: 詳細出力を表示するか
        dump_graph: filter_complex を保存するファイルパス（デバッグ用）
    """
    ffmpeg = _check_ffmpeg()
    timeline = get_timeline()

    if not timeline.video_entries and not timeline.audio_entries and not timeline.text_entries:
        raise ValueError("タイムラインが空です。show()またはplay()でメディアを追加してください。")

    # 映像フィルタ構築
    video_inputs, video_filters, video_out = _build_video_filter(
        timeline, timeline.video_entries, timeline.text_entries
    )

    # 音声フィルタ構築
    audio_inputs, audio_filters, audio_out = _build_audio_filter(
        timeline, timeline.audio_entries, len(timeline.video_entries)
    )

    # フィルタ結合
    all_filters = video_filters + audio_filters
    filter_complex = ";".join(all_filters)

    # filter_complex をファイルに保存（デバッグ用）
    if dump_graph:
        # 読みやすく整形（1フィルタ1行）
        formatted = ";\n".join(all_filters)
        with open(dump_graph, "w", encoding="utf-8") as f:
            f.write(formatted)
        if verbose:
            print(f"Filter graph saved to: {dump_graph}")

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
