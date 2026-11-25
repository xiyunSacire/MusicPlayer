"""
播放控制面板
"""
import os
import time
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QPushButton, 
                             QSlider, QLabel, QVBoxLayout)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QPixmap

class ClickableSlider(QSlider):
    """支持点击任意位置精准定位与丝滑拖动的滑动条"""
    
    def _pos_to_val(self, pos_x: int) -> int:
        """根据鼠标水平像素坐标精准折算滑动条数值"""
        w = self.width()
        if w <= 0:
            return self.minimum()
        ratio = max(0.0, min(1.0, pos_x / float(w)))
        val_range = self.maximum() - self.minimum()
        return int(self.minimum() + ratio * val_range)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.orientation() == Qt.Horizontal and self.width() > 0:
                self.setSliderDown(True)
                new_val = self._pos_to_val(event.x())
                self.setValue(new_val)
                self.sliderMoved.emit(new_val)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown() and (event.buttons() & Qt.LeftButton):
            if self.orientation() == Qt.Horizontal and self.width() > 0:
                new_val = self._pos_to_val(event.x())
                self.setValue(new_val)
                self.sliderMoved.emit(new_val)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.isSliderDown():
                new_val = self._pos_to_val(event.x())
                self.setValue(new_val)
                self.setSliderDown(False)
                self.sliderReleased.emit()
                event.accept()
                return
        super().mouseReleaseEvent(event)

