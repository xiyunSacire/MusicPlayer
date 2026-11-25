# -*- coding: utf-8 -*-
"""
LRC 歌词制作与微调编辑器

提供：
1. 导入纯文本（TXT）或直接粘贴，快速生成未打点歌词草稿
2. 导入现有 LRC 文件进行可视化微调与翻译增补
3. 独立音频播放控制栏（播放/暂停、快进/快退3秒、倍速播放、进度拖动）
4. 实时打点标记：播放时按快捷键（F5 / Ctrl+Space / 空格模式）或点击打点按钮，
   自动将当前时间戳赋予选中行并平滑跳至下一行
5. 每一行支持原文歌词编辑、独立翻译歌词输入
6. 精细时间微调：单行 ±0.1s / ±0.5s 微调、单行试听、全局时间平移
7. 增删行、调整顺序
8. 保存输出标准 LRC 文件至音频所在目录和项目歌词库
"""

import os
import re
import time
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QFileDialog, QMessageBox, QSlider, QComboBox,
    QPlainTextEdit, QDialogButtonBox, QShortcut, QFrame
)
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QTime, QTimer
from PyQt5.QtGui import QFont, QColor, QKeySequence
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

from ..audio_utils import get_audio_metadata
from .. import lyrics_service
from .ui_controls import ClickableSlider


def ms_to_lrc_str(ms: int) -> str:
    """毫秒转换为 [mm:ss.xx] 格式，未设置时返回 [--:--.--]"""
    if ms is None or ms < 0:
        return "[--:--.--]"
    total_seconds = ms / 1000.0
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    hundredths = int((total_seconds - int(total_seconds)) * 100)
    return f"[{minutes:02d}:{seconds:02d}.{hundredths:02d}]"


def parse_lrc_str_to_ms(time_str: str) -> int:
    """解析 [mm:ss.xx] 或 [mm:ss.xxx] 为毫秒，无效时返回 -1"""
    if not time_str:
        return -1
    m = re.search(r'(\d{2}):(\d{2})\.(\d{2,3})', time_str.strip())
    if not m:
        return -1
    minutes = int(m.group(1))
    seconds = int(m.group(2))
    sub = m.group(3)
    if len(sub) == 2:
        ms = int(sub) * 10
    else:
        ms = int(sub.ljust(3, '0')[:3])
    return minutes * 60000 + seconds * 1000 + ms


