"""
scriptvedit PySide6 GUI エディタ

クリップリスト、プロパティエディタ、プレビュー機能を持つ
動画編集GUIアプリケーション。
"""

import os
import sys
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, List, Any

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QSplitter, QListWidget, QListWidgetItem, QFormLayout, QLabel,
        QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QPushButton,
        QFileDialog, QMessageBox, QGroupBox, QScrollArea, QCheckBox,
        QStatusBar, QMenuBar, QMenu, QToolBar
    )
    from PySide6.QtCore import Qt, QTimer, Signal, QObject, QUrl
    from PySide6.QtGui import QAction, QKeySequence
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False

from .project import Project
from .timeline import VideoEntry, AudioEntry, TextEntry


class PreviewManager(QObject):
    """プレビュー生成を管理するクラス

    デバウンス機能と FFmpeg プロセスのキャンセル機能を持つ。
    """
    preview_ready = Signal(str)  # プレビューファイルパス
    preview_error = Signal(str)  # エラーメッセージ

    def __init__(self, parent=None):
        super().__init__(parent)
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._generate_preview)
        self._ffmpeg_process: Optional[subprocess.Popen] = None
        self._pending_timeline = None
        self._pending_center_time: float = 0.0
        self._temp_dir = tempfile.mkdtemp(prefix="scriptvedit_preview_")
        self._preview_counter = 0

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
            self._temp_dir,
            f"preview_{self._preview_counter}.mp4"
        )

        try:
            from .renderer import spawn_ffmpeg, compile_filtergraph

            # プレビュー範囲を計算
            pre = 2.0
            post = 2.0
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
                include_audio=True,
                out_width=640,
                out_height=360,
                out_fps=15,
                curve_samples=30
            )

            # 非同期で FFmpeg を起動
            self._ffmpeg_process = spawn_ffmpeg(
                compiled,
                output_path,
                verbose=False
            )

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
                    self.preview_ready.emit(output_path)
                else:
                    self._ffmpeg_process = None
                    self.preview_error.emit(f"FFmpeg がエラー終了: {ret}")

            QTimer.singleShot(100, check_process)

        except Exception as e:
            self.preview_error.emit(str(e))

    def cleanup(self):
        """一時ファイルをクリーンアップ"""
        self.cancel()
        try:
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass


class ClipListWidget(QListWidget):
    """クリップ一覧を表示するリストウィジェット"""

    clip_selected = Signal(object, str)  # (entry, type)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self._entries: List[tuple] = []  # (entry, type)

    def load_timeline(self, timeline):
        """タイムラインからクリップを読み込む"""
        self.clear()
        self._entries.clear()

        # 全エントリを収集してstart_timeでソート
        all_entries = []
        for entry in timeline.video_entries:
            all_entries.append((entry, "video"))
        for entry in timeline.audio_entries:
            all_entries.append((entry, "audio"))
        for entry in timeline.text_entries:
            all_entries.append((entry, "text"))

        all_entries.sort(key=lambda x: x[0].start_time)

        for entry, entry_type in all_entries:
            self._add_entry_item(entry, entry_type)

    def _add_entry_item(self, entry, entry_type: str):
        """エントリをリストに追加"""
        if entry_type == "video":
            label = f"[V] {Path(entry.media.path).name} @ {entry.start_time:.1f}s"
        elif entry_type == "audio":
            label = f"[A] {Path(entry.audio.path).name} @ {entry.start_time:.1f}s"
        elif entry_type == "text":
            content = entry.clip.content[:20]
            if len(entry.clip.content) > 20:
                content += "..."
            label = f"[T] \"{content}\" @ {entry.start_time:.1f}s"
        else:
            label = f"[?] Unknown @ {entry.start_time:.1f}s"

        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, len(self._entries))
        self.addItem(item)
        self._entries.append((entry, entry_type))

    def _on_selection_changed(self):
        """選択変更時の処理"""
        items = self.selectedItems()
        if items:
            idx = items[0].data(Qt.UserRole)
            if 0 <= idx < len(self._entries):
                entry, entry_type = self._entries[idx]
                self.clip_selected.emit(entry, entry_type)

    def get_selected_entry(self) -> Optional[tuple]:
        """選択中のエントリを取得"""
        items = self.selectedItems()
        if items:
            idx = items[0].data(Qt.UserRole)
            if 0 <= idx < len(self._entries):
                return self._entries[idx]
        return None


