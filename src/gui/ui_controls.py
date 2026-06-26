"""
播放控制面板
"""
import os
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QPushButton, 
                             QSlider, QLabel, QVBoxLayout)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QPixmap

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
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.is_playing = False  # 播放状态
            
    def setup_ui(self):
        """设置控制面板界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 2, 5, 2)  # 收紧边距
        main_layout.setSpacing(3)  # 控件间紧凑间距
        
        # 进度条
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 100)
        self.progress_slider.setValue(0)
        self.progress_slider.setEnabled(False)
        self.progress_slider.sliderMoved.connect(self.on_progress_moved)
        main_layout.addWidget(self.progress_slider)
        
        # 时间标签
        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("00:00")
        self.total_time_label = QLabel("00:00")
        time_layout.addWidget(self.current_time_label)
        time_layout.addStretch()
        time_layout.addWidget(self.total_time_label)
        main_layout.addLayout(time_layout)
        
        # 控制按钮布局
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        # 左侧透明占位组件（与右侧音量控制对称，使按钮完美居中）
        left_placeholder_label = QLabel("音量:")
        left_placeholder_label.setStyleSheet("color: transparent;")
        controls_layout.addWidget(left_placeholder_label)

        left_placeholder_slider = QSlider(Qt.Horizontal)
        left_placeholder_slider.setRange(0, 100)
        left_placeholder_slider.setValue(70)
        left_placeholder_slider.setFixedWidth(100)
        left_placeholder_slider.setEnabled(False)
        left_placeholder_slider.setStyleSheet("QSlider::groove:horizontal { background: transparent; } QSlider::handle:horizontal { background: transparent; }")
        controls_layout.addWidget(left_placeholder_slider)

        # 播放控制按钮子布局（内部完美居中）
        playback_layout = QHBoxLayout()
        playback_layout.setSpacing(8)  # 按钮间距收紧
        playback_layout.addStretch(1)
        
        # 统一按钮和图标尺寸
        BTN_W, BTN_H = 150, 150  # 上一首/下一首按钮大小
        ICON_SIZE = 150  # 上一首/下一首图标大小
        
        PLAY_SIZE = 200  # 播放按钮专属大小（图标+按钮都更大）
        
        # 上一首按钮
        self.prev_btn = QPushButton()
        icon_path1 = os.path.join(os.path.dirname(__file__), "..", "resources", "icons", "Left.png")
        self.prev_btn.setIcon(QIcon(icon_path1))
        self.prev_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.prev_btn.setFixedSize(BTN_W, BTN_H)
        self.prev_btn.setEnabled(True)
        self.prev_btn.setStyleSheet("QPushButton { border: none; background: transparent; padding: 0px; }")
        self.prev_btn.clicked.connect(self.on_prev_clicked)
        
        # 用容器包裹上一首按钮，通过边距实现精确偏移（上移25px）
        prev_container = QWidget()
        prev_container_layout = QHBoxLayout(prev_container)
        prev_container_layout.setContentsMargins(0, 25, 0, 0)  # (左, 上, 右, 下)
        prev_container_layout.setSpacing(0)
        prev_container_layout.addWidget(self.prev_btn)
        playback_layout.addWidget(prev_container, alignment=Qt.AlignVCenter)

        # 播放/暂停按钮（比其他按钮更大）
        self.play_btn = QPushButton()
        icon_path3 = os.path.join(os.path.dirname(__file__), "..", "resources", "icons", "play.png")
        self.play_btn.setIcon(QIcon(icon_path3))
        self.play_btn.setIconSize(QSize(PLAY_SIZE, PLAY_SIZE))
        self.play_btn.setFixedSize(PLAY_SIZE, PLAY_SIZE)
        self.play_btn.setEnabled(True)
        self.play_btn.setStyleSheet("QPushButton { border: none; background: transparent; padding: 0px; }")
        self.play_btn.clicked.connect(self.on_play_pause_clicked)
        
        # 用容器包裹播放按钮，通过边距实现精确偏移（右移30px）
        play_container = QWidget()
        play_container_layout = QHBoxLayout(play_container)
        play_container_layout.setContentsMargins(30, 0, 0, 0)  # (左, 上, 右, 下)
        play_container_layout.setSpacing(0)
        play_container_layout.addWidget(self.play_btn)
        playback_layout.addWidget(play_container, alignment=Qt.AlignVCenter)

        # 下一首按钮
        self.next_btn = QPushButton()
        icon_path2 = os.path.join(os.path.dirname(__file__), "..", "resources", "icons", "Right.png")
        self.next_btn.setIcon(QIcon(icon_path2))
        self.next_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.next_btn.setFixedSize(BTN_W, BTN_H)
        self.next_btn.setEnabled(True)
        self.next_btn.setStyleSheet("QPushButton { border: none; background: transparent; padding: 0px; }")
        self.next_btn.clicked.connect(self.on_next_clicked)
        
        # 用容器包裹下一首按钮，通过边距实现精确偏移（上移25px）
        next_container = QWidget()
        next_container_layout = QHBoxLayout(next_container)
        next_container_layout.setContentsMargins(0, 25, 0, 0)  # (左, 上, 右, 下)
        next_container_layout.setSpacing(0)
        next_container_layout.addWidget(self.next_btn)
        playback_layout.addWidget(next_container, alignment=Qt.AlignVCenter)
        
        playback_layout.addStretch(1)
        
        # 播放按钮组占据所有可伸缩空间，内部居中
        controls_layout.addLayout(playback_layout, stretch=1)
        
        # 音量控制固定在最右侧
        self.volume_label = QLabel("音量:")
        controls_layout.addWidget(self.volume_label)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setEnabled(True)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        controls_layout.addWidget(self.volume_slider)
        
        main_layout.addLayout(controls_layout)
        
        # 根据最大按钮高度自适应面板高度（仅保留最小必要边距）
        self.setFixedHeight(max(BTN_H, PLAY_SIZE) + 5)
        
  # ========== 槽函数（接收播放器信号更新UI） ==========

    def update_play_state(self, state):
        """更新播放状态（来自播放器）"""
        self.is_playing = (state == 'playing')
        self.play_btn.setText("")  # 确保不显示文本，避免与图标叠加
        # 如果有暂停图标则切换，否则保持播放图标
        icon_name = "pause.png" if self.is_playing else "play.png"
        icon_path = os.path.join(os.path.dirname(__file__), "..", "resources", "icons", icon_name)
        if os.path.exists(icon_path):
            self.play_btn.setIcon(QIcon(icon_path))
            self.play_btn.setIconSize(QSize(200, 200))  # 保持播放按钮图标大小

    def update_position(self, position_ms, duration_ms):
       """更新进度条和时间标签"""
       if duration_ms > 0:
           self.progress_slider.setEnabled(True)
           
           # 避免信号循环，暂时断开
           self.progress_slider.blockSignals(True)
           self.progress_slider.setValue(int(position_ms * 100 / duration_ms))
           self.progress_slider.blockSignals(False)
           
           # 更新时间显示
           current_sec = position_ms // 1000
           total_sec = duration_ms // 1000
           self.current_time_label.setText(self._format_time(current_sec))
           self.total_time_label.setText(self._format_time(total_sec))
       else:
           self.progress_slider.setEnabled(False)
           self.current_time_label.setText("00:00")
           self.total_time_label.setText("00:00")
           
    def update_volume(self, volume):
        """更新音量滑块"""
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(volume)
        self.volume_slider.blockSignals(False)
        
# ========== 用户操作转发信号 ==========

    def on_play_pause_clicked(self):
        if self.is_playing:
            # print("Play/Pause button clicked")  # 调试信息
            self.pause_clicked.emit()
        else:
            self.play_clicked.emit()

    def on_prev_clicked(self):
        # print("Previous button clicked")  # 调试信息
        self.prev_clicked.emit()

    def on_next_clicked(self):
        # print("Next button clicked")  # 调试信息
        self.next_clicked.emit()

    def on_volume_changed(self, value):
        self.volume_changed.emit(value)

    def on_progress_moved(self, value):
        """用户拖动进度条"""
        if self.total_time_label.text() != "00:00":
            total_sec = self._parse_time(self.total_time_label.text())
            target_ms = int(value * total_sec * 10)  # value是百分比0-100，total_sec是秒，需转为毫秒
            self.position_changed.emit(target_ms)

    # ========== 辅助函数 ==========

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

    def _parse_time(self, time_str):
        """将格式化的时间字符串解析为秒数"""
        parts = time_str.split(':')
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return 0
    
