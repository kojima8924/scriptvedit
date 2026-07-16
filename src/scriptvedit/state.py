# -*- coding: utf-8 -*-

import subprocess
import os
import re
import sys
import json
import hashlib
import math as _math
import warnings
import builtins as _builtins
import time as _time
import difflib as _difflib
import shutil as _shutil
import concurrent.futures as _futures
import inspect as _inspect


# --- media_type判定 ---

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".gif"}
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
_WEB_EXTS = {".html", ".htm"}


def _detect_media_type(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in _AUDIO_EXTS:
        return "audio"
    if ext in _WEB_EXTS:
        return "web"
    return "image"  # フォールバック


# --- ffmpeg実行ヘルパー ---

# Windowsのコマンドライン長制限対策: フィルタ文字列がこの長さを超えたら一時ファイル経由で渡す


# --- configure許可キー ---

_CONFIGURE_KEYS = {"width", "height", "fps", "duration", "background_color",
                   "preset", "encoder", "parallel"}

# 出力プリセット: name -> (width, height, fps)
_PRESETS = {
    "shorts": (1080, 1920, 30),
    "reel":   (1080, 1920, 30),
    "reels":  (1080, 1920, 30),
    "tiktok": (1080, 1920, 30),
    "vertical": (1080, 1920, 30),
    "square": (1080, 1080, 30),
    "hd":     (1920, 1080, 30),
    "fhd":    (1920, 1080, 30),
    "1080p":  (1920, 1080, 30),
    "720p":   (1280, 720, 30),
    "2k":     (2560, 1440, 30),
    "4k":     (3840, 2160, 30),
}

# エンコーダ名 -> {cv: -c:v の値, args: 追加エンコード引数, draft: ドラフト用引数}
_ENCODER_MAP = {
    # libx264 の既定は追加引数なし（従来の出力・スナップショットと一致させる）
    "libx264":    {"cv": "libx264", "args": [],
                   "draft": ["-preset", "ultrafast", "-crf", "28"]},
    "nvenc":      {"cv": "h264_nvenc", "args": ["-preset", "p5", "-cq", "23"],
                   "draft": ["-preset", "p1", "-cq", "30"]},
    "hevc_nvenc": {"cv": "hevc_nvenc", "args": ["-preset", "p5", "-cq", "25"],
                   "draft": ["-preset", "p1", "-cq", "32"]},
    "qsv":        {"cv": "h264_qsv", "args": ["-global_quality", "23"],
                   "draft": ["-global_quality", "32"]},
    "hevc":       {"cv": "libx265", "args": ["-preset", "medium", "-crf", "24"],
                   "draft": ["-preset", "ultrafast", "-crf", "30"]},
}

# 生成した中間ファイル数のカウンタ（render統計用。render開始時にリセット）
_GEN_COUNTER = [0]
# _GEN_COUNTER の並列更新保護（並列レイヤー生成での過少計上を防ぐ）
import threading as _threading
_GEN_COUNTER_LOCK = _threading.Lock()

# 有効な出力品質サフィックス（draft時にチェックポイント鍵へ混ぜ本番と分離）
_ACTIVE_QUALITY = [""]

# ffmpeg 利用可能エンコーダ集合のキャッシュ（None=未取得）
_AVAILABLE_ENCODERS = [None]


def _suggest_hint(name, candidates, prefix="\nもしかして: "):
    """未知の名前に対し近い候補を difflib で探し、'もしかして: X?' を返す。
    候補が無ければ空文字列。エラーメッセージ末尾に連結して使う。"""
    try:
        matches = _difflib.get_close_matches(
            str(name), [str(c) for c in candidates], n=3, cutoff=0.6)
    except Exception:
        matches = []
    if not matches:
        return ""
    return f"{prefix}{', '.join(matches)}?"


_CACHE_DIR = "__cache__"
_CHECKPOINT_DIR = os.path.join(_CACHE_DIR, "checkpoints")
_ARTIFACT_DIR = os.path.join(_CACHE_DIR, "artifacts")
_ENGINE_VER = "8"
_BAKEABLE_EFFECTS = {"scale", "fade", "trim", "morph_to", "rotate_to", "wipe", "color_shift",
                     "chroma_key", "vignette", "pixelize", "glow", "lut", "glitch",
                     "perspective_warp", "lens", "ken_burns", "drop_shadow", "outline",
                     "explode_to", "assemble_from",
                     "mask", "mask_wipe", "opacity", "rounded"}

# 終端フレーム生成Effect（bakeable末尾に1つだけ・映像を生成する）
_TERMINAL_FRAME_EFFECTS = {"morph_to", "explode_to", "assemble_from"}

# 時間操作系の live Effect（setpts/reverse/concat による時間変形）。
# チェックポイントベイクの表示尺基準と食い違うため bakeable にはしない
# （ベイク済みソースに対して毎レンダ live で適用する）。
_TIME_LIVE_EFFECTS = {"speed", "reverse", "freeze_frame"}

# reverse Effect の実効尺上限（全フレームをメモリに保持するため長尺は危険）
_REVERSE_MAX_SEC = 30.0


# --- パッケージ名前空間（プラグイン注入・describe のイントロスペクション用）---
# 旧単一ファイル版の globals() / __all__ に相当。分割後は公開名前空間である
# scriptvedit パッケージ本体を指す（プラグインのファクトリはここへ注入される）。
def _pkg_ns():
    """scriptvedit パッケージの名前空間 dict を返す"""
    return sys.modules["scriptvedit"].__dict__


def _pkg_all():
    """scriptvedit パッケージの __all__ リスト（実体・破壊的更新可）を返す"""
    return sys.modules["scriptvedit"].__all__