class PropertyEditorWidget(QScrollArea):
    """プロパティエディタウィジェット"""

    property_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._current_entry = None
        self._current_type = None
        self._widgets: dict = {}
        self._setup_ui()

    def _setup_ui(self):
        """UIを構築"""
        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setAlignment(Qt.AlignTop)

        # 空の状態
        self._empty_label = QLabel("クリップを選択してください")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(self._empty_label)

        self.setWidget(container)

    def load_entry(self, entry, entry_type: str):
        """エントリのプロパティを表示"""
        self._current_entry = entry
        self._current_type = entry_type
        self._clear_widgets()

        if entry_type == "video":
            self._build_video_editor(entry)
        elif entry_type == "audio":
            self._build_audio_editor(entry)
        elif entry_type == "text":
            self._build_text_editor(entry)

    def _clear_widgets(self):
        """ウィジェットをクリア"""
        self._empty_label.hide()
        for widget in self._widgets.values():
            widget.setParent(None)
            widget.deleteLater()
        self._widgets.clear()

    def _build_video_editor(self, entry: VideoEntry):
        """映像エントリのエディタを構築"""
        group = QGroupBox("映像クリップ")
        form = QFormLayout(group)

        # パス
        path_label = QLabel(str(entry.media.path))
        path_label.setWordWrap(True)
        form.addRow("ファイル:", path_label)

        # 開始時間
        start_spin = QDoubleSpinBox()
        start_spin.setRange(0, 9999)
        start_spin.setDecimals(2)
        start_spin.setValue(entry.start_time)
        start_spin.valueChanged.connect(
            lambda v: self._update_entry("start_time", v)
        )
        form.addRow("開始時間:", start_spin)
        self._widgets["start_time"] = start_spin

        # 再生時間
        duration_spin = QDoubleSpinBox()
        duration_spin.setRange(0.1, 9999)
        duration_spin.setDecimals(2)
        duration_spin.setValue(entry.duration)
        duration_spin.valueChanged.connect(
            lambda v: self._update_entry("duration", v)
        )
        form.addRow("再生時間:", duration_spin)
        self._widgets["duration"] = duration_spin

        # レイヤー
        layer_spin = QSpinBox()
        layer_spin.setRange(0, 99)
        layer_spin.setValue(entry.layer)
        layer_spin.valueChanged.connect(
            lambda v: self._update_entry("layer", v)
        )
        form.addRow("レイヤー:", layer_spin)
        self._widgets["layer"] = layer_spin

        # オフセット
        offset_spin = QDoubleSpinBox()
        offset_spin.setRange(0, 9999)
        offset_spin.setDecimals(2)
        offset_spin.setValue(entry.offset)
        offset_spin.valueChanged.connect(
            lambda v: self._update_entry("offset", v)
        )
        form.addRow("オフセット:", offset_spin)
        self._widgets["offset"] = offset_spin

        self._layout.addWidget(group)
        self._widgets["group"] = group

        # Transform グループ
        self._build_transform_editor(entry.media.transform)

    def _build_audio_editor(self, entry: AudioEntry):
        """音声エントリのエディタを構築"""
        group = QGroupBox("音声クリップ")
        form = QFormLayout(group)

        # パス
        path_label = QLabel(str(entry.audio.path))
        path_label.setWordWrap(True)
        form.addRow("ファイル:", path_label)

        # 開始時間
        start_spin = QDoubleSpinBox()
        start_spin.setRange(0, 9999)
        start_spin.setDecimals(2)
        start_spin.setValue(entry.start_time)
        start_spin.valueChanged.connect(
            lambda v: self._update_entry("start_time", v)
        )
        form.addRow("開始時間:", start_spin)
        self._widgets["start_time"] = start_spin

        # 再生時間
        duration_spin = QDoubleSpinBox()
        duration_spin.setRange(0.1, 9999)
        duration_spin.setDecimals(2)
        duration_spin.setValue(entry.duration)
        duration_spin.valueChanged.connect(
            lambda v: self._update_entry("duration", v)
        )
        form.addRow("再生時間:", duration_spin)
        self._widgets["duration"] = duration_spin

        # 音量
        volume_spin = QDoubleSpinBox()
        volume_spin.setRange(0, 10)
        volume_spin.setDecimals(2)
        volume_spin.setValue(entry.audio.volume)
        volume_spin.valueChanged.connect(
            lambda v: self._update_audio("volume", v)
        )
        form.addRow("音量:", volume_spin)
        self._widgets["volume"] = volume_spin

        # フェードイン
        fade_in_spin = QDoubleSpinBox()
        fade_in_spin.setRange(0, 60)
        fade_in_spin.setDecimals(2)
        fade_in_spin.setValue(entry.audio.fade_in)
        fade_in_spin.valueChanged.connect(
            lambda v: self._update_audio("fade_in", v)
        )
        form.addRow("フェードイン:", fade_in_spin)
        self._widgets["fade_in"] = fade_in_spin

        # フェードアウト
        fade_out_spin = QDoubleSpinBox()
        fade_out_spin.setRange(0, 60)
        fade_out_spin.setDecimals(2)
        fade_out_spin.setValue(entry.audio.fade_out)
        fade_out_spin.valueChanged.connect(
            lambda v: self._update_audio("fade_out", v)
        )
        form.addRow("フェードアウト:", fade_out_spin)
        self._widgets["fade_out"] = fade_out_spin

        self._layout.addWidget(group)
        self._widgets["group"] = group

    def _build_text_editor(self, entry: TextEntry):
        """テキストエントリのエディタを構築"""
        group = QGroupBox("テキストクリップ")
        form = QFormLayout(group)

        # コンテンツ
        content_edit = QLineEdit()
        content_edit.setText(entry.clip.content)
        content_edit.textChanged.connect(
            lambda v: self._update_text("content", v)
        )
        form.addRow("テキスト:", content_edit)
        self._widgets["content"] = content_edit

        # 開始時間
        start_spin = QDoubleSpinBox()
        start_spin.setRange(0, 9999)
        start_spin.setDecimals(2)
        start_spin.setValue(entry.start_time)
        start_spin.valueChanged.connect(
            lambda v: self._update_entry("start_time", v)
        )
        form.addRow("開始時間:", start_spin)
        self._widgets["start_time"] = start_spin

        # 再生時間
        duration_spin = QDoubleSpinBox()
        duration_spin.setRange(0.1, 9999)
        duration_spin.setDecimals(2)
        duration_spin.setValue(entry.duration)
        duration_spin.valueChanged.connect(
            lambda v: self._update_entry("duration", v)
        )
        form.addRow("再生時間:", duration_spin)
        self._widgets["duration"] = duration_spin

        # レイヤー
        layer_spin = QSpinBox()
        layer_spin.setRange(0, 99)
        layer_spin.setValue(entry.layer)
        layer_spin.valueChanged.connect(
            lambda v: self._update_entry("layer", v)
        )
        form.addRow("レイヤー:", layer_spin)
        self._widgets["layer"] = layer_spin

        # フォントサイズ
        fontsize_spin = QSpinBox()
        fontsize_spin.setRange(8, 256)
        fontsize_spin.setValue(entry.clip.style.fontsize)
        fontsize_spin.valueChanged.connect(
            lambda v: self._update_style("fontsize", v)
        )
        form.addRow("フォントサイズ:", fontsize_spin)
        self._widgets["fontsize"] = fontsize_spin

        # フォント色
        fontcolor_edit = QLineEdit()
        fontcolor_edit.setText(entry.clip.style.fontcolor)
        fontcolor_edit.textChanged.connect(
            lambda v: self._update_style("fontcolor", v)
        )
        form.addRow("フォント色:", fontcolor_edit)
        self._widgets["fontcolor"] = fontcolor_edit

        self._layout.addWidget(group)
        self._widgets["group"] = group

        # Transform グループ
        self._build_transform_editor(entry.clip.transform)

    def _build_transform_editor(self, transform):
        """Transform のエディタを構築"""
        group = QGroupBox("トランスフォーム")
        form = QFormLayout(group)

        # 位置 X
        pos_x = transform.pos_x if not callable(transform.pos_x) else 0.5
        pos_x_spin = QDoubleSpinBox()
        pos_x_spin.setRange(0, 1)
        pos_x_spin.setDecimals(3)
        pos_x_spin.setSingleStep(0.01)
        pos_x_spin.setValue(float(pos_x) if pos_x is not None else 0.5)
        pos_x_spin.valueChanged.connect(
            lambda v: self._update_transform("pos_x", v)
        )
        form.addRow("位置 X:", pos_x_spin)
        self._widgets["pos_x"] = pos_x_spin

        # 位置 Y
        pos_y = transform.pos_y if not callable(transform.pos_y) else 0.5
        pos_y_spin = QDoubleSpinBox()
        pos_y_spin.setRange(0, 1)
        pos_y_spin.setDecimals(3)
        pos_y_spin.setSingleStep(0.01)
        pos_y_spin.setValue(float(pos_y) if pos_y is not None else 0.5)
        pos_y_spin.valueChanged.connect(
            lambda v: self._update_transform("pos_y", v)
        )
        form.addRow("位置 Y:", pos_y_spin)
        self._widgets["pos_y"] = pos_y_spin

        # 透明度
        alpha = transform.alpha if not callable(transform.alpha) else 1.0
        alpha_spin = QDoubleSpinBox()
        alpha_spin.setRange(0, 1)
        alpha_spin.setDecimals(2)
        alpha_spin.setSingleStep(0.1)
        alpha_spin.setValue(float(alpha) if alpha is not None else 1.0)
        alpha_spin.valueChanged.connect(
            lambda v: self._update_transform("alpha", v)
        )
        form.addRow("透明度:", alpha_spin)
        self._widgets["alpha"] = alpha_spin

        # 回転
        rotation = transform.rotation if not callable(transform.rotation) else 0.0
        rotation_spin = QDoubleSpinBox()
        rotation_spin.setRange(-360, 360)
        rotation_spin.setDecimals(1)
        rotation_spin.setValue(float(rotation) if rotation is not None else 0.0)
        rotation_spin.valueChanged.connect(
            lambda v: self._update_transform("rotation", v)
        )
        form.addRow("回転:", rotation_spin)
        self._widgets["rotation"] = rotation_spin

        self._layout.addWidget(group)
        self._widgets["transform_group"] = group

    def _update_entry(self, attr: str, value):
        """エントリ属性を更新"""
        if self._current_entry:
            setattr(self._current_entry, attr, value)
            self.property_changed.emit()

    def _update_audio(self, attr: str, value):
        """Audio 属性を更新"""
        if self._current_entry and self._current_type == "audio":
            setattr(self._current_entry.audio, attr, value)
            self.property_changed.emit()

    def _update_text(self, attr: str, value):
        """TextClip 属性を更新"""
        if self._current_entry and self._current_type == "text":
            setattr(self._current_entry.clip, attr, value)
            self.property_changed.emit()

    def _update_style(self, attr: str, value):
        """TextStyle 属性を更新"""
        if self._current_entry and self._current_type == "text":
            setattr(self._current_entry.clip.style, attr, value)
            self.property_changed.emit()

    def _update_transform(self, attr: str, value):
        """Transform 属性を更新"""
        if self._current_entry:
            if self._current_type == "video":
                setattr(self._current_entry.media.transform, attr, value)
            elif self._current_type == "text":
                setattr(self._current_entry.clip.transform, attr, value)
            self.property_changed.emit()


