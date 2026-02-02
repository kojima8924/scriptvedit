"""
プロジェクトのシリアライズ/デシリアライズモジュール

Project (Timeline) を JSON 互換の dict に変換し、
永続化・復元を可能にする。

Note:
    callable な値（エフェクト関数など）は直接シリアライズできないため、
    既知のイージング関数名で表現するか、静的値のみを保存する。
"""

from typing import Any, Dict, List, Optional, Callable
import warnings

from . import ease
from .timeline import Timeline, VideoEntry, AudioEntry, TextEntry
from .media import Media, Audio, Transform
from .text import TextClip, TextStyle
from .effects import (
    MoveEffect, FadeEffect, RotateToEffect,
    ScaleEffect, BlurEffect, ShakeEffect
)


# 既知のイージング関数名とその関数のマッピング
EASING_FUNCTIONS: Dict[str, Callable[[float], float]] = {
    "linear": ease.linear,
    "in_quad": ease.in_quad,
    "out_quad": ease.out_quad,
    "in_out_quad": ease.in_out_quad,
    "in_cubic": ease.in_cubic,
    "out_cubic": ease.out_cubic,
    "in_out_cubic": ease.in_out_cubic,
    "in_quart": ease.in_quart,
    "out_quart": ease.out_quart,
    "in_out_quart": ease.in_out_quart,
    "in_sine": ease.in_sine,
    "out_sine": ease.out_sine,
    "in_out_sine": ease.in_out_sine,
    "in_expo": ease.in_expo,
    "out_expo": ease.out_expo,
    "in_out_expo": ease.in_out_expo,
}

# 逆引きマップ（関数 -> 名前）
_EASING_NAMES: Dict[int, str] = {id(fn): name for name, fn in EASING_FUNCTIONS.items()}


def _serialize_value(value: Any, field_name: str = "") -> Any:
    """Transform/Effect の値をシリアライズ

    Args:
        value: シリアライズする値
        field_name: デバッグ用フィールド名

    Returns:
        JSON互換の値
    """
    if value is None:
        return None
    if isinstance(value, (int, float, bool, str)):
        return value
    if callable(value):
        # 既知のイージング関数か確認
        func_id = id(value)
        if func_id in _EASING_NAMES:
            return {"easing": _EASING_NAMES[func_id]}
        # 不明な callable - 警告を出して None で保存
        warnings.warn(
            f"callable値はシリアライズできません ({field_name}): {value}",
            UserWarning,
            stacklevel=4
        )
        return None
    return value


def _deserialize_value(value: Any) -> Any:
    """シリアライズされた値を復元

    Args:
        value: シリアライズされた値

    Returns:
        復元された値
    """
    if value is None:
        return None
    if isinstance(value, dict) and "easing" in value:
        easing_name = value["easing"]
        if easing_name in EASING_FUNCTIONS:
            return EASING_FUNCTIONS[easing_name]
        warnings.warn(
            f"不明なイージング関数: {easing_name}",
            UserWarning,
            stacklevel=4
        )
        return None
    return value


def _transform_to_dict(transform: Transform) -> Dict[str, Any]:
    """Transform をシリアライズ"""
    return {
        "scale_x": _serialize_value(transform.scale_x, "scale_x"),
        "scale_y": _serialize_value(transform.scale_y, "scale_y"),
        "pos_x": _serialize_value(transform.pos_x, "pos_x"),
        "pos_y": _serialize_value(transform.pos_y, "pos_y"),
        "anchor": transform.anchor,
        "rotation": _serialize_value(transform.rotation, "rotation"),
        "alpha": _serialize_value(transform.alpha, "alpha"),
        "flip_h": transform.flip_h,
        "flip_v": transform.flip_v,
        "crop_x": _serialize_value(transform.crop_x, "crop_x"),
        "crop_y": _serialize_value(transform.crop_y, "crop_y"),
        "crop_w": _serialize_value(transform.crop_w, "crop_w"),
        "crop_h": _serialize_value(transform.crop_h, "crop_h"),
        "chromakey_color": transform.chromakey_color,
        "chromakey_similarity": _serialize_value(
            transform.chromakey_similarity, "chromakey_similarity"
        ),
        "chromakey_blend": _serialize_value(
            transform.chromakey_blend, "chromakey_blend"
        ),
    }


