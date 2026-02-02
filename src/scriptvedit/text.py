"""
テキストオーバーレイを扱うモジュール
"""

from dataclasses import dataclass, field
from typing import Optional, Union, Callable, TYPE_CHECKING

from .media import Transform, TransformValue, _chain, _UNSET

if TYPE_CHECKING:
    from .timeline import Timeline


@dataclass
class TextStyle:
    """テキストのスタイル設定

    FFmpeg drawtext フィルタのオプションに対応する。
    """
    fontfile: Optional[str] = None        # フォントファイルパス
    fontsize: int = 48                     # フォントサイズ（ピクセル）
    fontcolor: str = "white"               # フォント色（FFmpeg形式）
    box: bool = False                      # 背景ボックス表示
    boxcolor: str = "black@0.5"            # 背景ボックス色
    boxborderw: int = 5                    # ボックス境界幅
    borderw: int = 0                       # テキスト縁取り幅
    bordercolor: str = "black"             # テキスト縁取り色
    shadowx: int = 0                       # 影のXオフセット
    shadowy: int = 0                       # 影のYオフセット
    shadowcolor: str = "black@0.5"         # 影の色


class TextClip:
    """
    テキストオーバーレイオブジェクト

    Media と同様のインターフェースで、テキストを画面に配置できる。
    """

    def __init__(self, content: str):
        """
        Args:
            content: 表示するテキスト
        """
        self.content = content
        self.transform = Transform()
        self.style = TextStyle()
        # テキストはアスペクト比計算不要なのでデフォルト位置を設定
        self.transform.pos_x = 0.5
        self.transform.pos_y = 0.5

    def font(
        self,
        file: Union[str, object] = _UNSET,
        size: Union[int, object] = _UNSET,
        color: Union[str, object] = _UNSET
    ) -> "TextClip":
        """
        フォントを設定する

        Args:
            file: フォントファイルパス
            size: フォントサイズ（ピクセル）
            color: フォント色

        Returns:
            self（メソッドチェーン用）
        """
        if file is not _UNSET:
            self.style.fontfile = file
        if size is not _UNSET:
            self.style.fontsize = size
        if color is not _UNSET:
            self.style.fontcolor = color
        return self

    def box(
        self,
        enable: bool = True,
        color: Union[str, object] = _UNSET,
        borderw: Union[int, object] = _UNSET
    ) -> "TextClip":
        """
        背景ボックスを設定する

        Args:
            enable: ボックス表示
            color: ボックス色
            borderw: ボックス境界幅

        Returns:
            self（メソッドチェーン用）
        """
        self.style.box = enable
        if color is not _UNSET:
            self.style.boxcolor = color
        if borderw is not _UNSET:
            self.style.boxborderw = borderw
        return self

    def border(
        self,
        width: Union[int, object] = _UNSET,
        color: Union[str, object] = _UNSET
    ) -> "TextClip":
        """
        テキストの縁取りを設定する

        Args:
            width: 縁取り幅
            color: 縁取り色

        Returns:
            self（メソッドチェーン用）
        """
        if width is not _UNSET:
            self.style.borderw = width
        if color is not _UNSET:
            self.style.bordercolor = color
        return self

    def shadow(
        self,
        x: Union[int, object] = _UNSET,
        y: Union[int, object] = _UNSET,
        color: Union[str, object] = _UNSET
    ) -> "TextClip":
        """
        影を設定する

        Args:
            x: 影のXオフセット
            y: 影のYオフセット
            color: 影の色

        Returns:
            self（メソッドチェーン用）
        """
        if x is not _UNSET:
            self.style.shadowx = x
        if y is not _UNSET:
            self.style.shadowy = y
        if color is not _UNSET:
            self.style.shadowcolor = color
        return self

    def pos(
        self,
        x: Union[TransformValue, object] = _UNSET,
        y: Union[TransformValue, object] = _UNSET,
        anchor: Union[str, object] = _UNSET
    ) -> "TextClip":
        """
        位置を設定する

        Args:
            x: X座標（0.0〜1.0、画面の割合）
            y: Y座標（0.0〜1.0、画面の割合）
            anchor: アンカーポイント（"tl", "center", "br" など）

        Returns:
            self（メソッドチェーン用）
        """
        if x is not _UNSET:
            self.transform.pos_x = _chain(self.transform.pos_x, x)
        if y is not _UNSET:
            self.transform.pos_y = _chain(self.transform.pos_y, y)
        if anchor is not _UNSET:
            self.transform.anchor = anchor
        return self

    def opacity(self, alpha: Union[TransformValue, object] = _UNSET) -> "TextClip":
        """
        透明度を設定する

        Args:
            alpha: 透明度（0.0=完全透明、1.0=不透明）

        Returns:
            self（メソッドチェーン用）
        """
        if alpha is not _UNSET:
            self.transform.alpha = _chain(self.transform.alpha, alpha)
        return self

    def show(
        self,
        timeline: "Timeline",
        time: float,
        effects: Optional[list] = None,
        start: Optional[float] = None,
        layer: int = 0
    ) -> "TextClip":
        """
        指定時間表示する（タイムラインに登録）

        Args:
            timeline: 登録先のタイムライン
            time: 表示時間（秒）
            effects: 適用するエフェクトのリスト（fade のみ対応）
            start: タイムライン上の開始時間（秒）
            layer: レイヤー（大きいほど手前に描画）

        Returns:
            self（メソッドチェーン用）
        """
        from .timeline import Timeline as TL
        if not isinstance(timeline, TL):
            raise TypeError("timeline 引数が必要です。Project.timeline を渡してください。")
        timeline.add_text(
            self,
            duration=time,
            effects=effects or [],
            start=start,
            layer=layer
        )
        return self


def text(content: str) -> TextClip:
    """
    テキストオーバーレイを作成する

    Args:
        content: 表示するテキスト

    Returns:
        TextClipオブジェクト
    """
    return TextClip(content)


def subtitle(content: str) -> TextClip:
    """
    字幕スタイルのテキストオーバーレイを作成する

    デフォルトで画面下部中央に配置され、視認性の高いスタイルが適用される。

    Args:
        content: 表示するテキスト

    Returns:
        TextClipオブジェクト（字幕スタイル適用済み）

    Example:
        subtitle("字幕テキスト").show(time=3, start=0)
    """
    return (
        text(content)
        .font(size=48, color="white")
        .border(width=2, color="black")
        .shadow(x=2, y=2, color="black@0.6")
        .pos(x=0.5, y=0.9, anchor="center")
    )
