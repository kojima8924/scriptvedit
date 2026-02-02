"""
エフェクトを定義するモジュール
"""

from dataclasses import dataclass
from typing import Callable, Union


@dataclass
class MoveEffect:
    """移動エフェクト"""
    x: float
    y: float

    def __repr__(self) -> str:
        return f"move(x={self.x}, y={self.y})"


@dataclass
class FadeEffect:
    """フェードエフェクト"""
    alpha: Union[float, Callable[[float], float]]

    def __repr__(self) -> str:
        if callable(self.alpha):
            return "fade(alpha=<function>)"
        return f"fade(alpha={self.alpha})"


@dataclass
class RotateToEffect:
    """回転アニメーションエフェクト"""
    angle: float

    def __repr__(self) -> str:
        return f"rotate_to(angle={self.angle})"


@dataclass
class ScaleEffect:
    """スケールアニメーションエフェクト"""
    sx: float
    sy: float

    def __repr__(self) -> str:
        return f"scale(sx={self.sx}, sy={self.sy})"


@dataclass
class BlurEffect:
    """ブラーエフェクト"""
    amount: float

    def __repr__(self) -> str:
        return f"blur(amount={self.amount})"


@dataclass
class ShakeEffect:
    """振動エフェクト"""
    intensity: float
    speed: float = 10.0

    def __repr__(self) -> str:
        return f"shake(intensity={self.intensity})"


def move(x: float = 0.0, y: float = 0.0) -> MoveEffect:
    """
    移動エフェクトを作成する

    Args:
        x: X方向の移動先（0.0〜1.0、画面の割合）
        y: Y方向の移動先（0.0〜1.0、画面の割合）

    Returns:
        MoveEffectオブジェクト
    """
    return MoveEffect(x=x, y=y)


def fade(alpha: Union[float, Callable[[float], float]] = 0.0) -> FadeEffect:
    """
    フェードエフェクトを作成する

    Args:
        alpha: 透明度（0.0〜1.0）または時間tを引数に取る関数

    Returns:
        FadeEffectオブジェクト
    """
    return FadeEffect(alpha=alpha)


def rotate_to(angle: float) -> RotateToEffect:
    """
    回転アニメーションエフェクトを作成する

    Args:
        angle: 最終回転角度（度）

    Returns:
        RotateToEffectオブジェクト
    """
    return RotateToEffect(angle=angle)


def scale(sx: float = 1.0, sy: float = None) -> ScaleEffect:
    """
    スケールアニメーションエフェクトを作成する

    Args:
        sx: X方向の最終スケール（画面に対する割合）
        sy: Y方向の最終スケール（省略時はsxと同じ）

    Returns:
        ScaleEffectオブジェクト
    """
    if sy is None:
        sy = sx
    return ScaleEffect(sx=sx, sy=sy)


def blur(amount: float) -> BlurEffect:
    """
    ブラーエフェクトを作成する（徐々にブラーがかかる）

    Args:
        amount: 最終ブラー量（ピクセル）

    Returns:
        BlurEffectオブジェクト
    """
    return BlurEffect(amount=amount)


def shake(intensity: float, speed: float = 10.0) -> ShakeEffect:
    """
    振動エフェクトを作成する

    Args:
        intensity: 振動の強さ（画面に対する割合、0.01=1%）
        speed: 振動の速さ（Hz）

    Returns:
        ShakeEffectオブジェクト
    """
    return ShakeEffect(intensity=intensity, speed=speed)
