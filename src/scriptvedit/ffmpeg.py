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


_FILTER_SCRIPT_THRESHOLD = 4000


def _externalize_long_filters(cmd):
    """フィルタ文字列が閾値を超える場合、一時ファイル + FFmpeg 8 の `-/オプション` 構文に差し替える

    例: `-filter_complex <長大な文字列>` → `-/filter_complex <一時ファイルパス>`
    Returns: (実行用cmd, 一時ファイルパスのリスト)
    """
    import tempfile
    new_cmd = list(cmd)
    tmp_files = []
    for opt in ("-filter_complex", "-vf", "-af"):
        for i in range(len(new_cmd) - 1):
            if new_cmd[i] == opt and len(new_cmd[i + 1]) >= _FILTER_SCRIPT_THRESHOLD:
                fd, path = tempfile.mkstemp(suffix=".txt", prefix="svfilter_")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(new_cmd[i + 1])
                new_cmd[i] = f"-/{opt.lstrip('-')}"
                new_cmd[i + 1] = path
                tmp_files.append(path)
                break
    return new_cmd, tmp_files


def _run_ffmpeg(cmd, timeout=600):
    """ffmpegコマンドを実行（長大フィルタは一時ファイル経由で渡し、実行後に削除）"""
    run_cmd, tmp_files = _externalize_long_filters(cmd)
    try:
        subprocess.run(run_cmd, check=True, timeout=timeout)
    finally:
        for path in tmp_files:
            try:
                os.remove(path)
            except OSError:
                pass


def _run_ffmpeg_to_cache(cmd, cache_path, timeout=600):
    """ffmpegを一時パスへ出力し、成功時のみ os.replace でキャッシュパスに確定する

    タイムアウトやCtrl-Cで壊れた部分ファイルがキャッシュとして残り、
    以後 os.path.exists() 判定で恒久的に使われ続けるのを防ぐ。
    cmd 内の cache_path と一致する引数を一時パス（拡張子は維持）に差し替えて実行する。
    """
    base, ext = os.path.splitext(cache_path)
    tmp_path = f"{base}.tmp{ext}"
    replaced = sum(1 for arg in cmd if arg == cache_path)
    if replaced == 0:
        # 置換0件のまま実行すると非アトミック書き込み後にos.replaceが
        # FileNotFoundErrorになるため、ここで即座に検出する
        raise ValueError(
            f"_run_ffmpeg_to_cache: cmd内に出力先cache_pathが見つかりません: {cache_path}\n"
            f"コマンド構築時と実行時で出力パスが食い違っています。")
    run_cmd = [tmp_path if arg == cache_path else arg for arg in cmd]
    try:
        _run_ffmpeg(run_cmd, timeout=timeout)
        os.replace(tmp_path, cache_path)
        with _GEN_COUNTER_LOCK:  # 並列レイヤー生成からの同時更新をアトミック化
            _GEN_COUNTER[0] += 1  # render統計用: 生成した中間ファイル数
    finally:
        # 失敗時に残った一時ファイルを削除（成功時はos.replace済みで存在しない）
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _ffmpeg_available_encoders():
    """ffmpeg -encoders を1回だけ実行し、利用可能なエンコーダ名の集合を返す"""
    if _AVAILABLE_ENCODERS[0] is not None:
        return _AVAILABLE_ENCODERS[0]
    names = set()
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=30)
        for line in out.stdout.splitlines():
            # 例: " V..... libx264   ..." 先頭にフラグ列、続いてエンコーダ名
            parts = line.split()
            if len(parts) >= 2 and parts[0] and parts[0][0] in "VAS":
                names.add(parts[1])
    except Exception:
        names = set()
    _AVAILABLE_ENCODERS[0] = names
    return names


# --- フィルタ生成ヘルパー ---

def _decoder_input_args(source, media_type, fps):
    """メディア種別に応じたffmpeg入力デコーダ引数を構築（全経路共通）

    本レンダ/レイヤーキャッシュ/チェックポイント/computeで共通利用し、
    webmデコーダ判定等の重複と乖離を防ぐ。
    """
    if media_type == "image":
        return ["-loop", "1", "-r", str(fps), "-i", source]
    if media_type != "audio" and source.lower().endswith(".webm"):
        # WebM(VP9 alpha)はlibvpx-vp9デコーダが必要
        # (ffmpeg 8.0のネイティブVP9デコーダはalpha非対応)
        return ["-c:v", "libvpx-vp9", "-i", source]
    return ["-i", source]


# --- 遅延解決の相互参照（関数本体からのみ使用: 循環importを避けるため末尾で束縛）---
from scriptvedit.state import _AVAILABLE_ENCODERS, _GEN_COUNTER, _GEN_COUNTER_LOCK
