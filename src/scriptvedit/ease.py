"""
イージング関数ユーティリティ

fade/move/scale/rotate/blur/shake でよく使うカーブを簡単に指定できる。
"""

import math
from typing import Callable


def clamp01(u: float) -> float:
    """u を 0〜1 にクランプする"""
    if u < 0:
        return 0.0
    if u > 1:
        return 1.0
    return u


# ============================================================
# 基本イージング関数
# ============================================================

def linear(u: float) -> float:
    """線形（デフォルト）"""
    return u


def in_quad(u: float) -> float:
    """二次関数（加速）"""
    return u * u


def out_quad(u: float) -> float:
    """二次関数（減速）"""
    return 1 - (1 - u) ** 2


def in_out_quad(u: float) -> float:
    """二次関数（加速→減速）"""
    if u < 0.5:
        return 2 * u * u
    else:
        return 1 - (-2 * u + 2) ** 2 / 2


def in_cubic(u: float) -> float:
    """三次関数（加速）"""
    return u * u * u


def out_cubic(u: float) -> float:
    """三次関数（減速）"""
    return 1 - (1 - u) ** 3


def in_out_cubic(u: float) -> float:
    """三次関数（加速→減速）"""
    if u < 0.5:
        return 4 * u * u * u
    else:
        return 1 - (-2 * u + 2) ** 3 / 2


def in_quart(u: float) -> float:
    """四次関数（加速）"""
    return u * u * u * u


def out_quart(u: float) -> float:
    """四次関数（減速）"""
    return 1 - (1 - u) ** 4


def in_out_quart(u: float) -> float:
    """四次関数（加速→減速）"""
    if u < 0.5:
        return 8 * u * u * u * u
    else:
        return 1 - (-2 * u + 2) ** 4 / 2


def in_sine(u: float) -> float:
    """サイン（加速）"""
    return 1 - math.cos(u * math.pi / 2)


def out_sine(u: float) -> float:
    """サイン（減速）"""
    return math.sin(u * math.pi / 2)


def in_out_sine(u: float) -> float:
    """サイン（加速→減速）"""
    return -(math.cos(math.pi * u) - 1) / 2


def in_expo(u: float) -> float:
    """指数関数（加速）"""
    if u == 0:
        return 0.0
    return 2 ** (10 * u - 10)


def out_expo(u: float) -> float:
    """指数関数（減速）"""
    if u == 1:
        return 1.0
    return 1 - 2 ** (-10 * u)


def in_out_expo(u: float) -> float:
    """指数関数（加速→減速）"""
    if u == 0:
        return 0.0
    if u == 1:
        return 1.0
    if u < 0.5:
        return 2 ** (20 * u - 10) / 2
    else:
        return (2 - 2 ** (-20 * u + 10)) / 2


# ============================================================
# ユーティリティ関数
# ============================================================

def inv(easing: Callable[[float], float]) -> Callable[[float], float]:
    """イージング関数を反転する（in系→out系）

    例: inv(in_quad) は out_quad と同等

    Args:
        easing: 反転するイージング関数

    Returns:
        反転されたイージング関数
    """
    def inverted(u: float) -> float:
        return 1 - easing(1 - u)
    return inverted


def lerp(a: float, b: float, easing: Callable[[float], float] = linear) -> Callable[[float], float]:
    """a から b への補間関数を作成する

    Args:
        a: 開始値（u=0 のとき）
        b: 終了値（u=1 のとき）
        easing: イージング関数（デフォルトは linear）

    Returns:
        u を受け取り補間された値を返す関数

    Examples:
        # 0 から 1 へのイーズイン
        fade(alpha=lerp(0, 1, in_quad))

        # 0 から 360 へのイーズインアウト
        rotate_to(angle=lerp(0, 360, in_out_cubic))

        # 1 から 0 へのイーズアウト（フェードアウト）
        fade(alpha=lerp(1, 0, out_quad))
    """
    def interpolate(u: float) -> float:
        t = easing(clamp01(u))
        return a + (b - a) * t
    return interpolate


def chain(*easings: Callable[[float], float]) -> Callable[[float], float]:
    """複数のイージングを連結する

    Args:
        *easings: 連結するイージング関数

    Returns:
        連結されたイージング関数

    Example:
        # 前半加速、後半減速
        chain(in_quad, out_quad)
    """
    n = len(easings)
    if n == 0:
        return linear
    if n == 1:
        return easings[0]

    def chained(u: float) -> float:
        segment_size = 1.0 / n
        for i, easing in enumerate(easings):
            start = i * segment_size
            end = (i + 1) * segment_size
            if u <= end or i == n - 1:
                local_u = (u - start) / segment_size
                local_u = clamp01(local_u)
                segment_start = i / n
                segment_end = (i + 1) / n
                return segment_start + (segment_end - segment_start) * easing(local_u)
        return 1.0
    return chained