def _transform_from_dict(data: Dict[str, Any]) -> Transform:
    """Transform を復元"""
    transform = Transform()
    transform.scale_x = _deserialize_value(data.get("scale_x"))
    transform.scale_y = _deserialize_value(data.get("scale_y"))
    transform.pos_x = _deserialize_value(data.get("pos_x", 0.0))
    transform.pos_y = _deserialize_value(data.get("pos_y", 0.0))
    transform.anchor = data.get("anchor", "center")
    transform.rotation = _deserialize_value(data.get("rotation", 0.0))
    transform.alpha = _deserialize_value(data.get("alpha", 1.0))
    transform.flip_h = data.get("flip_h", False)
    transform.flip_v = data.get("flip_v", False)
    transform.crop_x = _deserialize_value(data.get("crop_x", 0.0))
    transform.crop_y = _deserialize_value(data.get("crop_y", 0.0))
    transform.crop_w = _deserialize_value(data.get("crop_w", 1.0))
    transform.crop_h = _deserialize_value(data.get("crop_h", 1.0))
    transform.chromakey_color = data.get("chromakey_color")
    transform.chromakey_similarity = _deserialize_value(
        data.get("chromakey_similarity", 0.1)
    )
    transform.chromakey_blend = _deserialize_value(
        data.get("chromakey_blend", 0.1)
    )
    return transform


def _text_style_to_dict(style: TextStyle) -> Dict[str, Any]:
    """TextStyle をシリアライズ"""
    return {
        "fontfile": style.fontfile,
        "fontsize": style.fontsize,
        "fontcolor": style.fontcolor,
        "box": style.box,
        "boxcolor": style.boxcolor,
        "boxborderw": style.boxborderw,
        "borderw": style.borderw,
        "bordercolor": style.bordercolor,
        "shadowx": style.shadowx,
        "shadowy": style.shadowy,
        "shadowcolor": style.shadowcolor,
    }


def _text_style_from_dict(data: Dict[str, Any]) -> TextStyle:
    """TextStyle を復元"""
    return TextStyle(
        fontfile=data.get("fontfile"),
        fontsize=data.get("fontsize", 48),
        fontcolor=data.get("fontcolor", "white"),
        box=data.get("box", False),
        boxcolor=data.get("boxcolor", "black@0.5"),
        boxborderw=data.get("boxborderw", 5),
        borderw=data.get("borderw", 0),
        bordercolor=data.get("bordercolor", "black"),
        shadowx=data.get("shadowx", 0),
        shadowy=data.get("shadowy", 0),
        shadowcolor=data.get("shadowcolor", "black@0.5"),
    )


def _effect_to_dict(effect: Any) -> Optional[Dict[str, Any]]:
    """エフェクトをシリアライズ"""
    if isinstance(effect, MoveEffect):
        return {
            "type": "move",
            "x": _serialize_value(effect.x, "move.x"),
            "y": _serialize_value(effect.y, "move.y"),
        }
    elif isinstance(effect, FadeEffect):
        return {
            "type": "fade",
            "alpha": _serialize_value(effect.alpha, "fade.alpha"),
        }
    elif isinstance(effect, RotateToEffect):
        return {
            "type": "rotate_to",
            "angle": _serialize_value(effect.angle, "rotate_to.angle"),
        }
    elif isinstance(effect, ScaleEffect):
        return {
            "type": "scale",
            "sx": _serialize_value(effect.sx, "scale.sx"),
            "sy": _serialize_value(effect.sy, "scale.sy"),
        }
    elif isinstance(effect, BlurEffect):
        return {
            "type": "blur",
            "amount": _serialize_value(effect.amount, "blur.amount"),
        }
    elif isinstance(effect, ShakeEffect):
        return {
            "type": "shake",
            "intensity": _serialize_value(effect.intensity, "shake.intensity"),
            "speed": effect.speed,
        }
    else:
        warnings.warn(
            f"不明なエフェクト型: {type(effect).__name__}",
            UserWarning,
            stacklevel=4
        )
        return None


