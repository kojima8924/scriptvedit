"""
メディア（画像・動画）を扱うモジュール
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any
import subprocess
import shutil
import json


@dataclass
class Transform:
    """変換情報"""
    scale_x: Optional[float] = None  # Noneでアスペクト比維持
    scale_y: Optional[float] = None  # Noneでアスペクト比維持
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
    chromakey_color: Optional[str] = None  # クロマキー色（例: "0x00FF00", "green"）
    chromakey_similarity: float = 0.1      # 類似度（0-1）
    chromakey_blend: float = 0.1           # エッジブレンド（0-1）


@dataclass
class ShowCommand:
    """表示コマンド"""
    time: float
    effects: list = field(default_factory=list)


def _get_media_dimensions(path: Path) -> tuple[int, int]:
    """ffprobeを使ってメディアの幅と高さを取得"""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobeが見つかりません")

    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobeエラー: {result.stderr}")

    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return stream["width"], stream["height"]


def _detect_chromakey_color(path: Path) -> str:
    """画像の四隅から背景色を自動検出する"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpegが見つかりません")

    # 四隅のピクセル色を取得（左上、右上、左下、右下の1x1ピクセル）
    corners = []
    positions = [
        "0:0:1:1",      # 左上
        "iw-1:0:1:1",   # 右上
        "0:ih-1:1:1",   # 左下
        "iw-1:ih-1:1:1" # 右下
    ]

    for pos in positions:
        cmd = [
            ffmpeg, "-v", "error",
            "-i", str(path),
            "-vf", f"crop={pos},format=rgb24",
            "-f", "rawvideo",
            "-frames:v", "1",
            "pipe:1"
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0 and len(result.stdout) >= 3:
            r, g, b = result.stdout[0], result.stdout[1], result.stdout[2]
            corners.append((r, g, b))

    if not corners:
        return "green"  # デフォルト

    # 最も多い色を選択（または平均）
    from collections import Counter
    color_counts = Counter(corners)
    most_common = color_counts.most_common(1)[0][0]
    r, g, b = most_common

    return f"0x{r:02X}{g:02X}{b:02X}"


class Media:
    """
    メディアオブジェクト（画像・動画）

    メソッドチェーンで変換やエフェクトを適用できる。
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self.transform = Transform()
        self._show_commands: list[ShowCommand] = []
        self._width: Optional[int] = None
        self._height: Optional[int] = None

    def _ensure_dimensions(self) -> tuple[int, int]:
        """画像サイズを取得（キャッシュ）"""
        if self._width is None or self._height is None:
            self._width, self._height = _get_media_dimensions(self.path)
        return self._width, self._height

    def resize(self, sx: float = None, sy: float = None) -> "Media":
        """
        リサイズする（画面サイズに対する相対値）

        Args:
            sx: 幅（0.0〜1.0、画面幅に対する割合。Noneでアスペクト比維持）
            sy: 高さ（0.0〜1.0、画面高さに対する割合。Noneでアスペクト比維持）

        Note:
            両方Noneの場合は元のサイズを維持
            片方のみ指定でアスペクト比を維持してリサイズ

        Returns:
            self（メソッドチェーン用）
        """
        from .timeline import get_timeline

        # 片方のみ指定の場合、アスペクト比を計算
        if sx is not None and sy is None:
            img_w, img_h = self._ensure_dimensions()
            timeline = get_timeline()
            # sy = sx * (img_h / img_w) * (screen_w / screen_h)
            sy = sx * (img_h / img_w) * (timeline.width / timeline.height)
        elif sy is not None and sx is None:
            img_w, img_h = self._ensure_dimensions()
            timeline = get_timeline()
            # sx = sy * (img_w / img_h) * (screen_h / screen_w)
            sx = sy * (img_w / img_h) * (timeline.height / timeline.width)

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

    def chromakey(self, color: str = None, similarity: float = 0.1, blend: float = 0.1) -> "Media":
        """
        クロマキー（カラーキー）を設定する

        Args:
            color: 透明にする色（"green", "blue", "0x00FF00"など）。省略時は自動検出
            similarity: 色の類似度（0.0〜1.0、大きいほど広い範囲を透明化）
            blend: エッジのブレンド（0.0〜1.0、大きいほど滑らか）

        Returns:
            self（メソッドチェーン用）
        """
        if color is None:
            color = _detect_chromakey_color(self.path)
            print(f"クロマキー色を自動検出: {color}")
        self.transform.chromakey_color = color
        self.transform.chromakey_similarity = similarity
        self.transform.chromakey_blend = blend
        return self

    def show(self, time: float, effects: Optional[list] = None, start: Optional[float] = None) -> "Media":
        """
        指定時間表示する（グローバルタイムラインに登録）

        Args:
            time: 表示時間（秒）
            effects: 適用するエフェクトのリスト
            start: 開始時間（秒）。省略時は前のメディアの終了後

        Returns:
            self（メソッドチェーン用）
        """
        from .timeline import get_timeline
        get_timeline().add_video(self, duration=time, effects=effects or [], start=start)
        return self


class Audio:
    """
    音声オブジェクト

    音声ファイルを扱うクラス。
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self.volume: float = 1.0
        self.fade_in: float = 0.0
        self.fade_out: float = 0.0
        self._duration: Optional[float] = None

    def _get_duration(self) -> float:
        """音声の長さを取得"""
        if self._duration is None:
            ffprobe = shutil.which("ffprobe")
            if not ffprobe:
                raise RuntimeError("ffprobeが見つかりません")
            cmd = [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(self.path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"ffprobeエラー: {result.stderr}")
            data = json.loads(result.stdout)
            self._duration = float(data["format"]["duration"])
        return self._duration

    def set_volume(self, volume: float) -> "Audio":
        """
        音量を設定する

        Args:
            volume: 音量（1.0=100%）

        Returns:
            self（メソッドチェーン用）
        """
        self.volume = volume
        return self

    def set_fade(self, fade_in: float = 0.0, fade_out: float = 0.0) -> "Audio":
        """
        フェードイン/アウトを設定する

        Args:
            fade_in: フェードイン時間（秒）
            fade_out: フェードアウト時間（秒）

        Returns:
            self（メソッドチェーン用）
        """
        self.fade_in = fade_in
        self.fade_out = fade_out
        return self

    def play(self, time: Optional[float] = None, start: Optional[float] = None) -> "Audio":
        """
        音声を再生する（グローバルタイムラインに登録）

        Args:
            time: 再生時間（秒）。省略時は音声全体
            start: 開始時間（秒）。省略時は0

        Returns:
            self（メソッドチェーン用）
        """
        from .timeline import get_timeline
        duration = time if time is not None else self._get_duration()
        get_timeline().add_audio(self, duration=duration, start=start)
        return self


def open(path: str) -> Media:
    """
    画像/動画ファイルを開く

    Args:
        path: ファイルパス

    Returns:
        Mediaオブジェクト
    """
    return Media(path)


def audio(path: str) -> Audio:
    """
    音声ファイルを開く

    Args:
        path: ファイルパス

    Returns:
        Audioオブジェクト
    """
    return Audio(path)
