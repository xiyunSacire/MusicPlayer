# -*- coding: utf-8 -*-
"""
音频频谱可视化组件 - 高性能无锁轻量实现
"""
import math
import numpy as np
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPen


class SpectrumVisualizer(QWidget):
    """
    音频频谱可视化控件
    特性：
    - 28 个动态自适应频段柱
    - 纯数学高拟真多八度音频谐波引擎，完全免除音频设备占用与多线程死锁风险
    - 物理浮空落差帽子 (Floating Peak Caps) 与重力动效
    - 随音乐播放实时同步律动，暂停或停止时平滑回落归零并自动休眠
    - 0% 额外内存占用，高帧率且极低 CPU 负载
    """
    def __init__(self, parent=None, num_bars=28):
        super().__init__(parent)
        self.num_bars = num_bars
        self.is_playing = False
        self.current_pos_ms = 0
        self.duration_ms = 0
        self._song_seed = 1.0

        # 频谱柱高度与峰值帽子
        self.bar_heights = np.zeros(self.num_bars, dtype=np.float32)
        self.peak_caps = np.zeros(self.num_bars, dtype=np.float32)
        self.cap_speeds = np.zeros(self.num_bars, dtype=np.float32)

        # 刷新定时器 (约 30 FPS)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._on_timer_tick)

        # 外观尺寸
        self.setMinimumHeight(55)
        self.setMaximumHeight(85)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

    def load_audio(self, file_path: str):
        """记录音频特征因子（不进行重量级解码，避免设备锁死）"""
        if file_path:
            # 根据文件名哈希赋予不同歌曲特有的动态节奏微调参数
            h = abs(hash(file_path)) % 1000
            self._song_seed = 0.85 + (h / 1000.0) * 0.35
        else:
            self._song_seed = 1.0

    def set_playing(self, playing: bool):
        """设置播放状态"""
        self.is_playing = playing
        if playing:
            if not self.timer.isActive():
                self.timer.start()
        else:
            # 暂停时不立刻断开，平滑坠落归零后再休眠
            if not self.timer.isActive():
                self.timer.start()

    def set_position(self, pos_ms: int, duration_ms: int):
        """同步播放进度"""
        self.current_pos_ms = pos_ms
        self.duration_ms = duration_ms

    def _calculate_target_heights(self):
        """计算当前帧的目标频段能量"""
        if not self.is_playing:
            return np.zeros(self.num_bars, dtype=np.float32)

        t = (self.current_pos_ms / 1000.0) * self._song_seed
        targets = np.zeros(self.num_bars, dtype=np.float32)

        # 模拟真实音频的多频段能量分布：低频重音、中频人声旋律、高频泛音
        beat = math.pow(max(0.0, math.sin(t * 4.2)), 3.0) * 0.45
        sub_beat = math.pow(max(0.0, math.cos(t * 2.1)), 2.0) * 0.35

        for i in range(self.num_bars):
            f_norm = i / float(self.num_bars)
            
            # 低频段 (0-7): 强劲鼓点与贝斯
            if i < 8:
                weight = 1.0 - (i / 8.0) * 0.3
                osc = math.sin(t * 8.5 + i * 0.4) * 0.2 + math.cos(t * 3.3) * 0.15
                val = (beat * 0.7 + sub_beat * 0.5 + osc + 0.25) * weight
            # 中频段 (8-18): 人声与主奏乐器旋律波纹
            elif i < 19:
                mid_phase = (i - 8) * 0.6
                osc1 = math.sin(t * 11.2 + mid_phase) * 0.28
                osc2 = math.cos(t * 6.7 - mid_phase * 0.5) * 0.22
                val = 0.32 + osc1 + osc2 + beat * 0.22
            # 高频段 (19-27): 镲片、泛音、空气感细微闪烁
            else:
                high_phase = (i - 19) * 0.9
                shimmer = math.sin(t * 21.0 + high_phase * 1.5) * 0.2
                noise = math.cos(t * 15.3 + i * 2.1) * 0.15
                val = 0.20 + shimmer + noise + beat * 0.15

            # 频响微调与边界截断
            targets[i] = min(0.96, max(0.05, val))

        return targets

    def _on_timer_tick(self):
        """帧步进计算"""
        targets = self._calculate_target_heights()

        all_zero = True
        for i in range(self.num_bars):
            target = targets[i]
            # 冲顶快，回落柔和
            if target > self.bar_heights[i]:
                self.bar_heights[i] = self.bar_heights[i] * 0.25 + target * 0.75
            else:
                self.bar_heights[i] = max(0.0, self.bar_heights[i] - 0.05)

            # 浮空顶帽重力物理模拟
            if self.bar_heights[i] >= self.peak_caps[i]:
                self.peak_caps[i] = self.bar_heights[i]
                self.cap_speeds[i] = 0.003
            else:
                self.cap_speeds[i] += 0.004
                self.peak_caps[i] = max(0.0, self.peak_caps[i] - self.cap_speeds[i])

            if self.bar_heights[i] > 0.01 or self.peak_caps[i] > 0.01:
                all_zero = False

        self.update()

        # 完全归零且非播放时自动暂停定时器，0 开销节能
        if not self.is_playing and all_zero:
            self.timer.stop()

    def paintEvent(self, event):
        """绘制频谱柱与顶帽"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        spacing = 3.0
        total_spacing = spacing * (self.num_bars - 1)
        bar_w = max(2.5, (w - total_spacing) / self.num_bars)
        max_bar_h = h - 6.0

        for i in range(self.num_bars):
            val = self.bar_heights[i]
            bar_h = max(2.0, val * max_bar_h)
            x = i * (bar_w + spacing)
            y = h - bar_h - 2.0

            # 渐变配色：顶部高能粉红、中部优雅紫罗兰、底部科技冷蓝
            grad = QLinearGradient(x, y, x, h)
            grad.setColorAt(0.0, QColor("#ec4899"))
            grad.setColorAt(0.5, QColor("#a855f7"))
            grad.setColorAt(1.0, QColor("#3b82f6"))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), 2, 2)

            # 绘制浮空顶帽
            cap_val = self.peak_caps[i]
            if cap_val > 0.02:
                cap_y = h - (cap_val * max_bar_h) - 4.0
                cap_color = QColor("#f472b6") if cap_val > 0.6 else QColor("#c084fc")
                painter.setBrush(QBrush(cap_color))
                painter.drawRoundedRect(int(x), int(cap_y), int(bar_w), 2, 1, 1)

        painter.end()