def _effect_from_dict(data: Dict[str, Any]) -> Optional[Any]:
    """エフェクトを復元"""
    effect_type = data.get("type")
    if effect_type == "move":
        return MoveEffect(
            x=_deserialize_value(data.get("x", 0.0)),
            y=_deserialize_value(data.get("y", 0.0)),
        )
    elif effect_type == "fade":
        alpha_val = _deserialize_value(data.get("alpha"))
        # None の場合はデフォルトで線形フェードイン（0→1）
        if alpha_val is None:
            alpha_val = lambda u: u
        return FadeEffect(alpha=alpha_val)
    elif effect_type == "rotate_to":
        return RotateToEffect(
            angle=_deserialize_value(data.get("angle", 0.0)),
        )
    elif effect_type == "scale":
        return ScaleEffect(
            sx=_deserialize_value(data.get("sx")),
            sy=_deserialize_value(data.get("sy")),
        )
    elif effect_type == "blur":
        return BlurEffect(
            amount=_deserialize_value(data.get("amount", 0.0)),
        )
    elif effect_type == "shake":
        return ShakeEffect(
            intensity=_deserialize_value(data.get("intensity", 0.01)),
            speed=data.get("speed", 10.0),
        )
    else:
        warnings.warn(
            f"不明なエフェクト型: {effect_type}",
            UserWarning,
            stacklevel=4
        )
        return None


def _video_entry_to_dict(entry: VideoEntry) -> Dict[str, Any]:
    """VideoEntry をシリアライズ"""
    effects = []
    for effect in entry.effects:
        effect_dict = _effect_to_dict(effect)
        if effect_dict:
            effects.append(effect_dict)

    return {
        "path": str(entry.media.path),
        "start_time": entry.start_time,
        "duration": entry.duration,
        "layer": entry.layer,
        "order": entry.order,
        "offset": entry.offset,
        "transform": _transform_to_dict(entry.media.transform),
        "effects": effects,
    }


def _video_entry_from_dict(data: Dict[str, Any]) -> VideoEntry:
    """VideoEntry を復元"""
    media = Media(data["path"])
    media.transform = _transform_from_dict(data.get("transform", {}))

    effects = []
    for effect_data in data.get("effects", []):
        effect = _effect_from_dict(effect_data)
        if effect:
            effects.append(effect)

    return VideoEntry(
        media=media,
        start_time=data.get("start_time", 0.0),
        duration=data.get("duration", 1.0),
        effects=effects,
        layer=data.get("layer", 0),
        order=data.get("order", 0),
        offset=data.get("offset", 0.0),
    )


def _audio_entry_to_dict(entry: AudioEntry) -> Dict[str, Any]:
    """AudioEntry をシリアライズ"""
    return {
        "path": str(entry.audio.path),
        "start_time": entry.start_time,
        "duration": entry.duration,
        "volume": entry.audio.volume,
        "fade_in": entry.audio.fade_in,
        "fade_out": entry.audio.fade_out,
    }


def _audio_entry_from_dict(data: Dict[str, Any]) -> AudioEntry:
    """AudioEntry を復元"""
    audio_obj = Audio(data["path"])
    audio_obj.volume = data.get("volume", 1.0)
    audio_obj.fade_in = data.get("fade_in", 0.0)
    audio_obj.fade_out = data.get("fade_out", 0.0)

    return AudioEntry(
        audio=audio_obj,
        start_time=data.get("start_time", 0.0),
        duration=data.get("duration", 1.0),
    )


