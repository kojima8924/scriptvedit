"""
メディア（画像・動画）を扱うモジュール
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class Transform:
    """変換情報"""
    scale_x: float = 1.0
    scale_y: float = 1.0
    pos_x: float = 0.0
    pos_y: float = 0.0
    anchor: str = "center"
    rotation: float = 0.0
    alpha: float = 1.0
    flip_h: bool = False
    flip_v: bool = False
    crop_x: float = 0.0
    crop_y: float = 0.0
    crop_w: float = 1.0
    crop_h: float = 1.0


@dataclass
class ShowCommand:
    """表示コマンド"""
    time: float
    effects: list = field(default_factory=list)


class Media:
    """
    メディアオブジェクト（画像・動画）

    メソッドチェーンで変換やエフェクトを適用できる。
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self.transform = Transform()
        self._show_commands: list[ShowCommand] = []

    def resize(self, sx: float = 1.0, sy: float = 1.0) -> "Media":
        """
        リサイズする（画面サイズに対する相対値）

        Args:
            sx: 幅（0.0〜1.0、画面幅に対する割合。1.0=画面幅100%）
            sy: 高さ（0.0〜1.0、画面高さに対する割合。1.0=画面高さ100%）

        Returns:
            self（メソッドチェーン用）
        """
        self.transform.scale_x = sx
        self.transform.scale_y = sy
        return self

    def pos(self, x: float = 0.0, y: float = 0.0, anchor: str = "center") -> "Media":
        """
        位置を設定する

        Args:
            x: X座標（0.0〜1.0、画面の割合）
            y: Y座標（0.0〜1.0、画面の割合）
            anchor: アンカーポイント（"tl", "center", "br" など）

        Returns:
            self（メソッドチェーン用）
        """
        self.transform.pos_x = x
        self.transform.pos_y = y
        self.transform.anchor = anchor
        return self

    def rotate(self, angle: float) -> "Media":
        """
        回転角度を設定する

        Args:
            angle: 回転角度（度、時計回りが正）

        Returns:
            self（メソッドチェーン用）
        """
        self.transform.rotation = angle
        return self

    def opacity(self, alpha: float) -> "Media":
        """
        初期透明度を設定する

        Args:
            alpha: 透明度（0.0=完全透明、1.0=不透明）

        Returns:
            self（メソッドチェーン用）
        """
        self.transform.alpha = alpha
        return self

    def flip(self, horizontal: bool = False, vertical: bool = False) -> "Media":
        """
        反転を設定する

        Args:
            horizontal: 水平反転
            vertical: 垂直反転

        Returns:
            self（メソッドチェーン用）
        """
        self.transform.flip_h = horizontal
        self.transform.flip_v = vertical
        return self

    def crop(self, x: float = 0.0, y: float = 0.0, w: float = 1.0, h: float = 1.0) -> "Media":
        """
        トリミング領域を設定する（元画像に対する相対値）

        Args:
            x: 左上X（0.0〜1.0）
            y: 左上Y（0.0〜1.0）
            w: 幅（0.0〜1.0）
            h: 高さ（0.0〜1.0）

        Returns:
            self（メソッドチェーン用）
        """
        self.transform.crop_x = x
        self.transform.crop_y = y
        self.transform.crop_w = w
        self.transform.crop_h = h
        return self

    def show(self, time: float, effects: Optional[list] = None) -> "Media":
        """
        指定時間表示する（グローバルタイムラインに登録）

        Args:
            time: 表示時間（秒）
            effects: 適用するエフェクトのリスト

        Returns:
            self（メソッドチェーン用）
        """
        from .timeline import get_timeline
        get_timeline().add(self, duration=time, effects=effects or [])
        return self


def open(path: str) -> Media:
    """
    メディアファイルを開く

    Args:
        path: ファイルパス

    Returns:
        Mediaオブジェクト
    """
    return Media(path)
