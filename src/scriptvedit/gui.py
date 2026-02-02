"""
scriptvedit PySide6 GUI エディタ

ミニマルGUI:
  - 再生ウィンドウ
  - シークバー（プロジェクト全体の時刻）
  - その時刻周辺の短いプレビューを高速生成して再生
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QFileDialog, QMessageBox, QStatusBar,
        QSlider, QProgressBar
    )
    from PySide6.QtCore import Qt, QTimer, Signal, QObject, QUrl
    from PySide6.QtGui import QAction, QKeySequence
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False

from .project import Project


# ------------------------------------------------------------
# PreviewManager: 高速プレビュー（短尺/低解像度/低fps/音声なし/ultrafast）
# ------------------------------------------------------------

class PreviewManager(QObject):
    """プレビュー生成を管理するクラス

    デバウンス機能と FFmpeg プロセスのキャンセル機能を持つ。
    """
    preview_ready = Signal(str, float, float)  # (path, window_start, window_duration)
    preview_error = Signal(str)  # エラーメッセージ

    def __init__(self, parent=None):
        super().__init__(parent)
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._generate_preview)
        self._ffmpeg_process: Optional[subprocess.Popen] = None
        self._active_filter_script_path: Optional[str] = None
        self._pending_timeline = None
        self._pending_center_time: float = 0.0
        self._preview_counter = 0

        # プレビュー保存先: tests/preview ディレクトリ
        self._preview_dir = self._find_preview_dir()
        os.makedirs(self._preview_dir, exist_ok=True)

        # プレビュー品質（高速化優先のデフォルト）
        self.preview_pre = 0.8
        self.preview_post = 0.8
        self.preview_width = 480
        self.preview_height = 270
        self.preview_fps = 10
        self.preview_curve_samples = 10

    def _find_preview_dir(self) -> str:
        """tests/preview ディレクトリのパスを取得"""
        # gui.py は src/scriptvedit/ にあるので、2階層上がってから tests/preview
        this_file = Path(__file__).resolve()
        project_root = this_file.parent.parent.parent  # src/scriptvedit -> src -> project_root
        preview_dir = project_root / "tests" / "preview"
        return str(preview_dir)

    def request_preview(
        self,
        timeline,
        center_time: float,
        debounce_ms: int = 300
    ):
        """プレビュー生成をリクエスト（デバウンス付き）

        Args:
            timeline: プレビューするタイムライン
            center_time: プレビュー中心時刻（秒）
            debounce_ms: デバウンス時間（ミリ秒）
        """
        self._pending_timeline = timeline
        self._pending_center_time = center_time
        self._debounce_timer.stop()
        self._debounce_timer.start(debounce_ms)

    def cancel(self):
        """実行中のプレビュー生成をキャンセル"""
        self._debounce_timer.stop()
        if self._ffmpeg_process is not None:
            try:
                self._ffmpeg_process.terminate()
                self._ffmpeg_process.wait(timeout=2)
            except Exception:
                try:
                    self._ffmpeg_process.kill()
                except Exception:
                    pass
            self._ffmpeg_process = None
        # filter_complex_script の一時ファイルも掃除
        if self._active_filter_script_path:
            try:
                os.remove(self._active_filter_script_path)
            except Exception:
                pass
            self._active_filter_script_path = None

    def _generate_preview(self):
        """プレビューを生成"""
        if self._pending_timeline is None:
            return

        self.cancel()  # 既存のプロセスをキャンセル

        timeline = self._pending_timeline
        center_time = self._pending_center_time
        self._pending_timeline = None

        self._preview_counter += 1
        output_path = os.path.join(
            self._preview_dir,
            f"preview_{self._preview_counter}.mp4"
        )

        try:
            from .renderer import spawn_ffmpeg, compile_filtergraph

            # プレビュー範囲を計算
            pre = float(self.preview_pre)
            post = float(self.preview_post)
            total_duration = timeline.total_duration
            start = max(0, center_time - pre)
            end = min(total_duration, center_time + post)
            duration = end - start

            if duration <= 0:
                self.preview_error.emit("プレビュー範囲が無効です")
                return

            # 低解像度・低FPSでコンパイル
            compiled = compile_filtergraph(
                timeline,
                start=start,
                duration=duration,
                include_audio=False,  # 音声なしで高速化
                out_width=int(self.preview_width),
                out_height=int(self.preview_height),
                out_fps=int(self.preview_fps),
                curve_samples=int(self.preview_curve_samples)
            )

            # 非同期で FFmpeg を起動（高速設定）
            self._ffmpeg_process = spawn_ffmpeg(
                compiled,
                output_path,
                verbose=False,
                video_preset="ultrafast",
                tune="zerolatency",
                crf=35
            )
            # renderer.spawn_ffmpeg が持つ一時フィルタファイルを覚えておく
            self._active_filter_script_path = getattr(self._ffmpeg_process, "_filter_script_path", None)

            # プロセス完了を監視するタイマー
            def check_process():
                if self._ffmpeg_process is None:
                    return
                ret = self._ffmpeg_process.poll()
                if ret is None:
                    # まだ実行中
                    QTimer.singleShot(100, check_process)
                elif ret == 0:
                    self._ffmpeg_process = None
                    # 一時フィルタファイル掃除
                    if self._active_filter_script_path:
                        try:
                            os.remove(self._active_filter_script_path)
                        except Exception:
                            pass
                        self._active_filter_script_path = None
                    self.preview_ready.emit(output_path, float(start), float(duration))
                else:
                    self._ffmpeg_process = None
                    if self._active_filter_script_path:
                        try:
                            os.remove(self._active_filter_script_path)
                        except Exception:
                            pass
                        self._active_filter_script_path = None
                    self.preview_error.emit(f"FFmpeg がエラー終了: {ret}")

            QTimer.singleShot(100, check_process)

        except Exception as e:
            self.preview_error.emit(str(e))

    def cleanup(self):
        """実行中のプロセスをキャンセル（プレビューファイルは保持）"""
        self.cancel()


class MainWindow(QMainWindow):
    """メインウィンドウ"""

    def __init__(self, project_path: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("scriptvedit Preview")
        self.resize(980, 720)

        self._project: Optional[Project] = None
        self._project_path: Optional[str] = None
        self._modified = False

        # プレビュー窓の範囲（preview_ready で更新）
        self._window_start: float = 0.0
        self._window_duration: float = 0.0
        self._seeking: bool = False  # スライダ更新のループ防止

        self._setup_ui()
        self._setup_menu()
        self._setup_connections()

        if project_path:
            self._load_project(project_path)
        else:
            self._new_project()

    def _setup_ui(self):
        """UIを構築"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self._video_widget = QVideoWidget()
        self._video_widget.setMinimumSize(640, 360)
        layout.addWidget(self._video_widget, stretch=1)

        self._media_player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._media_player.setAudioOutput(self._audio_output)
        self._media_player.setVideoOutput(self._video_widget)

        # シークバー（プロジェクト全体の時刻）
        self._seek = QSlider(Qt.Horizontal)
        self._seek.setRange(0, 0)
        self._seek.setSingleStep(50)   # 50ms
        self._seek.setPageStep(200)    # 200ms
        layout.addWidget(self._seek)

        # 操作ボタン
        ctrl = QHBoxLayout()
        self._preview_btn = QPushButton("更新")
        self._play_pause_btn = QPushButton("再生/一時停止")
        self._stop_btn = QPushButton("停止")
        ctrl.addWidget(self._preview_btn)
        ctrl.addWidget(self._play_pause_btn)
        ctrl.addWidget(self._stop_btn)
        layout.addLayout(ctrl)

        # ステータスバー
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        # プレビューマネージャー
        self._preview_manager = PreviewManager(self)

    def _setup_menu(self):
        """メニューを構築"""
        menubar = self.menuBar()

        # ファイルメニュー
        file_menu = menubar.addMenu("ファイル(&F)")

        new_action = QAction("新規(&N)", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)

        open_action = QAction("開く(&O)", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)

        save_action = QAction("保存(&S)", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)

        save_as_action = QAction("名前を付けて保存(&A)", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self._save_project_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        render_action = QAction("レンダリング(&R)", self)
        render_action.triggered.connect(self._render_project)
        file_menu.addAction(render_action)

        file_menu.addSeparator()

        quit_action = QAction("終了(&Q)", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _setup_connections(self):
        """シグナル/スロットを接続"""
        self._preview_btn.clicked.connect(self._request_preview)
        self._play_pause_btn.clicked.connect(self._play_pause)
        self._stop_btn.clicked.connect(self._stop_preview)

        self._preview_manager.preview_ready.connect(self._on_preview_ready)
        self._preview_manager.preview_error.connect(self._on_preview_error)

        self._seek.sliderPressed.connect(self._on_seek_pressed)
        self._seek.sliderReleased.connect(self._on_seek_released)
        self._seek.valueChanged.connect(self._on_seek_value_changed)
        self._media_player.positionChanged.connect(self._on_player_position_changed)

    def _new_project(self):
        """新規プロジェクト"""
        if self._modified:
            ret = QMessageBox.question(
                self, "確認",
                "変更を保存しますか？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if ret == QMessageBox.Save:
                self._save_project()
            elif ret == QMessageBox.Cancel:
                return

        self._project = Project()
        self._project.configure(width=1920, height=1080, fps=30)
        self._project_path = None
        self._modified = False
        self._update_seek_range()
        self._update_title()

    def _open_project(self):
        """プロジェクトを開く"""
        if self._modified:
            ret = QMessageBox.question(
                self, "確認",
                "変更を保存しますか？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if ret == QMessageBox.Save:
                self._save_project()
            elif ret == QMessageBox.Cancel:
                return

        path, _ = QFileDialog.getOpenFileName(
            self, "プロジェクトを開く", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if path:
            self._load_project(path)

    def _load_project(self, path: str):
        """プロジェクトを読み込む"""
        try:
            self._project = Project.load(path)
            self._project_path = path
            self._modified = False
            self._update_seek_range()
            self._update_title()
            self._status_bar.showMessage(f"プロジェクトを読み込みました: {path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"プロジェクトの読み込みに失敗: {e}")

    def _save_project(self):
        """プロジェクトを保存"""
        if not self._project:
            return

        if not self._project_path:
            self._save_project_as()
            return

        try:
            self._project.save(self._project_path)
            self._modified = False
            self._update_title()
            self._status_bar.showMessage(f"保存しました: {self._project_path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"保存に失敗: {e}")

    def _save_project_as(self):
        """名前を付けて保存"""
        if not self._project:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "名前を付けて保存", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if path:
            self._project_path = path
            self._save_project()

    def _render_project(self):
        """プロジェクトをレンダリング"""
        if not self._project:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "レンダリング出力", "",
            "MP4 Files (*.mp4);;All Files (*)"
        )
        if path:
            self._status_bar.showMessage("レンダリング中...")
            try:
                from .renderer import render
                render(self._project.timeline, path, verbose=False)
                self._status_bar.showMessage(f"レンダリング完了: {path}", 5000)
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"レンダリングに失敗: {e}")

    def _update_seek_range(self):
        """シークバーの範囲をプロジェクト尺に合わせる（ms）"""
        if not self._project:
            self._seek.setRange(0, 0)
            return
        total_ms = max(0, int(self._project.total_duration * 1000))
        self._seek.setRange(0, total_ms)

    def _update_title(self):
        """ウィンドウタイトルを更新"""
        title = "scriptvedit Preview"
        if self._project_path:
            title += f" - {Path(self._project_path).name}"
        if self._modified:
            title += " *"
        self.setWindowTitle(title)

    def _request_preview(self):
        """プレビューをリクエスト"""
        if not self._project or self._project.total_duration <= 0:
            return
        center = self._seek.value() / 1000.0
        self._preview_manager.request_preview(self._project.timeline, center)
        self._status_bar.showMessage("プレビュー生成中...")

    def _on_preview_ready(self, path: str, window_start: float, window_duration: float):
        """プレビュー完了時"""
        self._status_bar.showMessage("プレビュー完了", 3000)
        self._window_start = float(window_start)
        self._window_duration = float(window_duration)
        self._media_player.setSource(QUrl.fromLocalFile(path))
        self._media_player.setPosition(0)

    def _on_preview_error(self, error: str):
        """プレビューエラー時"""
        self._status_bar.showMessage(f"プレビューエラー: {error}", 5000)

    def _play_pause(self):
        """再生/一時停止"""
        if self._media_player.playbackState() == QMediaPlayer.PlayingState:
            self._media_player.pause()
        else:
            self._media_player.play()

    def _stop_preview(self):
        """プレビュー停止"""
        self._media_player.stop()

    # ---- seek bar (global timeline) ----
    def _on_seek_pressed(self):
        self._seeking = True

    def _on_seek_released(self):
        # スライダを離したら、その時刻中心でプレビューを作り直す
        self._seeking = False
        self._request_preview()

    def _on_seek_value_changed(self, v: int):
        # ドラッグ中はステータス表示だけ
        if not self._project:
            return
        t = v / 1000.0
        self._status_bar.showMessage(f"t = {t:.2f}s", 200)

    def _on_player_position_changed(self, pos_ms: int):
        # 再生中の位置を「プロジェクト全体の時刻」に反映
        if self._seeking:
            return
        if self._window_duration <= 0:
            return
        global_ms = int((self._window_start * 1000.0) + pos_ms)
        if global_ms < self._seek.minimum():
            global_ms = self._seek.minimum()
        if global_ms > self._seek.maximum():
            global_ms = self._seek.maximum()
        self._seek.blockSignals(True)
        self._seek.setValue(global_ms)
        self._seek.blockSignals(False)

    def closeEvent(self, event):
        """終了時"""
        if self._modified:
            ret = QMessageBox.question(
                self, "確認",
                "変更を保存しますか？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if ret == QMessageBox.Save:
                self._save_project()
                event.accept()
            elif ret == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
                return

        self._preview_manager.cleanup()
        event.accept()


def main(project_path: Optional[str] = None):
    """GUIアプリケーションを起動"""
    if not PYSIDE6_AVAILABLE:
        raise ImportError("PySide6 がインストールされていません")

    app = QApplication(sys.argv)
    app.setApplicationName("scriptvedit")

    window = MainWindow(project_path)
    window.show()

    sys.exit(app.exec())
