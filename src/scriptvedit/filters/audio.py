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


def _atempo_chain_rates(rate):
    """atempoの有効範囲(0.5〜100)を超えるレートを複数段に分解する。
    範囲内はそのまま1段で返す（既存出力との互換維持）。"""
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return [rate]
    if r <= 0 or 0.5 <= r <= 100.0:
        return [rate]  # 範囲内（or 不正値はffmpegに検出させる）
    rates = []
    while r < 0.5:
        rates.append(0.5)
        r /= 0.5
    while r > 100.0:
        rates.append(100.0)
        r /= 100.0
    rates.append(_builtins.round(r, 6))
    return rates


def _build_audio_pre_filters(obj):
    """atrim/atempo等の前処理フィルタ"""
    filters = []
    for e in obj.audio_effects:
        if e.name == "atrim":
            d = e.params.get("duration")
            if d is not None:
                filters.append(f"atrim=duration={d}")
                filters.append("asetpts=PTS-STARTPTS")
        elif e.name == "atempo":
            rate = e.params.get("rate", 1.0)
            for r in _atempo_chain_rates(rate):
                filters.append(f"atempo={r}")
    return filters


def _build_audio_effect_filters(obj, dur):
    """音声エフェクトフィルタを生成（again/afade）"""
    filters = []
    for e in obj.audio_effects:
        if e.name == "again":
            value_expr = e.params.get("value", Const(1))
            u_expr = f"clip((t)/{dur}\\,0\\,1)"
            ffmpeg_str = value_expr.to_ffmpeg(u_expr)
            filters.append(f"volume=volume='{ffmpeg_str}':eval=frame")
        elif e.name == "afade":
            alpha_expr = e.params.get("alpha", Const(1.0))
            u_expr = f"clip((t)/{dur}\\,0\\,1)"
            ffmpeg_str = alpha_expr.to_ffmpeg(u_expr)
            filters.append(f"volume=volume='{ffmpeg_str}':eval=frame")
    return filters


# --- 遅延解決の相互参照（関数本体からのみ使用: 循環importを避けるため末尾で束縛）---
from scriptvedit.expr import Const
