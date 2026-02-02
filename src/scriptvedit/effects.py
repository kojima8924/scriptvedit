"""
エフェクトを定義するモジュール

エフェクトの引数には float または callable を指定可能。
callable は正規化時間 u (0.0〜1.0) を引数に取り、値を返す関数。
例: blur(amount=lambda u: 10*u*u)  # 二次関数でブラーが増加
"""

from dataclasses import dataclass
from typing import Callable, Optional, Union

# エフェクト値の型: float または callable（正規化時間 u を受け取り値を返す）
EffectValue = Union[float, Callable[[float], float]]


@dataclass
class MoveEffect:
    """移動エフェクト

    x, y が float の場合: 開始位置から終了位置への線形補間
    x, y が callable の場合: u (0-1) を引数に取る関数で絶対位置を指定
    """
    x: EffectValue
    y: EffectValue

    def __repr__(self) -> str:
        x_str = "<fn>" if callable(self.x) else self.x
        y_str = "<fn>" if callable(self.y) else self.y
        return f"move(x={x_str}, y={y_str})"


@dataclass
class FadeEffect:
    """フェードエフェクト

    alpha が float の場合: 固定透明度（0.0=完全透明, 1.0=不透明）
    alpha が callable の場合: u (0-1) を引数に取る関数で透明度を指定

    例:
        fade(alpha=0.5)             # 常に50%透明
        fade(alpha=lambda u: u)     # フェードイン（0→1）
        fade(alpha=lambda u: 1-u)   # フェードアウト（1→0）
    """
    alpha: EffectValue

    def __repr__(self) -> str:
        if callable(self.alpha):
            return "fade(alpha=<fn>)"
        return f"fade(alpha={self.alpha})"


@dataclass
class RotateToEffect:
    """回転アニメーションエフェクト

    angle が float の場合: 開始角度から終了角度への線形補間
    angle が callable の場合: u (0-1) を引数に取る関数で角度を指定
    """
    angle: EffectValue

    def __repr__(self) -> str:
        angle_str = "<fn>" if callable(self.angle) else self.angle
        return f"rotate_to(angle={angle_str})"


@dataclass
class ScaleEffect:
    """スケールアニメーションエフェクト

    sx, sy が float の場合: 開始スケールから終了スケールへの線形補間
    sx, sy が callable の場合: u (0-1) を引数に取る関数でスケールを指定
    片方が None の場合: アスペクト比を維持
    """
    sx: Optional[EffectValue]
    sy: Optional[EffectValue]

    def __repr__(self) -> str:
        sx_str = "<fn>" if callable(self.sx) else self.sx
        sy_str = "<fn>" if callable(self.sy) else self.sy
        return f"scale(sx={sx_str}, sy={sy_str})"


@dataclass
class BlurEffect:
    """ブラーエフェクト

    amount が float の場合: 0 から amount への線形補間
    amount が callable の場合: u (0-1) を引数に取る関数でブラー量を指定
    """
    amount: EffectValue

    def __repr__(self) -> str:
        amount_str = "<fn>" if callable(self.amount) else self.amount
        return f"blur(amount={amount_str})"


@dataclass
class ShakeEffect:
    """振動エフェクト

    intensity が float の場合: 固定の振動強度
    intensity が callable の場合: u (0-1) を引数に取る関数で振動強度を指定
    speed は常に float（周波数）
    """
    intensity: EffectValue
    speed: float = 10.0

    def __repr__(self) -> str:
        intensity_str = "<fn>" if callable(self.intensity) else self.intensity
        return f"shake(intensity={intensity_str}, speed={self.speed})"


def move(x: EffectValue = 0.0, y: EffectValue = 0.0) -> MoveEffect:
    """
    移動エフェクトを作成する

    Args:
        x: X方向の移動先（0.0〜1.0、画面の割合）
           callable の場合は u (0-1) を引数に取る関数
        y: Y方向の移動先（0.0〜1.0、画面の割合）
           callable の場合は u (0-1) を引数に取る関数

    Returns:
        MoveEffectオブジェクト
    """
    return MoveEffect(x=x, y=y)


def fade(alpha: EffectValue = 1.0) -> FadeEffect:
    """
    フェードエフェクトを作成する

    Args:
        alpha: 透明度（0.0=完全透明, 1.0=不透明）
               float の場合は固定透明度
               callable の場合は u (0-1) を引数に取る関数

    Examples:
        fade(alpha=0.5)             # 常に50%透明
        fade(alpha=lambda u: u)     # フェードイン（0→1）
        fade(alpha=lambda u: 1-u)   # フェードアウト（1→0）

    Returns:
        FadeEffectオブジェクト
    """
    return FadeEffect(alpha=alpha)


def rotate_to(angle: EffectValue) -> RotateToEffect:
    """
    回転アニメーションエフェクトを作成する

    Args:
        angle: 最終回転角度（度）
               callable の場合は u (0-1) を引数に取る関数

    Returns:
        RotateToEffectオブジェクト
    """
    return RotateToEffect(angle=angle)


def scale(sx: Optional[EffectValue] = None, sy: Optional[EffectValue] = None) -> ScaleEffect:
    """
    スケールアニメーションエフェクトを作成する

    Args:
        sx: X方向の最終スケール（画面に対する割合。Noneでアスペクト比維持）
            callable の場合は u (0-1) を引数に取る関数
        sy: Y方向の最終スケール（画面に対する割合。Noneでアスペクト比維持）
            callable の場合は u (0-1) を引数に取る関数

    Note:
        片方のみ指定でアスペクト比を維持してスケール

    Returns:
        ScaleEffectオブジェクト
    """
    return ScaleEffect(sx=sx, sy=sy)


def blur(amount: EffectValue) -> BlurEffect:
    """
    ブラーエフェクトを作成する（徐々にブラーがかかる）

    Args:
        amount: 最終ブラー量（ピクセル）
                callable の場合は u (0-1) を引数に取る関数

    Returns:
        BlurEffectオブジェクト
    """
    return BlurEffect(amount=amount)


def shake(intensity: EffectValue, speed: float = 10.0) -> ShakeEffect:
    """
    振動エフェクトを作成する

    Args:
        intensity: 振動の強さ（画面に対する割合、0.01=1%）
                   callable の場合は u (0-1) を引数に取る関数
        speed: 振動の速さ（Hz）

    Returns:
        ShakeEffectオブジェクト
    """
    return ShakeEffect(intensity=intensity, speed=speed)
