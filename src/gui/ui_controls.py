"""
播放控制面板
"""
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QPushButton, 
                             QSlider, QLabel, QVBoxLayout)
from PyQt5.QtCore import Qt, pyqtSignal

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
        main_layout.setContentsMargins(10, 5, 10, 5)
        
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
        
        # 上一首按钮
        self.prev_btn = QPushButton("◀◀")
        self.prev_btn.setFixedSize(40, 40)
        self.prev_btn.setEnabled(True)  # 启用按钮
        self.prev_btn.clicked.connect(self.on_prev_clicked)  # 连接信号
        controls_layout.addWidget(self.prev_btn)

        # 播放/暂停按钮
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(50, 50)
        self.play_btn.setEnabled(True)  # 启用按钮
        self.play_btn.clicked.connect(self.on_play_pause_clicked)  # 连接信号
        controls_layout.addWidget(self.play_btn)

        # 下一首按钮
        self.next_btn = QPushButton("▶▶")
        self.next_btn.setFixedSize(40, 40)
        self.next_btn.setEnabled(True)  # 启用按钮
        self.next_btn.clicked.connect(self.on_next_clicked)  # 连接信号
        controls_layout.addWidget(self.next_btn)
        
        # 占位空间
        controls_layout.addStretch(1)
        
        # 音量控制
        self.volume_label = QLabel("音量:")
        controls_layout.addWidget(self.volume_label)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setEnabled(True)  # 启用音量控制
        self.volume_slider.valueChanged.connect(self.on_volume_changed)  # 连接信号
        controls_layout.addWidget(self.volume_slider)
        
        main_layout.addLayout(controls_layout)
        
        # 设置固定高度
        self.setFixedHeight(120)
        
  # ========== 槽函数（接收播放器信号更新UI） ==========

    def update_play_state(self, state):
        """更新播放状态（来自播放器）"""
        self.is_playing = (state == 'playing')
        if self.is_playing:
            self.play_btn.setText("⏸")
        else:
            self.play_btn.setText("▶")

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
    
