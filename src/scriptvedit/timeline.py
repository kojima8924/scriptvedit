"""
タイムラインを管理するモジュール
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .media import Media


@dataclass
class TimelineEntry:
    """タイムライン上のエントリ"""
    media: "Media"
    start_time: float
    duration: float
    effects: list


class Timeline:
    """
    グローバルタイムライン

    メディアのshow()が呼ばれると自動的に登録される。
    """

    def __init__(self):
        self.entries: list[TimelineEntry] = []
        self._current_time: float = 0.0
        self.width: int = 1920
        self.height: int = 1080
        self.fps: int = 30
        self.background_color: str = "black"

    def add(self, media: "Media", duration: float, effects: list) -> None:
        """メディアをタイムラインに追加"""
        entry = TimelineEntry(
            media=media,
            start_time=self._current_time,
            duration=duration,
            effects=effects
        )
        self.entries.append(entry)
        self._current_time += duration

    def clear(self) -> None:
        """タイムラインをクリア"""
        self.entries.clear()
        self._current_time = 0.0

    @property
    def total_duration(self) -> float:
        """総再生時間"""
        return self._current_time

    def configure(
        self,
        width: int = None,
        height: int = None,
        fps: int = None,
        background_color: str = None
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