class PlayerControls(QWidget):
    """播放控制面板"""
    # 定义信号（当用户操作控件时发出）
    play_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    volume_changed = pyqtSignal(int)
    position_changed = pyqtSignal(int)
    mode_changed = pyqtSignal(str)
    desktop_lyrics_toggled = pyqtSignal(bool)   # 桌面歌词开关

    SCRUB_EMIT_INTERVAL_S = 0.15   # 拖动时两次真实 seek 的最小间隔（保持有声音跟随又不冲刷后端）
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_playing = False  # 播放状态
        self.current_mode = 'loop'  # 默认循环播放
        self.setup_ui()
            
    def setup_ui(self):
        """设置控制面板界面"""
        self.setStyleSheet("""
            PlayerControls {
                background-color: #ffffff;
                border-top: 1px solid #e2e8f0;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 4, 16, 4)  # 精致紧凑边距
        main_layout.setSpacing(1)  # 控件间适度微距
        
        # 进度条（支持直接点击跳转）
        self.progress_slider = ClickableSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 1)
        self.progress_slider.setValue(0)
        self.progress_slider.setEnabled(False)
        self.progress_slider.setCursor(Qt.PointingHandCursor)
        # 采用柔美淡粉色现代渐变
        self.progress_slider.setStyleSheet("""
            QSlider {
                min-height: 10px;
                max-height: 14px;
            }
            QSlider::groove:horizontal {
                height: 3px;
                background: #f1f5f9;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f9a8d4, stop:1 #ec4899);
                border-radius: 2px;
            }
            QSlider::add-page:horizontal {
                background: #f1f5f9;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 2px solid #ec4899;
                width: 10px;
                height: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }
            QSlider::handle:horizontal:hover {
                background: #ec4899;
                border: 2px solid #ffffff;
                width: 12px;
                height: 12px;
                margin: -5px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:disabled {
                background: #cbd5e1;
                border: 1px solid #cbd5e1;
            }
        """)
        self.progress_slider.sliderMoved.connect(self.on_progress_moved)
        self.progress_slider.sliderReleased.connect(self.on_slider_released)
        main_layout.addWidget(self.progress_slider)
        
        # 时间标签
        time_layout = QHBoxLayout()
        time_layout.setContentsMargins(2, 0, 2, 0)
        self.current_time_label = QLabel("00:00.00")
        self.total_time_label = QLabel("00:00")
        
        time_label_style = """
            QLabel {
                color: #64748b;
                font-family: 'Segoe UI', 'Consolas', 'Microsoft YaHei', sans-serif;
                font-size: 10px;
                font-weight: 500;
                line-height: 10px;
            }
        """
        self.current_time_label.setStyleSheet(time_label_style)
        self.total_time_label.setStyleSheet(time_label_style)
        
        time_layout.addWidget(self.current_time_label)
        time_layout.addStretch()
        time_layout.addWidget(self.total_time_label)
        main_layout.addLayout(time_layout)
        
        # 控制按钮布局
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(12)

        # 左侧：科技感灰色带边框矩形（包裹播放模式切换组件，与右侧音量卡片对称）
        self.mode_card = QWidget()
        self.mode_card.setObjectName("modeCard")
        self.mode_card.setStyleSheet("""
            QWidget#modeCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f8fafc);
                border: 1px solid #cbd5e1;
                border-radius: 10px;
            }
        """)
        self.mode_card.setFixedWidth(200)
        mode_layout = QHBoxLayout(self.mode_card)
        mode_layout.setContentsMargins(14, 4, 14, 4)
        mode_layout.setSpacing(10)

        self.mode_label = QLabel("模式:")
        self.mode_label.setStyleSheet("color: #475569; font-size: 13px; font-weight: 600;")
        mode_layout.addWidget(self.mode_label)

        self.mode_btn = QPushButton("循环播放")
        self.mode_btn.setCursor(Qt.PointingHandCursor)
        self.mode_btn.setToolTip("点击切换：循环播放 / 随机播放 / 顺序播放")
        self.mode_btn.setStyleSheet("""
            QPushButton {
                background: #f1f5f9;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #fdf2f8;
                color: #db2777;
                border-color: #f472b6;
            }
            QPushButton:pressed {
                background: #fce7f3;
            }
        """)
        self.mode_btn.clicked.connect(self._cycle_playback_mode)
        mode_layout.addWidget(self.mode_btn, 1)

        controls_layout.addWidget(self.mode_card, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # 桌面歌词开关（与模式卡片同高，选中态高亮）
        self.desktop_lyrics_btn = QPushButton("桌面歌词")
        self.desktop_lyrics_btn.setCheckable(True)
        self.desktop_lyrics_btn.setCursor(Qt.PointingHandCursor)
        self.desktop_lyrics_btn.setToolTip("在桌面上显示悬浮歌词（置顶、可拖动，双击锁定后鼠标穿透）")
        self.desktop_lyrics_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f8fafc);
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #fdf2f8;
                color: #db2777;
                border-color: #f472b6;
            }
            QPushButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fbcfe8, stop:1 #f9a8d4);
                color: #9d174d;
                border: 1px solid #f472b6;
            }
        """)
        self.desktop_lyrics_btn.toggled.connect(self.desktop_lyrics_toggled.emit)
        controls_layout.addWidget(self.desktop_lyrics_btn, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        controls_layout.addStretch(1)

        # 中间：科技感灰色带边框矩形（包裹上一首、播放、下一首按钮）
        self.playback_card = QWidget()
        self.playback_card.setObjectName("playbackCard")
        self.playback_card.setStyleSheet("""
            QWidget#playbackCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f8fafc);
                border: 1px solid #cbd5e1;
                border-radius: 12px;
            }
        """)
        self.playback_layout = QHBoxLayout(self.playback_card)
        self.playback_layout.setContentsMargins(24, 0, 24, 0)
        self.playback_layout.setSpacing(32)  # 按钮左右间距适度放大
        
        btn_style = """
            QPushButton {
                border: none;
                background: transparent;
                padding: 0px;
            }
            QPushButton:hover {
                /* 微妙悬停反馈 */
            }
            QPushButton:pressed {
                padding-top: 2px;
            }
        """
        
        # 上一首按钮
        self.prev_btn = QPushButton()
        icon_path1 = os.path.join(os.path.dirname(__file__), "..", "resources", "icons", "Left.png")
        self.prev_btn.setIcon(QIcon(icon_path1))
        self.prev_btn.setEnabled(True)
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setStyleSheet(btn_style)
        self.prev_btn.clicked.connect(self.on_prev_clicked)
        self.playback_layout.addWidget(self.prev_btn, alignment=Qt.AlignCenter)

        # 播放/暂停按钮
        self.play_btn = QPushButton()
        icon_path3 = os.path.join(os.path.dirname(__file__), "..", "resources", "icons", "play.png")
        self.play_btn.setIcon(QIcon(icon_path3))
        self.play_btn.setEnabled(True)
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setStyleSheet(btn_style)
        self.play_btn.clicked.connect(self.on_play_pause_clicked)
        self.playback_layout.addWidget(self.play_btn, alignment=Qt.AlignCenter)

        # 下一首按钮
        self.next_btn = QPushButton()
        icon_path2 = os.path.join(os.path.dirname(__file__), "..", "resources", "icons", "Right.png")
        self.next_btn.setIcon(QIcon(icon_path2))
        self.next_btn.setEnabled(True)
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setStyleSheet(btn_style)
        self.next_btn.clicked.connect(self.on_next_clicked)
        self.playback_layout.addWidget(self.next_btn, alignment=Qt.AlignCenter)
        
        controls_layout.addWidget(self.playback_card, alignment=Qt.AlignCenter)
        controls_layout.addStretch(1)
        
        # 右侧：科技感灰色带边框矩形（包裹音量组件并整体放大）
        self.volume_card = QWidget()
        self.volume_card.setObjectName("volumeCard")
        self.volume_card.setStyleSheet("""
            QWidget#volumeCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f8fafc);
                border: 1px solid #cbd5e1;
                border-radius: 10px;
            }
        """)
        self.volume_card.setFixedWidth(200)
        vol_layout = QHBoxLayout(self.volume_card)
        vol_layout.setContentsMargins(14, 4, 16, 4)
        vol_layout.setSpacing(10)
        
        self.volume_label = QLabel("音量:")
        self.volume_label.setStyleSheet("color: #475569; font-size: 13px; font-weight: 600;")
        vol_layout.addWidget(self.volume_label)

        self.volume_slider = ClickableSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(125)  # 音量条放大
        self.volume_slider.setEnabled(True)
        self.volume_slider.setCursor(Qt.PointingHandCursor)
        self.volume_slider.setStyleSheet("""
            QSlider {
                min-height: 16px;
                max-height: 20px;
            }
            QSlider::groove:horizontal {
                height: 5px;
                background: #e2e8f0;
                border-radius: 2.5px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f472b6, stop:1 #ec4899);
                border-radius: 2.5px;
            }
            QSlider::add-page:horizontal {
                background: #e2e8f0;
                border-radius: 2.5px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 2px solid #ec4899;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #ec4899;
                border: 2px solid #ffffff;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
        """)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        vol_layout.addWidget(self.volume_slider)
        controls_layout.addWidget(self.volume_card, alignment=Qt.AlignRight | Qt.AlignVCenter)
        
        main_layout.addLayout(controls_layout)
        
        # 最小高度降至55px（约为先前110px的1/2，且支持自适应平滑缩放）
        self.setMinimumHeight(55)
        self._update_button_sizes()

    def minimumSizeHint(self):
        """提供紧凑的尺寸建议，确保QSplitter能自由下调至55px高度"""
        return QSize(200, 55)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_button_sizes()

    def _update_button_sizes(self):
        """根据当前面板高度动态自适应按钮与科技卡片尺寸，保证居中且无遮挡"""
        h = self.height()
        avail = max(20, h - 36)
        card_inner_h = max(16, avail - 12)
        play_dia = min(110, max(20, int(card_inner_h * 0.88)))
        oval_h = max(16, int(play_dia * 0.78))
        oval_w = int(oval_h * 1.51)
        
        # 按钮间距动态平滑适配
        spacing = max(16, min(36, int(play_dia * 0.52)))
        if hasattr(self, 'playback_layout'):
            self.playback_layout.setSpacing(spacing)
            
        if hasattr(self, 'playback_card'):
            self.playback_card.setFixedHeight(play_dia + 12)
            vol_h = max(28, min(42, int(play_dia * 0.65)))
            self.volume_card.setFixedHeight(vol_h)
            if hasattr(self, 'mode_card'):
                self.mode_card.setFixedHeight(vol_h)
            if hasattr(self, 'desktop_lyrics_btn'):
                self.desktop_lyrics_btn.setFixedHeight(vol_h)
            
            self.prev_btn.setFixedSize(oval_w, oval_h)
            self.prev_btn.setIconSize(QSize(oval_w, oval_h))
            
            self.play_btn.setFixedSize(play_dia, play_dia)
            self.play_btn.setIconSize(QSize(play_dia, play_dia))
            
            self.next_btn.setFixedSize(oval_w, oval_h)
            self.next_btn.setIconSize(QSize(oval_w, oval_h))
        
    def set_desktop_lyrics_checked(self, checked):
        """外部同步桌面歌词按钮状态（不触发信号，避免回环）"""
        if not hasattr(self, 'desktop_lyrics_btn'):
            return
        self.desktop_lyrics_btn.blockSignals(True)
        self.desktop_lyrics_btn.setChecked(bool(checked))
        self.desktop_lyrics_btn.blockSignals(False)

    # ========== 槽函数（接收播放器信号更新UI） ==========

    def update_play_state(self, state):
        """更新播放状态（来自播放器）"""
        self.is_playing = (state == 'playing')
        self.play_btn.setText("")
        icon_name = "pause.png" if self.is_playing else "play.png"
        icon_path = os.path.join(os.path.dirname(__file__), "..", "resources", "icons", icon_name)
        if os.path.exists(icon_path):
            self.play_btn.setIcon(QIcon(icon_path))
            sz = self.play_btn.size()
            self.play_btn.setIconSize(sz if sz.isValid() and sz.width() > 0 else QSize(60, 60))

    def update_position(self, position_ms, duration_ms):
        """更新进度条和时间标签

        position_ms 由 MusicPlayer 的渲染时钟以 50ms 节奏推进（墙钟插值），
        这里是纯显示：滑块量程改为毫秒，彻底消除 1% 量化造成的"一跳一跳"。
        """
        # 用户正在按住/拖动滑块时，不被外部回填覆盖
        if self.progress_slider.isSliderDown():
            return

        if duration_ms > 0:
            self._last_valid_duration = duration_ms
        else:
            duration_ms = getattr(self, '_last_valid_duration', 0)

        if duration_ms > 0:
            self.progress_slider.setEnabled(True)
            if self.progress_slider.maximum() != duration_ms:
                self.progress_slider.blockSignals(True)
                self.progress_slider.setRange(0, duration_ms)
                self.progress_slider.blockSignals(False)
            self.progress_slider.blockSignals(True)
            self.progress_slider.setValue(int(position_ms))
            self.progress_slider.blockSignals(False)

            self.current_time_label.setText(self._format_time_ms(position_ms))
            total_text = self._format_time(duration_ms // 1000)
            if self.total_time_label.text() != total_text:
                self.total_time_label.setText(total_text)
        elif position_ms > 0:
            self.current_time_label.setText(self._format_time_ms(position_ms))
        else:
            if not self.is_playing and duration_ms <= 0:
                self.progress_slider.setEnabled(False)
                self.current_time_label.setText("00:00.00")
                self.total_time_label.setText("00:00")
            
    def update_volume(self, volume):
        """更新音量滑块"""
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(volume)
        self.volume_slider.blockSignals(False)
        
    # ========== 用户操作转发信号 ==========

    def on_play_pause_clicked(self):
        if self.is_playing:
            self.pause_clicked.emit()
        else:
            self.play_clicked.emit()

    def on_prev_clicked(self):
        self.prev_clicked.emit()

    def on_next_clicked(self):
        self.next_clicked.emit()

    def on_volume_changed(self, value):
        self.volume_changed.emit(value)

    def _cycle_playback_mode(self):
        """循环切换播放模式：循环 -> 随机 -> 顺序 -> 循环"""
        modes = ['loop', 'random', 'sequential']
        cur_idx = modes.index(self.current_mode) if self.current_mode in modes else 0
        next_mode = modes[(cur_idx + 1) % len(modes)]
        self.set_playback_mode(next_mode)
        self.mode_changed.emit(next_mode)

    def set_playback_mode(self, mode: str):
        """设置播放模式并更新界面显示"""
        mode_lower = (mode or 'loop').lower()
        if mode_lower not in ['loop', 'random', 'sequential']:
            mode_lower = 'loop'
        self.current_mode = mode_lower
        
        mode_names = {
            'loop': '循环播放',
            'random': '随机播放',
            'sequential': '顺序播放'
        }
        mode_tips = {
            'loop': '当前模式：列表循环播放',
            'random': '当前模式：随机播放',
            'sequential': '当前模式：按顺序播放至列表末尾'
        }
        if hasattr(self, 'mode_btn'):
            self.mode_btn.setText(mode_names.get(mode_lower, '循环播放'))
            self.mode_btn.setToolTip(mode_tips.get(mode_lower, ''))

    def on_progress_moved(self, value):
        """用户按住/拖拽滑块：实时预览时间，并按 150ms 节流发起真实跳转

        拖动过程中节流地发 seek，声音就会跟着手指走（有快进声），
        但不会因为每秒几十次 setPosition 把后端冲刷到卡死。
        """
        target_ms = int(value)
        self.current_time_label.setText(self._format_time_ms(target_ms))

        now = time.time()
        if now - getattr(self, '_last_scrub_emit', 0.0) >= self.SCRUB_EMIT_INTERVAL_S:
            self._last_scrub_emit = now
            self.position_changed.emit(target_ms)

    def on_slider_released(self):
        """松开鼠标：补发最后一次跳转，确保落点精确等于松手位置"""
        target_ms = int(self.progress_slider.value())
        self._last_scrub_emit = 0.0
        self.current_time_label.setText(self._format_time_ms(target_ms))
        self.position_changed.emit(target_ms)

    def seek_to_ms(self, target_ms: int):
        """点击歌词时间戳时，等效于操作播放条跳转到对应时间点（走完全相同的播放条链路）

        这里只做两件事：把界面立刻显示成目标状态（意图反馈）、把意图发给播放器。
        是否正确到达由 MusicPlayer 的跳转状态机确认，播放条不再自己维护跳转锁。
        """
        if target_ms < 0:
            return

        dur_ms = getattr(self, '_last_valid_duration', 0)
        if dur_ms > 0:
            self.progress_slider.blockSignals(True)
            self.progress_slider.setRange(0, dur_ms)
            self.progress_slider.setValue(int(target_ms))
            self.progress_slider.blockSignals(False)
            self.total_time_label.setText(self._format_time(dur_ms // 1000))

        self.current_time_label.setText(self._format_time_ms(target_ms))
        self._last_scrub_emit = 0.0

        # 触发播放条的 position_changed 信号，统一由播放器执行跳转
        self.position_changed.emit(target_ms)

    def reset_display(self):
        """无媒体（清空列表等）时复位进度条与时间显示

        时间清零现在只允许发生在这类"确实没有媒体"的显式场景，
        不再由底层瞬态 stopped 状态或 0 脉冲隐式触发。
        """
        self._last_valid_duration = 0
        self.progress_slider.blockSignals(True)
        self.progress_slider.setRange(0, 1)
        self.progress_slider.setValue(0)
        self.progress_slider.blockSignals(False)
        self.progress_slider.setEnabled(False)
        self.current_time_label.setText("00:00.00")
        self.total_time_label.setText("00:00")

    # ========== 辅助函数 ==========

    @staticmethod
    def _format_time_ms(ms):
        """格式化毫秒为 mm:ss.cc（带百分秒，供进度条时间使用）"""
        if ms < 0:
            ms = 0
        total_cs = int(ms) // 10
        m = total_cs // 6000
        s = (total_cs // 100) % 60
        cs = total_cs % 100
        return f"{m:02d}:{s:02d}.{cs:02d}"

    def _format_time(self, seconds):
        """格式化时间为 mm:ss 或 hh:mm:ss"""
        if seconds < 3600:
            m = seconds // 60
            s = seconds % 60
            return f"{m:02d}:{s:02d}"
        else:
            h = seconds // 3600
            m = (seconds % 3600) // 60
            s = seconds % 60
            return f"{h:02d}:{m:02d}:{s:02d}"