class TextPasteDialog(QDialog):
    """纯文本快速粘贴弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("粘贴纯文本歌词")
        self.resize(560, 420)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            QLabel {
                color: #334155;
                font-size: 14px;
            }
            QPlainTextEdit {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
                background-color: #f8fafc;
                color: #0f172a;
            }
            QPlainTextEdit:focus {
                border-color: #2563eb;
                background-color: #ffffff;
            }
            QPushButton {
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 14px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        tip_label = QLabel("请在下方粘贴纯文本歌词（每行一句，将自动过滤空行并生成草稿）：")
        layout.addWidget(tip_label)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("在此粘贴歌词内容...")
        layout.addWidget(self.editor)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("确认导入")
        btn_box.button(QDialogButtonBox.Ok).setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #1d4ed8;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        btn_box.button(QDialogButtonBox.Cancel).setText("取消")
        btn_box.button(QDialogButtonBox.Cancel).setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                border: 1px solid #cbd5e1;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_text(self) -> str:
        return self.editor.toPlainText().strip()


class LyricsEditorDialog(QDialog):
    """LRC 歌词制作与微调编辑器主窗口"""

    # 信号：歌词已成功保存 (lrc_content, title, artist, audio_file_path)
    lyrics_saved = pyqtSignal(str, str, str, str)

    # 跳转判定参数（与 MusicPlayer 保持同一套语义，仅作用于编辑器自带的播放器）
    SEEK_CONFIRM_TOLERANCE_MS = 1500   # 驱动回吐位置进入目标±该值即判定跳转完成
    SEEK_BACKWARD_JUMP_MS = 500        # 正常播放中位置倒退超过该值，视为无来源的异常回退
    SEEK_LOOP_END_MARGIN_MS = 3000     # 上一位置距总时长小于该值时，允许把倒退解释为循环重播
    SEEK_CONFIRM_TIMEOUT_MS = 3000     # 兜底：驱动始终不回吐目标时放弃等待

    def __init__(self, parent=None, audio_file: str = "", title: str = "", artist: str = "", initial_lyrics: str = ""):
        super().__init__(parent)
        self.audio_file = audio_file
        self.song_title = title
        self.song_artist = artist
        self.initial_lyrics = initial_lyrics
        self._cached_duration = 0
        # 跳转状态：None 为正常态，非 None 表示已登记跳转意图、等待驱动确认
        self._seeking_target_ms = None
        self._seeking_start_time = 0.0
        self._last_pos_ms = 0            # 最近一次被确认并显示的位置
        self._pending_seek_ms = None     # 排队中的最新试听/跳转目标（串行化用）

        # 顶部进度条的渲染时钟：后端位置只有约 1 秒粒度，这里按 50ms 插值刷新
        self._anchor_ms = 0
        self._anchor_time = time.time()
        self._render_ms = 0
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(50)
        self._render_timer.timeout.connect(self._on_render_tick_ui)
        self._render_timer.start()

        # 跳转队列兜底：确认信号迟迟不来时，超时后把排队的那一条放行
        self._seek_queue_timer = QTimer(self)
        self._seek_queue_timer.setInterval(100)
        self._seek_queue_timer.timeout.connect(self._drain_seek_queue)
        self._seek_queue_timer.start()

        # 内部专用媒体播放器
        self.player = QMediaPlayer(self)
        self.player.positionChanged.connect(self._on_player_position_changed)
        self.player.durationChanged.connect(self._on_player_duration_changed)
        self.player.stateChanged.connect(self._on_player_state_changed)

        self.setWindowTitle("LRC 歌词制作与微调工具")
        self.resize(1160, 750)
        self.setMinimumSize(980, 620)

        self._setup_ui()
        self._setup_shortcuts()

        # 加载初始数据
        if self.audio_file and os.path.exists(self.audio_file):
            self._load_audio(self.audio_file)
        if self.initial_lyrics:
            self._parse_and_load_lyrics(self.initial_lyrics)
        elif self.song_title:
            # 尝试加载本地歌词
            local = lyrics_service.get_local_lyrics(self.song_title, self.song_artist, self.audio_file)
            if local:
                self._parse_and_load_lyrics(local)

    def _setup_ui(self):
        """构建界面布局"""
        self.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #1e293b;
                font-size: 13px;
            }
            QLineEdit {
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                padding: 4px 8px;
                background-color: #ffffff;
                color: #0f172a;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #2563eb;
            }
            QPushButton {
                background-color: #ffffff;
                color: #334155;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
            QPushButton:pressed {
                background-color: #e2e8f0;
            }
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                gridline-color: #f1f5f9;
                selection-background-color: #fdf2f8;
                selection-color: #be185d;
            }
            QHeaderView::section {
                background-color: #f1f5f9;
                color: #475569;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                font-weight: 600;
                font-size: 13px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #e2e8f0;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #ec4899;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
                background: #db2777;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # 1. 顶部音频信息栏
        header_card = QFrame()
        header_card.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
        """)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(12)

        header_layout.addWidget(QLabel("歌曲标题:"))
        self.title_input = QLineEdit(self.song_title)
        self.title_input.setFixedWidth(180)
        self.title_input.setPlaceholderText("歌曲名")
        header_layout.addWidget(self.title_input)

        header_layout.addWidget(QLabel("歌手/艺术家:"))
        self.artist_input = QLineEdit(self.song_artist)
        self.artist_input.setFixedWidth(150)
        self.artist_input.setPlaceholderText("歌手")
        header_layout.addWidget(self.artist_input)

        header_layout.addWidget(QLabel("音频文件:"))
        self.audio_path_label = QLabel(os.path.basename(self.audio_file) if self.audio_file else "未关联音频文件")
        self.audio_path_label.setStyleSheet("color: #64748b; font-weight: 500;")
        self.audio_path_label.setToolTip(self.audio_file)
        header_layout.addWidget(self.audio_path_label, 1)

        self.btn_choose_audio = QPushButton("更换音频...")
        self.btn_choose_audio.setCursor(Qt.PointingHandCursor)
        self.btn_choose_audio.clicked.connect(self._on_choose_audio)
        header_layout.addWidget(self.btn_choose_audio)

        main_layout.addWidget(header_card)

        # 2. 播放控制器与实时打点交互栏
        player_card = QFrame()
        player_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffffff, stop:1 #fdf2f8);
                border: 1px solid #fbcfe8;
                border-radius: 8px;
            }
        """)
        player_layout = QVBoxLayout(player_card)
        player_layout.setContentsMargins(14, 10, 14, 10)
        player_layout.setSpacing(8)

        # 播放进度行
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(10)

        self.time_label = QLabel("00:00.00 / 00:00.00")
        self.time_label.setStyleSheet("font-family: 'Consolas', 'Segoe UI', monospace; font-size: 14px; font-weight: 600; color: #db2777;")
        progress_layout.addWidget(self.time_label)

        self.progress_slider = ClickableSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 1)   # 量程在拿到时长后改成毫秒
        self.progress_slider.sliderMoved.connect(self._on_slider_moved)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        progress_layout.addWidget(self.progress_slider, 1)

        player_layout.addLayout(progress_layout)

        # 核心操作按钮行（播放、快进退、速度调节、大打点按钮）
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        self.btn_play_pause = QPushButton("播放")
        self.btn_play_pause.setFixedSize(80, 36)
        self.btn_play_pause.setCursor(Qt.PointingHandCursor)
        self.btn_play_pause.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: 600;
                font-size: 14px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        controls_layout.addWidget(self.btn_play_pause)

        self.btn_seek_back = QPushButton("快退 3 秒")
        self.btn_seek_back.setFixedHeight(36)
        self.btn_seek_back.setCursor(Qt.PointingHandCursor)
        self.btn_seek_back.clicked.connect(lambda: self._seek_relative(-3000))
        controls_layout.addWidget(self.btn_seek_back)

        self.btn_seek_forward = QPushButton("快进 3 秒")
        self.btn_seek_forward.setFixedHeight(36)
        self.btn_seek_forward.setCursor(Qt.PointingHandCursor)
        self.btn_seek_forward.clicked.connect(lambda: self._seek_relative(3000))
        controls_layout.addWidget(self.btn_seek_forward)

        controls_layout.addWidget(QLabel("打点速度:"))
        self.combo_rate = QComboBox()
        self.combo_rate.setFixedHeight(36)
        self.combo_rate.addItems(["1.0x (原速)", "0.8x (减速精准打点)", "0.6x (超慢速打点)"])
        self.combo_rate.currentIndexChanged.connect(self._on_rate_changed)
        controls_layout.addWidget(self.combo_rate)

        controls_layout.addSpacing(10)

        # 核心打点大按钮
        self.btn_stamp = QPushButton("打点标记当前句并跳到下一行 (F5 / Space)")
        self.btn_stamp.setFixedHeight(38)
        self.btn_stamp.setCursor(Qt.PointingHandCursor)
        self.btn_stamp.setToolTip("将播放器当前的时间点赋给当前选中的歌词行，并自动跳转至下一行歌词")
        self.btn_stamp.setStyleSheet("""
            QPushButton {
                background-color: #ec4899;
                color: #ffffff;
                font-weight: 600;
                font-size: 14px;
                border: 1px solid #db2777;
                border-radius: 6px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #db2777;
            }
            QPushButton:pressed {
                background-color: #be185d;
            }
        """)
        self.btn_stamp.clicked.connect(self._stamp_current_row)
        controls_layout.addWidget(self.btn_stamp, 1)

        player_layout.addLayout(controls_layout)
        main_layout.addWidget(player_card)

        # 3. 功能操作工具栏（导入、增删、全局微调、保存）
        tools_widget = QWidget()
        tools_widget.setStyleSheet("""
            QPushButton {
                padding: 4px 10px;
                font-size: 13px;
            }
        """)
        tools_layout = QHBoxLayout(tools_widget)
        tools_layout.setContentsMargins(0, 2, 0, 2)
        tools_layout.setSpacing(6)

        btn_import_txt = QPushButton("导入 TXT 文本...")
        btn_import_txt.setCursor(Qt.PointingHandCursor)
        btn_import_txt.clicked.connect(self._on_import_txt_file)
        tools_layout.addWidget(btn_import_txt)

        btn_paste_text = QPushButton("粘贴文本歌词...")
        btn_paste_text.setCursor(Qt.PointingHandCursor)
        btn_paste_text.clicked.connect(self._on_paste_text)
        tools_layout.addWidget(btn_paste_text)

        btn_import_lrc = QPushButton("导入现有 LRC...")
        btn_import_lrc.setCursor(Qt.PointingHandCursor)
        btn_import_lrc.clicked.connect(self._on_import_lrc_file)
        tools_layout.addWidget(btn_import_lrc)

        tools_layout.addSpacing(6)

        btn_add_line = QPushButton("插入新行 (+)")
        btn_add_line.setCursor(Qt.PointingHandCursor)
        btn_add_line.clicked.connect(self._on_insert_row)
        tools_layout.addWidget(btn_add_line)

        btn_clear_stamps = QPushButton("重置时间戳")
        btn_clear_stamps.setCursor(Qt.PointingHandCursor)
        btn_clear_stamps.setToolTip("清空所有已打点的时间戳，保留文本")
        btn_clear_stamps.clicked.connect(self._on_clear_all_timestamps)
        tools_layout.addWidget(btn_clear_stamps)

        btn_shift_all = QPushButton("全局时间平移...")
        btn_shift_all.setCursor(Qt.PointingHandCursor)
        btn_shift_all.setToolTip("所有歌词时间整体前移或后移若干秒")
        btn_shift_all.clicked.connect(self._on_shift_all_timestamps)
        tools_layout.addWidget(btn_shift_all)

        tools_layout.addStretch()

        btn_save = QPushButton("保存歌词")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setMinimumWidth(110)
        btn_save.setFixedHeight(34)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                font-weight: 600;
                font-size: 13px;
                border: 1px solid #059669;
                border-radius: 6px;
                padding: 4px 14px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        btn_save.clicked.connect(self._on_save_lyrics)
        tools_layout.addWidget(btn_save)

        btn_save_as = QPushButton("另存为...")
        btn_save_as.setCursor(Qt.PointingHandCursor)
        btn_save_as.setMinimumWidth(90)
        btn_save_as.setFixedHeight(34)
        btn_save_as.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #334155;
                font-weight: 500;
                font-size: 13px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 4px 14px;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
            }
        """)
        btn_save_as.clicked.connect(self._on_save_as)
        tools_layout.addWidget(btn_save_as)

        main_layout.addWidget(tools_widget)

        # 4. 歌词表格主界面
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "序号", "时间戳", "时间调整与试听", "原文歌词 (点击直接修改)", "翻译歌词 (可选)", "操作"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Fixed)

        self.table.setColumnWidth(0, 48)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 230)
        self.table.setColumnWidth(5, 78)

        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        main_layout.addWidget(self.table, 1)

        # 5. 底部状态指示栏
        self.status_tip = QLabel("提示: 导入纯文本后，播放音频并在每一句开始时按下【F5】即可快速连续打点。")
        self.status_tip.setStyleSheet("color: #64748b; font-size: 12px;")
        main_layout.addWidget(self.status_tip)

    def _setup_shortcuts(self):
        """配置便捷全局快捷键"""
        # F5 键打点
        self.shortcut_f5 = QShortcut(QKeySequence("F5"), self)
        self.shortcut_f5.activated.connect(self._stamp_current_row)

        # Ctrl+Space 打点
        self.shortcut_ctrl_space = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.shortcut_ctrl_space.activated.connect(self._stamp_current_row)

        # 空格键播放/暂停（当焦点不在输入框时）
        self.shortcut_space = QShortcut(QKeySequence("Space"), self)
        self.shortcut_space.activated.connect(self._on_space_pressed)

    def _on_space_pressed(self):
        """空格键响应：若正在编辑单行文本则不拦截；否则执行打点或播放/暂停"""
        focus_widget = self.focusWidget()
        if isinstance(focus_widget, QLineEdit):
            # 正在文字编辑输入，正常输入空格
            return
        if self.player.state() == QMediaPlayer.PlayingState:
            self._stamp_current_row()
        else:
            self._toggle_play_pause()

    # ================== 音频控制与播放 ==================

    def _on_choose_audio(self):
        """选择或切换本地音频文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择关联音频文件", "", "音频文件 (*.mp3 *.flac *.wav *.ogg *.m4a);;所有文件 (*.*)"
        )
        if file_path:
            self._load_audio(file_path)

    def _load_audio(self, file_path: str):
        """加载音频到专用播放器"""
        if not os.path.exists(file_path):
            return
        self.audio_file = file_path
        self.audio_path_label.setText(os.path.basename(file_path))
        self.audio_path_label.setToolTip(file_path)

        # 自动提取歌曲名与艺术家补充至输入框
        meta = get_audio_metadata(file_path)
        if not self.title_input.text():
            title = meta.get('title') or os.path.splitext(os.path.basename(file_path))[0]
            self.title_input.setText(title)
        if not self.artist_input.text():
            artist = meta.get('artist') or ''
            if artist != '未知艺术家':
                self.artist_input.setText(artist)

        url = QUrl.fromLocalFile(file_path)
        self.player.setMedia(QMediaContent(url))
        self.status_tip.setText(f"已加载音频: {os.path.basename(file_path)}")

    def _toggle_play_pause(self):
        """播放/暂停切换"""
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            if self.player.mediaStatus() == QMediaPlayer.NoMedia and self.audio_file:
                self._load_audio(self.audio_file)
            self.player.play()

    def _on_player_state_changed(self, state):
        """播放状态变化更新按钮文字"""
        # 暂停/停止时冻结渲染时钟，恢复播放后从原处继续
        self._anchor_ms = self._render_ms
        self._anchor_time = time.time()
        if state == QMediaPlayer.PlayingState:
            self.btn_play_pause.setText("暂停")
            self.btn_play_pause.setStyleSheet("""
                QPushButton {
                    background-color: #ea580c;
                    color: #ffffff;
                    font-weight: 600;
                    font-size: 14px;
                    border: none;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #c2410c;
                }
            """)
        else:
            self.btn_play_pause.setText("播放")
            self.btn_play_pause.setStyleSheet("""
                QPushButton {
                    background-color: #2563eb;
                    color: #ffffff;
                    font-weight: 600;
                    font-size: 14px;
                    border: none;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #1d4ed8;
                }
            """)

    def get_duration(self) -> int:
        """获取当前有效总时长（毫秒）"""
        dur = self.player.duration()
        if dur > 0:
            self._cached_duration = dur
            return dur
        return getattr(self, '_cached_duration', 0)

    def _on_player_position_changed(self, pos_ms: int):
        """音频进度变化

        与主播放器同一套判定思路：跳转等待期只接受落入目标容差窗口的回吐，
        正常播放期用"位置连续性"判别驱动 flush 抛出的孤立回退脉冲。
        不再使用"seek 后多少毫秒 / 位置小于多少毫秒"的阈值组合。
        """
        if self.progress_slider.isSliderDown():
            return

        dur_ms = self.get_duration()

        # ---- 第一层：跳转等待期 ----
        if self._seeking_target_ms is not None:
            near_target = abs(pos_ms - self._seeking_target_ms) <= self.SEEK_CONFIRM_TOLERANCE_MS
            flush_like = pos_ms <= 200 and self._seeking_target_ms > 200
            if near_target and not flush_like:
                self._seeking_target_ms = None
                self._last_pos_ms = pos_ms
                if self._pending_seek_ms is not None:
                    # 上一次跳转刚落定，立刻放行排队的那一条（界面由它负责刷新）
                    self._drain_seek_queue()
                    return
            else:
                elapsed_ms = (time.time() - self._seeking_start_time) * 1000.0
                if elapsed_ms < self.SEEK_CONFIRM_TIMEOUT_MS:
                    return
                # 超时：跳转没生效，放弃等待并把基线对齐到驱动真实位置
                self._seeking_target_ms = None
                self._last_pos_ms = pos_ms

        # ---- 第二层：正常播放期，位置只应单调前进；倒退只可能来自曲目重播 ----
        if pos_ms < self._last_pos_ms - self.SEEK_BACKWARD_JUMP_MS:
            near_end = dur_ms > 0 and self._last_pos_ms >= dur_ms - self.SEEK_LOOP_END_MARGIN_MS
            if not near_end:
                return

        self._last_pos_ms = pos_ms
        self._set_clock(pos_ms)
        self._set_display(pos_ms, dur_ms)

    def _set_display(self, pos_ms, dur_ms=None):
        """把顶部时间文字与进度条刷新到指定位置（毫秒量程）"""
        if dur_ms is None:
            dur_ms = self.get_duration()
        self.time_label.setText(f"{self._format_time_ms(pos_ms)} / {self._format_time_ms(dur_ms)}")
        if dur_ms > 0:
            if self.progress_slider.maximum() != dur_ms:
                self.progress_slider.blockSignals(True)
                self.progress_slider.setRange(0, dur_ms)
                self.progress_slider.blockSignals(False)
            self.progress_slider.blockSignals(True)
            self.progress_slider.setValue(int(pos_ms))
            self.progress_slider.blockSignals(False)

    def _set_clock(self, pos_ms):
        """重设渲染时钟锚点"""
        self._anchor_ms = pos_ms
        self._anchor_time = time.time()
        self._render_ms = pos_ms

    def _on_render_tick_ui(self):
        """50ms 渲染：正常播放且没有跳转悬挂时，按墙钟推进顶部进度条"""
        if self.player.state() != QMediaPlayer.PlayingState:
            return
        if self._seeking_target_ms is not None:
            return
        dur_ms = self.get_duration()
        est = self._anchor_ms + int((time.time() - self._anchor_time) * 1000.0)
        if dur_ms > 0:
            est = min(est, dur_ms)
        if est <= self._render_ms:
            return
        self._render_ms = est
        self._set_display(est, dur_ms)

    def _on_player_duration_changed(self, dur_ms: int):
        """音频总时长变化"""
        if dur_ms <= 0:
            dur_ms = self.get_duration()
        else:
            self._cached_duration = dur_ms
        if self._seeking_target_ms is not None:
            # 跳转期间驱动会释放瞬态的 0 时长/旧位置，不刷新界面
            return
        self._set_display(self._render_ms, dur_ms)

    def _on_slider_moved(self, val: int):
        """拖动进度条：仅更新预览时间（毫秒量程，值本身就是毫秒）"""
        self.time_label.setText(f"{self._format_time_ms(val)} / {self._format_time_ms(self.get_duration())}")

    def _apply_seek(self, target_ms, ensure_playing=False):
        """真正发出一次 seek，并把界面立即对齐到目标"""
        self._pending_seek_ms = None
        target_ms = max(0, int(target_ms))
        self._seeking_target_ms = target_ms
        self._seeking_start_time = time.time()
        self._last_pos_ms = target_ms
        if ensure_playing and self.player.state() != QMediaPlayer.PlayingState:
            self.player.play()
        self.player.setPosition(target_ms)

        dur_ms = self.get_duration()
        self._set_clock(target_ms)
        self._set_display(target_ms, dur_ms)

    def _request_seek(self, target_ms, ensure_playing=False):
        """串行化跳转：上一次 seek 未落定前只保留最新目标，不连续下发

        后端会把间隔极短的多个 setPosition 合并/丢弃，导致"点哪一句都从同一处开始"。
        排队后每次跳转都能真正落定，精度回到时间戳本身。
        """
        if self._seeking_target_ms is not None:
            self._pending_seek_ms = (int(target_ms), ensure_playing)
            return
        self._apply_seek(target_ms, ensure_playing)

    def _drain_seek_queue(self):
        """把排队的跳转放行（在确认、超时后调用；也有定时器兜底）"""
        if self._seeking_target_ms is not None:
            elapsed_ms = (time.time() - self._seeking_start_time) * 1000.0
            if elapsed_ms < self.SEEK_CONFIRM_TIMEOUT_MS:
                return
            self._seeking_target_ms = None
        if self._pending_seek_ms is not None:
            target_ms, ensure = self._pending_seek_ms
            self._pending_seek_ms = None
            self._apply_seek(target_ms, ensure)

    def _on_slider_released(self):
        """松开进度条精准跳转播放（毫秒量程，值本身就是毫秒）"""
        self._request_seek(int(self.progress_slider.value()))

    def _seek_relative(self, delta_ms: int):
        """相对跳转播放进度（快退或快进）"""
        cur = self.player.position()
        target = max(0, min(self.player.duration(), cur + delta_ms))
        self._request_seek(target)

    def _on_rate_changed(self, index: int):
        """切换播放倍速"""
        rates = [1.0, 0.8, 0.6]
        if index < len(rates):
            self.player.setPlaybackRate(rates[index])

    @staticmethod
    def _format_time_ms(ms: int) -> str:
        """格式化为 mm:ss.xx"""
        if ms < 0:
            ms = 0
        total_seconds = ms / 1000.0
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)
        hundredths = int((total_seconds - int(total_seconds)) * 100)
        return f"{minutes:02d}:{seconds:02d}.{hundredths:02d}"

    # ================== 导入与解析 ==================

    def _on_import_txt_file(self):
        """从本地 TXT 导入纯文本歌词"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择纯文本歌词文件", "", "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                content = f.read()
        self._load_plain_text(content)

    def _on_paste_text(self):
        """快速弹出粘贴框粘贴文本"""
        dlg = TextPasteDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            text = dlg.get_text()
            if text:
                self._load_plain_text(text)

    def _load_plain_text(self, text: str):
        """将无时间戳纯文本加载到表格"""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            QMessageBox.information(self, "提示", "未检测到有效文本行")
            return

        self.table.setRowCount(0)
        for i, line in enumerate(lines):
            self._add_row(time_ms=-1, lyric_text=line, trans_text="")
        self.table.selectRow(0)
        self.status_tip.setText(f"已成功导入 {len(lines)} 行纯文本歌词，点击【播放】后按【F5】开始打点。")

    def _on_import_lrc_file(self):
        """导入现有 LRC 文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 LRC 歌词文件", "", "LRC 歌词 (*.lrc);;所有文件 (*.*)"
        )
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                content = f.read()
        self._parse_and_load_lyrics(content)

    def _parse_and_load_lyrics(self, content: str):
        """解析标准 LRC 格式，自动合并相同时间戳的翻译行"""
        pattern = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')
        parsed = []  # [(time_ms, text), ...]

        for raw_line in content.splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            # 提取元标签
            ti_match = re.match(r'\[ti:(.*?)\]', raw_line, re.IGNORECASE)
            if ti_match and not self.title_input.text():
                self.title_input.setText(ti_match.group(1).strip())
                continue
            ar_match = re.match(r'\[ar:(.*?)\]', raw_line, re.IGNORECASE)
            if ar_match and not self.artist_input.text():
                self.artist_input.setText(ar_match.group(1).strip())
                continue

            tags = pattern.findall(raw_line)
            if not tags:
                continue

            last_tag_end = raw_line.rfind(']') + 1
            line_text = raw_line[last_tag_end:].strip()

            for minutes, seconds, millis in tags:
                if len(millis) == 2:
                    ms = int(millis) * 10
                else:
                    ms = int(millis.ljust(3, '0')[:3])
                time_ms = int(minutes) * 60000 + int(seconds) * 1000 + ms
                parsed.append((time_ms, line_text))

        if not parsed:
            # 尝试当作纯文本加载
            self._load_plain_text(content)
            return

        parsed.sort(key=lambda x: x[0])

        # 智能匹配翻译行：若两个连续项时间戳相同，后一项作为翻译项
        merged = []
        i = 0
        while i < len(parsed):
            t_ms, txt = parsed[i]
            trans = ""
            if i + 1 < len(parsed) and parsed[i + 1][0] == t_ms:
                trans = parsed[i + 1][1]
                i += 1
            merged.append((t_ms, txt, trans))
            i += 1

        self.table.setRowCount(0)
        for t_ms, txt, trans in merged:
            self._add_row(time_ms=t_ms, lyric_text=txt, trans_text=trans)

        if self.table.rowCount() > 0:
            self.table.selectRow(0)
        self.status_tip.setText(f"已加载 {len(merged)} 行歌词，可随时双击文本修改或微调时间。")

    # ================== 表格与行维护 ==================

    def _add_row(self, time_ms: int = -1, lyric_text: str = "", trans_text: str = "", insert_idx: int = -1):
        """向表格插入一行"""
        row_idx = self.table.rowCount() if insert_idx < 0 else insert_idx
        self.table.insertRow(row_idx)

        # 0. 序号
        item_idx = QTableWidgetItem(str(row_idx + 1))
        item_idx.setTextAlignment(Qt.AlignCenter)
        item_idx.setFlags(item_idx.flags() & ~Qt.ItemIsEditable)
        item_idx.setForeground(QColor("#64748b"))
        self.table.setItem(row_idx, 0, item_idx)

        # 1. 时间戳
        t_str = ms_to_lrc_str(time_ms)
        item_time = QTableWidgetItem(t_str)
        item_time.setTextAlignment(Qt.AlignCenter)
        item_time.setData(Qt.UserRole, time_ms)
        item_time.setFlags(item_time.flags() & ~Qt.ItemIsEditable)
        font = QFont("Consolas", 11)
        font.setBold(True)
        item_time.setFont(font)
        if time_ms >= 0:
            item_time.setForeground(QColor("#db2777"))
        else:
            item_time.setForeground(QColor("#94a3b8"))
        self.table.setItem(row_idx, 1, item_time)

        # 2. 时间微调与试听按钮组
        tune_widget = QWidget()
        tune_widget.setStyleSheet("""
            QPushButton {
                font-size: 11px;
                padding: 1px 2px;
                border-radius: 4px;
            }
        """)
        tune_layout = QHBoxLayout(tune_widget)
        tune_layout.setContentsMargins(2, 2, 2, 2)
        tune_layout.setSpacing(4)

        btn_minus = QPushButton("-0.2s")
        btn_minus.setFixedSize(50, 26)
        btn_minus.setToolTip("当前行时间戳前移 0.2 秒")
        btn_minus.setCursor(Qt.PointingHandCursor)
        btn_minus.clicked.connect(lambda _, r=row_idx: self._adjust_row_time(r, -200))
        tune_layout.addWidget(btn_minus)

        btn_plus = QPushButton("+0.2s")
        btn_plus.setFixedSize(50, 26)
        btn_plus.setToolTip("当前行时间戳后移 0.2 秒")
        btn_plus.setCursor(Qt.PointingHandCursor)
        btn_plus.clicked.connect(lambda _, r=row_idx: self._adjust_row_time(r, 200))
        tune_layout.addWidget(btn_plus)

        btn_mark = QPushButton("打点")
        btn_mark.setFixedSize(46, 26)
        btn_mark.setToolTip("将播放器当前时间直接赋给此行")
        btn_mark.setCursor(Qt.PointingHandCursor)
        btn_mark.setStyleSheet("background-color: #fdf2f8; color: #db2777; border-color: #fbcfe8;")
        btn_mark.clicked.connect(lambda _, r=row_idx: self._stamp_specific_row(r))
        tune_layout.addWidget(btn_mark)

        btn_listen = QPushButton("试听")
        btn_listen.setFixedSize(46, 26)
        btn_listen.setToolTip("从本句开始前 0.3 秒处播放试听")
        btn_listen.setCursor(Qt.PointingHandCursor)
        btn_listen.setStyleSheet("background-color: #eff6ff; color: #2563eb; border-color: #bfdbfe;")
        btn_listen.clicked.connect(lambda _, r=row_idx: self._listen_row(r))
        tune_layout.addWidget(btn_listen)

        self.table.setCellWidget(row_idx, 2, tune_widget)

        # 3. 原文歌词输入框
        edit_lyric = QLineEdit(lyric_text)
        edit_lyric.setPlaceholderText("原文歌词")
        edit_lyric.setStyleSheet("border: 1px solid transparent; background: transparent; padding: 2px 4px;")
        edit_lyric.textChanged.connect(lambda: edit_lyric.setStyleSheet("border: 1px solid #cbd5e1; background: #ffffff; padding: 2px 4px;"))
        self.table.setCellWidget(row_idx, 3, edit_lyric)

        # 4. 翻译歌词输入框
        edit_trans = QLineEdit(trans_text)
        edit_trans.setPlaceholderText("添加翻译（可选）")
        edit_trans.setStyleSheet("border: 1px solid transparent; background: transparent; padding: 2px 4px; color: #475569;")
        edit_trans.textChanged.connect(lambda: edit_trans.setStyleSheet("border: 1px solid #cbd5e1; background: #ffffff; padding: 2px 4px; color: #0f172a;"))
        self.table.setCellWidget(row_idx, 4, edit_trans)

        # 5. 操作按钮：插入(+)、删除(X)
        act_widget = QWidget()
        act_widget.setStyleSheet("""
            QPushButton {
                padding: 0px;
                font-size: 11px;
                border-radius: 4px;
            }
        """)
        act_layout = QHBoxLayout(act_widget)
        act_layout.setContentsMargins(2, 2, 2, 2)
        act_layout.setSpacing(4)

        btn_ins = QPushButton("+")
        btn_ins.setFont(QFont("Segoe UI", 11, QFont.Bold))
        btn_ins.setFixedSize(26, 26)
        btn_ins.setToolTip("在下方插入一行")
        btn_ins.setCursor(Qt.PointingHandCursor)
        btn_ins.clicked.connect(lambda _, r=row_idx: self._on_insert_row_at(r + 1))
        act_layout.addWidget(btn_ins)

        btn_del = QPushButton("X")
        btn_del.setFont(QFont("Segoe UI", 9, QFont.Bold))
        btn_del.setFixedSize(26, 26)
        btn_del.setToolTip("删除当前行")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setStyleSheet("color: #ef4444; border-color: #fca5a5; font-weight: bold; padding: 0px;")
        btn_del.clicked.connect(lambda _, r=row_idx: self._on_delete_row(r))
        act_layout.addWidget(btn_del)

        self.table.setCellWidget(row_idx, 5, act_widget)

    def _refresh_row_indices(self):
        """刷新序号以及所有行内绑定的索引闭包"""
        for r in range(self.table.rowCount()):
            idx_item = self.table.item(r, 0)
            if idx_item:
                idx_item.setText(str(r + 1))

            # 重新连接微调按钮与删除按钮以对应最新的行号
            tune_widget = self.table.cellWidget(r, 2)
            if tune_widget:
                buttons = tune_widget.findChildren(QPushButton)
                if len(buttons) >= 4:
                    buttons[0].clicked.disconnect()
                    buttons[0].clicked.connect(lambda _, row=r: self._adjust_row_time(row, -200))
                    buttons[1].clicked.disconnect()
                    buttons[1].clicked.connect(lambda _, row=r: self._adjust_row_time(row, 200))
                    buttons[2].clicked.disconnect()
                    buttons[2].clicked.connect(lambda _, row=r: self._stamp_specific_row(row))
                    buttons[3].clicked.disconnect()
                    buttons[3].clicked.connect(lambda _, row=r: self._listen_row(row))

            act_widget = self.table.cellWidget(r, 5)
            if act_widget:
                act_btns = act_widget.findChildren(QPushButton)
                if len(act_btns) >= 2:
                    act_btns[0].clicked.disconnect()
                    act_btns[0].clicked.connect(lambda _, row=r: self._on_insert_row_at(row + 1))
                    act_btns[1].clicked.disconnect()
                    act_btns[1].clicked.connect(lambda _, row=r: self._on_delete_row(row))

    def _on_insert_row(self):
        """在当前选中行下方或末尾插入空行"""
        cur = self.table.currentRow()
        insert_at = cur + 1 if cur >= 0 else self.table.rowCount()
        self._on_insert_row_at(insert_at)

    def _on_insert_row_at(self, idx: int):
        """在指定位置插入新行"""
        self._add_row(time_ms=-1, lyric_text="", trans_text="", insert_idx=idx)
        self._refresh_row_indices()
        self.table.selectRow(idx)

    def _on_delete_row(self, row_idx: int):
        """删除指定行"""
        if 0 <= row_idx < self.table.rowCount():
            self.table.removeRow(row_idx)
            self._refresh_row_indices()

    # ================== 打点与时间调整 ==================

    def _stamp_current_row(self):
        """将当前播放时间戳赋给选中的行，并平滑自动跳转至下一行"""
        if self.table.rowCount() == 0:
            return
        cur_row = self.table.currentRow()
        if cur_row < 0:
            cur_row = 0

        self._stamp_specific_row(cur_row)

        # 自动跳至下一行并聚焦
        next_row = cur_row + 1
        if next_row < self.table.rowCount():
            self.table.selectRow(next_row)
            self.table.scrollToItem(self.table.item(next_row, 0))
            self.status_tip.setText(f"第 {cur_row + 1} 句已打点，请在第 {next_row + 1} 句唱响时继续按【F5】打点。")
        else:
            self.status_tip.setText(f"已完成全部 {self.table.rowCount()} 句打点！点击右上角【保存歌词】即可生效。")

    def _stamp_specific_row(self, row_idx: int):
        """将播放器当前时间戳写入指定行"""
        if not (0 <= row_idx < self.table.rowCount()):
            return
        pos_ms = self.player.position()
        self._set_row_time(row_idx, pos_ms)

    def _adjust_row_time(self, row_idx: int, delta_ms: int):
        """对某一行时间进行微调 (+/- 200ms)"""
        if not (0 <= row_idx < self.table.rowCount()):
            return
        item_time = self.table.item(row_idx, 1)
        if not item_time:
            return
        cur_ms = item_time.data(Qt.UserRole)
        if cur_ms is None or cur_ms < 0:
            # 如果尚未打点，取当前播放进度
            cur_ms = self.player.position()
        target_ms = max(0, cur_ms + delta_ms)
        self._set_row_time(row_idx, target_ms)

    def _set_row_time(self, row_idx: int, time_ms: int):
        """更新某一行的显示与存储时间"""
        item_time = self.table.item(row_idx, 1)
        if not item_time:
            return
        item_time.setData(Qt.UserRole, time_ms)
        item_time.setText(ms_to_lrc_str(time_ms))
        if time_ms >= 0:
            item_time.setForeground(QColor("#db2777"))
        else:
            item_time.setForeground(QColor("#94a3b8"))

    def _listen_row(self, row_idx: int):
        """试听某一行歌词"""
        if not (0 <= row_idx < self.table.rowCount()):
            return
        item_time = self.table.item(row_idx, 1)
        if not item_time:
            return
        time_ms = item_time.data(Qt.UserRole)
        if time_ms is None or time_ms < 0:
            QMessageBox.information(self, "提示", "该行尚未设置时间戳，请先打点。")
            return
        # 提前 300 毫秒开始播放以提供听觉缓冲（保留原有听感）
        start_ms = max(0, time_ms - 300)
        # 走串行化通道：上一次跳转未落定前不会连发，避免被后端合并
        self._request_seek(start_ms, ensure_playing=True)
        self.table.selectRow(row_idx)

    def _on_clear_all_timestamps(self):
        """清空所有时间戳，保留文本"""
        if self.table.rowCount() == 0:
            return
        reply = QMessageBox.question(
            self, "确认清空", "确定要清空所有已打点的时间戳并重新开始打点吗？\n（原文和翻译文本将完整保留）",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for r in range(self.table.rowCount()):
                self._set_row_time(r, -1)
            self.table.selectRow(0)
            self.status_tip.setText("已清空所有时间戳，可以重新从第一句开始打点。")

    def _on_shift_all_timestamps(self):
        """全局平移所有时间戳"""
        if self.table.rowCount() == 0:
            return
        from PyQt5.QtWidgets import QInputDialog
        val, ok = QInputDialog.getDouble(
            self, "全局时间平移",
            "请输入所有歌词整体调整的秒数（正数为延后，负数为提前，例如 0.5 或 -0.5）：",
            0.0, -600.0, 600.0, 2
        )
        if ok and val != 0:
            delta_ms = int(val * 1000)
            shifted = 0
            for r in range(self.table.rowCount()):
                item_time = self.table.item(r, 1)
                if item_time:
                    cur_ms = item_time.data(Qt.UserRole)
                    if cur_ms is not None and cur_ms >= 0:
                        self._set_row_time(r, max(0, cur_ms + delta_ms))
                        shifted += 1
            self.status_tip.setText(f"已对 {shifted} 行歌词全局平移 {val:+.2f} 秒。")

    # ================== 保存与导出 ==================

    def _compile_lrc(self) -> str:
        """根据当前表格数据编译为标准 LRC 格式文本"""
        lines = []
        title = self.title_input.text().strip()
        artist = self.artist_input.text().strip()

        if title:
            lines.append(f"[ti:{title}]")
        if artist:
            lines.append(f"[ar:{artist}]")

        for r in range(self.table.rowCount()):
            item_time = self.table.item(r, 1)
            time_ms = item_time.data(Qt.UserRole) if item_time else -1

            t_tag = ms_to_lrc_str(time_ms) if time_ms is not None and time_ms >= 0 else "[00:00.00]"

            lyric_widget = self.table.cellWidget(r, 3)
            lyric_text = lyric_widget.text().strip() if isinstance(lyric_widget, QLineEdit) else ""

            trans_widget = self.table.cellWidget(r, 4)
            trans_text = trans_widget.text().strip() if isinstance(trans_widget, QLineEdit) else ""

            if lyric_text:
                lines.append(f"{t_tag}{lyric_text}")
            if trans_text:
                # 翻译行保存相同时间戳，标准双语 LRC 格式
                lines.append(f"{t_tag}{trans_text}")

        return "\n".join(lines) + "\n"

    def _on_save_lyrics(self):
        """保存歌词到项目资源歌词目录 (src/resources/lyrics)"""
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "提示", "当前没有可保存的歌词内容")
            return

        title = self.title_input.text().strip()
        if not title:
            title = os.path.splitext(os.path.basename(self.audio_file))[0] if self.audio_file else "未知歌曲"
        artist = self.artist_input.text().strip()

        lrc_content = self._compile_lrc()
        success = lyrics_service.save_lyrics_to_file(title, artist, lrc_content, self.audio_file)

        if success:
            QMessageBox.information(
                self, "保存成功",
                f"LRC 歌词已成功保存！\n\n"
                f"歌曲名: {title}\n"
                f"保存目录: {lyrics_service.LYRICS_DIR}"
            )
            self.lyrics_saved.emit(lrc_content, title, artist, self.audio_file)
            self.status_tip.setText("歌词保存成功并已同步生效。")
        else:
            QMessageBox.warning(self, "保存失败", "保存歌词失败，请检查目录读写权限。")

    def _on_save_as(self):
        """另存为其他目录与文件"""
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "提示", "当前没有可保存的歌词内容")
            return

        default_name = f"{self.song_artist} - {self.song_title}.lrc".strip(" -")
        if not default_name or default_name == ".lrc":
            default_name = "lyrics.lrc"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "另存为 LRC 歌词文件", default_name, "LRC 歌词 (*.lrc);;所有文件 (*.*)"
        )
        if not file_path:
            return

        lrc_content = self._compile_lrc()
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(lrc_content)
            QMessageBox.information(self, "保存成功", f"歌词已成功另存为至:\n{file_path}")
            self.lyrics_saved.emit(lrc_content, self.title_input.text().strip(), self.artist_input.text().strip(), file_path)
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"另存为失败: {e}")

    def closeEvent(self, event):
        """关闭对话框时安全停止内部播放器"""
        if hasattr(self, 'player'):
            self.player.stop()
        super().closeEvent(event)
