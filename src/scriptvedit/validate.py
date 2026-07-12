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


# --- Effect用バリデーションヘルパー ---

_COLOR_NAME_RGB = {
    "black": (0, 0, 0), "white": (255, 255, 255),
    "red": (255, 0, 0), "green": (0, 128, 0), "lime": (0, 255, 0),
    "blue": (0, 0, 255), "yellow": (255, 255, 0), "cyan": (0, 255, 255),
    "magenta": (255, 0, 255), "gray": (128, 128, 128), "grey": (128, 128, 128),
    "orange": (255, 165, 0), "purple": (128, 0, 128), "pink": (255, 192, 203),
    "brown": (165, 42, 42), "navy": (0, 0, 128),
}


def _parse_color_rgb(color):
    """色名/16進文字列を (R, G, B) タプルに変換（drop_shadow/outline のgeq色付け用）"""
    if not isinstance(color, str) or not color:
        raise ValueError(f"color には色名か16進(#RRGGBB)の文字列を指定してください: {color!r}")
    s = color.strip().lower()
    if s.startswith("#"):
        s = s[1:]
    elif s.startswith("0x"):
        s = s[2:]
    else:
        if s in _COLOR_NAME_RGB:
            return _COLOR_NAME_RGB[s]
        raise ValueError(
            f"未対応の色名です: '{color}'。"
            f"対応色名: {', '.join(sorted(_COLOR_NAME_RGB))} または16進(#RRGGBB)")
    if len(s) != 6 or any(c not in "0123456789abcdef" for c in s):
        raise ValueError(f"16進カラーは #RRGGBB / 0xRRGGBB 形式で指定してください: '{color}'")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _validate_ffmpeg_color(func_name, color):
    """ffmpegに渡す色指定（色名 or 16進）を検証し正規化して返す"""
    if not isinstance(color, str) or not color:
        raise ValueError(f"{func_name}: color には色名か16進の文字列を指定してください: {color!r}")
    s = color.strip()
    if s.startswith("#") or s.lower().startswith("0x"):
        h = s[1:] if s.startswith("#") else s[2:]
        if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
            raise ValueError(f"{func_name}: 16進カラーは #RRGGBB / 0xRRGGBB 形式です: '{color}'")
        return "0x" + h.upper()
    if not s.isalpha():
        raise ValueError(f"{func_name}: 無効な色指定です: '{color}'")
    return s.lower()


def _require_number(func_name, param_name, value, lo=None, hi=None):
    """定数数値パラメータの型・範囲検証（Expr/lambda不可）"""
    if isinstance(value, Expr) or callable(value):
        raise ValueError(
            f"{func_name}: {param_name} には Expr/lambda は使えません（定数のみ）")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{func_name}: {param_name} は数値で指定してください: {value!r}")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        rng = f"{lo if lo is not None else ''}〜{hi if hi is not None else ''}"
        raise ValueError(
            f"{func_name}: {param_name} は {rng} の範囲で指定してください: {value}")
    return value


# --- 遅延解決の相互参照（関数本体からのみ使用: 循環importを避けるため末尾で束縛）---
from scriptvedit.expr import Expr
