"""
タイムラインを管理するモジュール
"""

import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .media import Media, Audio
    from .text import TextClip


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


@dataclass
class TextEntry:
    """テキストタイムライン上のエントリ"""
    clip: "TextClip"
    start_time: float
    duration: float
    effects: list
    layer: int = 0       # レイヤー（大きいほど手前に描画）
    order: int = 0       # 追加順序（同一layer内での重なり順）


class Timeline:
    """
    グローバルタイムライン

    映像と音声を並列で管理する。
    """

    def __init__(self):
        self.video_entries: list[VideoEntry] = []
        self.audio_entries: list[AudioEntry] = []
        self.text_entries: list[TextEntry] = []
        self._video_current_time: float = 0.0
        self._order_counter: int = 0  # 追加順序カウンタ（video/text共通）
        self.width: int = 1920
        self.height: int = 1080
        self.fps: int = 30
        self.background_color: str = "black"
        self.strict: bool = False  # 素材尺チェックの厳格モード
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

        # 素材尺チェック（動画のみ、画像は無限扱い）
        media_duration = media._get_duration()
        if media_duration is not None:
            required = offset + duration
            eps = 0.01  # 許容誤差
            if required > media_duration + eps:
                msg = (
                    f"素材の長さを超えています: "
                    f"offset({offset}) + duration({duration}) = {required}秒 > "
                    f"素材尺 {media_duration:.2f}秒 ({media.path.name})"
                )
                if self.strict:
                    raise ValueError(msg)
                else:
                    warnings.warn(msg, UserWarning, stacklevel=3)

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
            order=self._order_counter,
            offset=offset
        )
        self._order_counter += 1
        self.video_entries.append(entry)

    def add_audio(self, audio: "Audio", duration: float, start: Optional[float] = None) -> None:
        """音声をタイムラインに追加"""
        # 素材尺チェック
        try:
            audio_duration = audio._get_duration()
            eps = 0.01
            if duration > audio_duration + eps:
                msg = (
                    f"音声の長さを超えています: "
                    f"duration({duration}秒) > 素材尺 {audio_duration:.2f}秒 ({audio.path.name})"
                )
                if self.strict:
                    raise ValueError(msg)
                else:
                    warnings.warn(msg, UserWarning, stacklevel=3)
        except RuntimeError:
            # ffprobe がない場合はスキップ
            pass

        start_time = start if start is not None else 0.0

        entry = AudioEntry(
            audio=audio,
            start_time=start_time,
            duration=duration
        )
        self.audio_entries.append(entry)

    def add_text(
        self,
        clip: "TextClip",
        duration: float,
        effects: list,
        start: Optional[float] = None,
        layer: int = 0
    ) -> None:
        """テキストをタイムラインに追加

        Args:
            clip: TextClipオブジェクト
            duration: 表示時間（秒）
            effects: エフェクトのリスト
            start: タイムライン上の開始時間（秒）
            layer: レイヤー（大きいほど手前に描画）
        """
        # バリデーション
        if duration <= 0:
            raise ValueError(f"duration は正の値である必要があります: {duration}")

        if start is None:
            start_time = self._video_current_time
            self._video_current_time += duration
        else:
            start_time = start

        entry = TextEntry(
            clip=clip,
            start_time=start_time,
            duration=duration,
            effects=effects,
            layer=layer,
            order=self._order_counter
        )
        self._order_counter += 1
        self.text_entries.append(entry)

    def clear(self) -> None:
        """タイムラインをクリア"""
        self.video_entries.clear()
        self.audio_entries.clear()
        self.text_entries.clear()
        self._video_current_time = 0.0
        self._order_counter = 0

    @property
    def total_duration(self) -> float:
        """総再生時間（映像、テキスト、音声の最大終了時間）"""
        max_video = 0.0
        max_audio = 0.0
        max_text = 0.0

        for entry in self.video_entries:
            end_time = entry.start_time + entry.duration
            if end_time > max_video:
                max_video = end_time

        for entry in self.text_entries:
            end_time = entry.start_time + entry.duration
            if end_time > max_text:
                max_text = end_time

        for entry in self.audio_entries:
            end_time = entry.start_time + entry.duration
            if end_time > max_audio:
                max_audio = end_time

        return max(max_video, max_text, max_audio)

    def configure(
        self,
        width: int = None,
        height: int = None,
        fps: int = None,
        background_color: str = None,
        curve_samples: int = None,
        strict: bool = None
    ) -> None:
        """タイムラインの設定を変更

        Args:
            width: 出力幅（ピクセル）
            height: 出力高さ（ピクセル）
            fps: フレームレート
            background_color: 背景色
            curve_samples: callable エフェクトのサンプリング数
            strict: True の場合、素材尺超過でエラー（デフォルトは警告のみ）
        """
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
        if strict is not None:
            self.strict = strict


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
