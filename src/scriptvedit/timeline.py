"""
タイムラインを管理するモジュール
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .media import Media, Audio


@dataclass
class VideoEntry:
    """映像タイムライン上のエントリ"""
    media: "Media"
    start_time: float
    duration: float
    effects: list
    layer: int = 0       # レイヤー（大きいほど手前に描画）
    order: int = 0       # 追加順序（同一layer内での重なり順）
    offset: float = 0.0  # 素材内開始位置（秒）


@dataclass
class AudioEntry:
    """音声タイムライン上のエントリ"""
    audio: "Audio"
    start_time: float
    duration: float


class Timeline:
    """
    グローバルタイムライン

    映像と音声を並列で管理する。
    """

    def __init__(self):
        self.video_entries: list[VideoEntry] = []
        self.audio_entries: list[AudioEntry] = []
        self._video_current_time: float = 0.0
        self._video_order_counter: int = 0  # 追加順序カウンタ
        self.width: int = 1920
        self.height: int = 1080
        self.fps: int = 30
        self.background_color: str = "black"
        self.curve_samples: int = 60  # callable エフェクトのサンプリング数

    def add_video(
        self,
        media: "Media",
        duration: float,
        effects: list,
        start: Optional[float] = None,
        layer: int = 0,
        offset: float = 0.0
    ) -> None:
        """映像をタイムラインに追加

        Args:
            media: メディアオブジェクト
            duration: 表示時間（秒）
            effects: エフェクトのリスト
            start: タイムライン上の開始時間（秒）。省略時は前のメディアの終了後
            layer: レイヤー（大きいほど手前に描画）
            offset: 素材内開始位置（秒）
        """
        # バリデーション
        if duration <= 0:
            raise ValueError(f"duration は正の値である必要があります: {duration}")
        if offset < 0:
            raise ValueError(f"offset は0以上である必要があります: {offset}")

        if start is None:
            start_time = self._video_current_time
            self._video_current_time += duration
        else:
            start_time = start
            # startが指定された場合、current_timeは更新しない（並列配置可能）

        entry = VideoEntry(
            media=media,
            start_time=start_time,
            duration=duration,
            effects=effects,
            layer=layer,
            order=self._video_order_counter,
            offset=offset
        )
        self._video_order_counter += 1
        self.video_entries.append(entry)

    def add_audio(self, audio: "Audio", duration: float, start: Optional[float] = None) -> None:
        """音声をタイムラインに追加"""
        start_time = start if start is not None else 0.0

        entry = AudioEntry(
            audio=audio,
            start_time=start_time,
            duration=duration
        )
        self.audio_entries.append(entry)

    def clear(self) -> None:
        """タイムラインをクリア"""
        self.video_entries.clear()
        self.audio_entries.clear()
        self._video_current_time = 0.0
        self._video_order_counter = 0

    @property
    def total_duration(self) -> float:
        """総再生時間（映像と音声の最大終了時間）"""
        max_video = 0.0
        max_audio = 0.0

        for entry in self.video_entries:
            end_time = entry.start_time + entry.duration
            if end_time > max_video:
                max_video = end_time

        for entry in self.audio_entries:
            end_time = entry.start_time + entry.duration
            if end_time > max_audio:
                max_audio = end_time

        return max(max_video, max_audio)

    def configure(
        self,
        width: int = None,
        height: int = None,
        fps: int = None,
        background_color: str = None,
        curve_samples: int = None
    ) -> None:
        """タイムラインの設定を変更"""
        if width is not None:
            self.width = width
        if height is not None:
            self.height = height
        if fps is not None:
            self.fps = fps
        if background_color is not None:
            self.background_color = background_color
        if curve_samples is not None:
            # 10〜240 でクランプ
            self.curve_samples = max(10, min(240, curve_samples))


# グローバルタイムライン
_timeline = Timeline()


def get_timeline() -> Timeline:
    """グローバルタイムラインを取得"""
    return _timeline


def configure(**kwargs) -> None:
    """タイムラインの設定"""
    _timeline.configure(**kwargs)


def clear() -> None:
    """タイムラインをクリア"""
    _timeline.clear()