def _text_entry_to_dict(entry: TextEntry) -> Dict[str, Any]:
    """TextEntry をシリアライズ"""
    effects = []
    for effect in entry.effects:
        effect_dict = _effect_to_dict(effect)
        if effect_dict:
            effects.append(effect_dict)

    return {
        "content": entry.clip.content,
        "start_time": entry.start_time,
        "duration": entry.duration,
        "layer": entry.layer,
        "order": entry.order,
        "transform": _transform_to_dict(entry.clip.transform),
        "style": _text_style_to_dict(entry.clip.style),
        "effects": effects,
    }


def _text_entry_from_dict(data: Dict[str, Any]) -> TextEntry:
    """TextEntry を復元"""
    clip = TextClip(data.get("content", ""))
    clip.transform = _transform_from_dict(data.get("transform", {}))
    clip.style = _text_style_from_dict(data.get("style", {}))

    effects = []
    for effect_data in data.get("effects", []):
        effect = _effect_from_dict(effect_data)
        if effect:
            effects.append(effect)

    return TextEntry(
        clip=clip,
        start_time=data.get("start_time", 0.0),
        duration=data.get("duration", 1.0),
        effects=effects,
        layer=data.get("layer", 0),
        order=data.get("order", 0),
    )


def project_to_dict(timeline: Timeline) -> Dict[str, Any]:
    """Timeline（プロジェクト）を辞書に変換

    Args:
        timeline: シリアライズするタイムライン

    Returns:
        JSON互換の辞書
    """
    return {
        "version": "0.3.0",
        "settings": {
            "width": timeline.width,
            "height": timeline.height,
            "fps": timeline.fps,
            "background_color": timeline.background_color,
            "curve_samples": timeline.curve_samples,
            "strict": timeline.strict,
        },
        "video_entries": [
            _video_entry_to_dict(entry) for entry in timeline.video_entries
        ],
        "audio_entries": [
            _audio_entry_to_dict(entry) for entry in timeline.audio_entries
        ],
        "text_entries": [
            _text_entry_to_dict(entry) for entry in timeline.text_entries
        ],
    }


def project_from_dict(data: Dict[str, Any]) -> Timeline:
    """辞書からTimeline（プロジェクト）を復元

    Args:
        data: シリアライズされた辞書

    Returns:
        復元されたTimeline
    """
    timeline = Timeline()

    # バージョンチェック
    version = data.get("version", "0.0.0")
    if not version.startswith("0.3"):
        warnings.warn(
            f"プロジェクトバージョン {version} は現在のバージョンと異なります",
            UserWarning,
            stacklevel=2
        )

    # 設定の復元
    settings = data.get("settings", {})
    timeline.width = settings.get("width", 1920)
    timeline.height = settings.get("height", 1080)
    timeline.fps = settings.get("fps", 30)
    timeline.background_color = settings.get("background_color", "black")
    timeline.curve_samples = settings.get("curve_samples", 60)
    timeline.strict = settings.get("strict", False)

    # エントリの復元
    for entry_data in data.get("video_entries", []):
        entry = _video_entry_from_dict(entry_data)
        timeline.video_entries.append(entry)

    for entry_data in data.get("audio_entries", []):
        entry = _audio_entry_from_dict(entry_data)
        timeline.audio_entries.append(entry)

    for entry_data in data.get("text_entries", []):
        entry = _text_entry_from_dict(entry_data)
        timeline.text_entries.append(entry)

    # order カウンタを復元
    max_order = 0
    for entry in timeline.video_entries:
        if entry.order > max_order:
            max_order = entry.order
    for entry in timeline.text_entries:
        if entry.order > max_order:
            max_order = entry.order
    timeline._order_counter = max_order + 1

    return timeline