class MainWindow(QMainWindow):
    """メインウィンドウ"""

    def __init__(self, project_path: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("scriptvedit Editor")
        self.resize(1200, 800)

        self._project: Optional[Project] = None
        self._project_path: Optional[str] = None
        self._modified = False

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
        main_layout = QHBoxLayout(central)

        # 左ペイン: クリップリスト
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("クリップ一覧"))
        self._clip_list = ClipListWidget()
        left_layout.addWidget(self._clip_list)

        # ファイル追加ボタン
        add_btn_layout = QHBoxLayout()
        self._add_video_btn = QPushButton("映像追加")
        self._add_audio_btn = QPushButton("音声追加")
        self._add_text_btn = QPushButton("テキスト追加")
        add_btn_layout.addWidget(self._add_video_btn)
        add_btn_layout.addWidget(self._add_audio_btn)
        add_btn_layout.addWidget(self._add_text_btn)
        left_layout.addLayout(add_btn_layout)

        # 中央ペイン: プレビュー
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.addWidget(QLabel("プレビュー"))

        self._video_widget = QVideoWidget()
        self._video_widget.setMinimumSize(640, 360)
        center_layout.addWidget(self._video_widget)

        self._media_player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._media_player.setAudioOutput(self._audio_output)
        self._media_player.setVideoOutput(self._video_widget)

        # プレビューコントロール
        preview_ctrl_layout = QHBoxLayout()
        self._preview_btn = QPushButton("プレビュー更新")
        self._play_btn = QPushButton("再生")
        self._stop_btn = QPushButton("停止")
        preview_ctrl_layout.addWidget(self._preview_btn)
        preview_ctrl_layout.addWidget(self._play_btn)
        preview_ctrl_layout.addWidget(self._stop_btn)
        center_layout.addLayout(preview_ctrl_layout)

        # 右ペイン: プロパティエディタ
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel("プロパティ"))
        self._property_editor = PropertyEditorWidget()
        right_layout.addWidget(self._property_editor)

        # スプリッター
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(center_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([250, 650, 300])
        main_layout.addWidget(splitter)

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

        # 編集メニュー
        edit_menu = menubar.addMenu("編集(&E)")

        delete_action = QAction("削除(&D)", self)
        delete_action.setShortcut(QKeySequence.Delete)
        delete_action.triggered.connect(self._delete_selected)
        edit_menu.addAction(delete_action)

    def _setup_connections(self):
        """シグナル/スロットを接続"""
        self._clip_list.clip_selected.connect(self._on_clip_selected)
        self._property_editor.property_changed.connect(self._on_property_changed)

        self._add_video_btn.clicked.connect(self._add_video)
        self._add_audio_btn.clicked.connect(self._add_audio)
        self._add_text_btn.clicked.connect(self._add_text)

        self._preview_btn.clicked.connect(self._request_preview)
        self._play_btn.clicked.connect(self._play_preview)
        self._stop_btn.clicked.connect(self._stop_preview)

        self._preview_manager.preview_ready.connect(self._on_preview_ready)
        self._preview_manager.preview_error.connect(self._on_preview_error)

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
        self._update_ui()
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
            self._update_ui()
            self._update_title()
            self._status_bar.showMessage(f"プロジェクトを読み込みました: {path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"読み込みに失敗: {e}")

    def _save_project(self):
        """プロジェクトを保存"""
        if self._project_path:
            try:
                self._project.save(self._project_path)
                self._modified = False
                self._update_title()
                self._status_bar.showMessage("保存しました", 3000)
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"保存に失敗: {e}")
        else:
            self._save_project_as()

    def _save_project_as(self):
        """名前を付けて保存"""
        path, _ = QFileDialog.getSaveFileName(
            self, "プロジェクトを保存", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if path:
            if not path.endswith(".json"):
                path += ".json"
            try:
                self._project.save(path)
                self._project_path = path
                self._modified = False
                self._update_title()
                self._status_bar.showMessage(f"保存しました: {path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"保存に失敗: {e}")

    def _render_project(self):
        """プロジェクトをレンダリング"""
        path, _ = QFileDialog.getSaveFileName(
            self, "出力ファイル", "",
            "MP4 Files (*.mp4);;All Files (*)"
        )
        if path:
            if not path.endswith(".mp4"):
                path += ".mp4"
            try:
                from .renderer import render
                self._status_bar.showMessage("レンダリング中...")
                QApplication.processEvents()
                render(self._project.timeline, path, verbose=True)
                self._status_bar.showMessage(f"レンダリング完了: {path}", 5000)
                QMessageBox.information(self, "完了", f"レンダリングが完了しました:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"レンダリングに失敗: {e}")

    def _update_ui(self):
        """UIを更新"""
        if self._project:
            self._clip_list.load_timeline(self._project.timeline)

    def _update_title(self):
        """ウィンドウタイトルを更新"""
        title = "scriptvedit Editor"
        if self._project_path:
            title += f" - {Path(self._project_path).name}"
        if self._modified:
            title += " *"
        self.setWindowTitle(title)

    def _on_clip_selected(self, entry, entry_type: str):
        """クリップ選択時"""
        self._property_editor.load_entry(entry, entry_type)

    def _on_property_changed(self):
        """プロパティ変更時"""
        self._modified = True
        self._update_title()
        self._update_ui()

    def _add_video(self):
        """映像を追加"""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "映像ファイルを選択", "",
            "Video Files (*.mp4 *.mov *.avi *.mkv);;Image Files (*.jpg *.png *.gif);;All Files (*)"
        )
        for path in paths:
            try:
                media = self._project.clip(path)
                media.show(
                    self._project.timeline,
                    time=5.0,
                    start=self._project.total_duration
                )
                self._modified = True
            except Exception as e:
                QMessageBox.warning(self, "警告", f"追加できませんでした: {path}\n{e}")
        self._update_ui()
        self._update_title()

    def _add_audio(self):
        """音声を追加"""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "音声ファイルを選択", "",
            "Audio Files (*.mp3 *.wav *.aac *.m4a);;All Files (*)"
        )
        for path in paths:
            try:
                audio_obj = self._project.audio(path)
                audio_obj.play(
                    self._project.timeline,
                    start=0.0
                )
                self._modified = True
            except Exception as e:
                QMessageBox.warning(self, "警告", f"追加できませんでした: {path}\n{e}")
        self._update_ui()
        self._update_title()

    def _add_text(self):
        """テキストを追加"""
        text_clip = self._project.text("テキスト")
        text_clip.show(
            self._project.timeline,
            time=3.0,
            start=self._project.total_duration
        )
        self._modified = True
        self._update_ui()
        self._update_title()

    def _delete_selected(self):
        """選択中のクリップを削除"""
        entry_data = self._clip_list.get_selected_entry()
        if not entry_data:
            return

        entry, entry_type = entry_data
        if entry_type == "video":
            if entry in self._project.timeline.video_entries:
                self._project.timeline.video_entries.remove(entry)
        elif entry_type == "audio":
            if entry in self._project.timeline.audio_entries:
                self._project.timeline.audio_entries.remove(entry)
        elif entry_type == "text":
            if entry in self._project.timeline.text_entries:
                self._project.timeline.text_entries.remove(entry)

        self._modified = True
        self._update_ui()
        self._update_title()

    def _request_preview(self):
        """プレビューをリクエスト"""
        if self._project and self._project.total_duration > 0:
            center = self._project.total_duration / 2
            self._preview_manager.request_preview(
                self._project.timeline,
                center
            )
            self._status_bar.showMessage("プレビュー生成中...")

    def _on_preview_ready(self, path: str):
        """プレビュー完了時"""
        self._status_bar.showMessage("プレビュー完了", 3000)
        self._media_player.setSource(QUrl.fromLocalFile(path))

    def _on_preview_error(self, error: str):
        """プレビューエラー時"""
        self._status_bar.showMessage(f"プレビューエラー: {error}", 5000)

    def _play_preview(self):
        """プレビュー再生"""
        self._media_player.play()

    def _stop_preview(self):
        """プレビュー停止"""
        self._media_player.stop()

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


if __name__ == "__main__":
    main()
