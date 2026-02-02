"""
プロジェクト管理モジュール

GUIで複数プロジェクトを扱いやすくするため、
グローバル状態を廃止し Project クラスにカプセル化する。
"""

from typing import Optional, List, Dict, Any

from .timeline import Timeline
from .media import Media, Audio
from .text import TextClip, TextStyle, subtitle as _subtitle_preset


class Project:
    """
    動画編集プロジェクト

    タイムラインと設定を保持し、メディア/テキスト/音声の追加を管理する。
    グローバル状態を持たないため、複数プロジェクトの同時操作や
    並列プレビュー生成が容易になる。

    Example:
        p = Project()
        p.configure(width=1920, height=1080, fps=30)

        bg = p.clip("background.jpg").resize(sx=1.0)
        bg.show(p.timeline, time=5, start=0)

        p.text("Hello").pos(x=0.5, y=0.5).show(p.timeline, time=3, start=1)

        from scriptvedit.renderer import render
        render(p.timeline, "output.mp4")
    """

    def __init__(self):
        """プロジェクトを初期化"""
        self.timeline = Timeline()

    def configure(
        self,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
        background_color: Optional[str] = None,
        curve_samples: Optional[int] = None,
        strict: Optional[bool] = None
    ) -> "Project":
        """
        タイムラインの設定を変更

        Args:
            width: 出力幅（ピクセル）
            height: 出力高さ（ピクセル）
            fps: フレームレート
            background_color: 背景色
            curve_samples: callable エフェクトのサンプリング数
            strict: True の場合、素材尺超過でエラー（デフォルトは警告のみ）

        Returns:
            self（メソッドチェーン用）
        """
        self.timeline.configure(
            width=width,
            height=height,
            fps=fps,
            background_color=background_color,
            curve_samples=curve_samples,
            strict=strict
        )
        return self

    def clear(self) -> "Project":
        """
        タイムラインをクリア

        Returns:
            self（メソッドチェーン用）
        """
        self.timeline.clear()
        return self

    def clip(self, path: str) -> Media:
        """
        画像/動画ファイルを開く

        Args:
            path: ファイルパス

        Returns:
            Mediaオブジェクト
        """
        return Media(path)

    def audio(self, path: str) -> Audio:
        """
        音声ファイルを開く

        Args:
            path: ファイルパス

        Returns:
            Audioオブジェクト
        """
        return Audio(path)

    def text(self, content: str) -> TextClip:
        """
        テキストオーバーレイを作成

        Args:
            content: 表示するテキスト

        Returns:
            TextClipオブジェクト
        """
        return TextClip(content)

    def subtitle(self, content: str) -> TextClip:
        """
        字幕スタイルのテキストオーバーレイを作成

        デフォルトで画面下部中央に配置され、視認性の高いスタイルが適用される。

        Args:
            content: 表示するテキスト

        Returns:
            TextClipオブジェクト（字幕スタイル適用済み）
        """
        return _subtitle_preset(content)

    @property
    def total_duration(self) -> float:
        """総再生時間（秒）"""
        return self.timeline.total_duration

    def to_dict(self) -> Dict[str, Any]:
        """
        プロジェクトを辞書に変換（シリアライズ用）

        Returns:
            dict: プロジェクトの辞書表現
        """
        from .serde import project_to_dict
        return project_to_dict(self.timeline)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        """
        辞書からプロジェクトを復元

        Args:
            data: プロジェクトの辞書表現

        Returns:
            Project: 復元されたプロジェクト
        """
        from .serde import project_from_dict
        project = cls()
        project.timeline = project_from_dict(data)
        return project

    def save(self, path: str) -> None:
        """
        プロジェクトをJSONファイルに保存

        Args:
            path: 保存先ファイルパス
        """
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "Project":
        """
        JSONファイルからプロジェクトを読み込む

        Args:
            path: ファイルパス

        Returns:
            Project: 読み込まれたプロジェクト
        """
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
