# -*- coding: utf-8 -*-
"""
歌词显示组件

支持：
- LRC 格式解析与逐行高亮
- 字体大小调节
- 高亮颜色调节
"""
import re
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel,
                             QHBoxLayout, QPushButton, QListWidget,
                             QListWidgetItem, QSpinBox, QColorDialog)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor


class LyricsWidget(QWidget):
    """歌词显示组件"""

    # 定义信号
    ai_extract_clicked = pyqtSignal()      # AI提取按钮点击
    save_lyrics_clicked = pyqtSignal()     # 保存歌词按钮点击

    def __init__(self, parent=None):
        super().__init__(parent)

        # 歌词数据
        self._lrc_lines = []        # [(time_ms, text), ...]
        self._is_lrc = False        # 是否为标准LRC格式
        self._current_index = -1    # 当前高亮行索引

        # 外观设置
        self._font_size = 14
        self._highlight_color = QColor("#6c5ce7")  # 默认紫色
        self._normal_color = QColor("#888888")     # 非高亮行颜色

        self.setup_ui()

    # ================== UI 构建 ==================

    def setup_ui(self):
        """设置歌词显示界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ===== 标题与按钮区域 =====
        header_layout = QHBoxLayout()

        header_label = QLabel("歌词")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        header_label.setFont(font)
        header_label.setStyleSheet("color: #333333; padding: 5px;")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # AI 提取歌词按钮
        self.ai_btn = QPushButton("AI提取歌词")
        self.ai_btn.setFixedSize(90, 28)
        self.ai_btn.setToolTip("使用 AI 提取歌词（开发中）")
        self.ai_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c5ce7;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #5b4bc4;
            }
        """)
        self.ai_btn.clicked.connect(self.ai_extract_clicked.emit)
        header_layout.addWidget(self.ai_btn)

        # 保存歌词按钮（默认隐藏）
        self.save_btn = QPushButton("保存歌词")
        self.save_btn.setFixedSize(80, 28)
        self.save_btn.setToolTip("将当前歌词保存到本地 .lrc 文件")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #00b894;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #00a383;
            }
        """)
        self.save_btn.clicked.connect(self.save_lyrics_clicked.emit)
        self.save_btn.setVisible(False)
        header_layout.addWidget(self.save_btn)

        main_layout.addLayout(header_layout)

        # ===== 工具栏：字号 + 颜色 =====
        toolbar_layout = QHBoxLayout()

        # 字号调节
        toolbar_layout.addWidget(QLabel("字号:"))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 32)
        self.font_spin.setValue(self._font_size)
        self.font_spin.setFixedWidth(50)
        self.font_spin.valueChanged.connect(self._on_font_size_changed)
        toolbar_layout.addWidget(self.font_spin)

        toolbar_layout.addStretch()

        # 颜色选择
        self.color_btn = QPushButton("高亮色")
        self.color_btn.setFixedSize(70, 26)
        self.color_btn.setToolTip("选择歌词高亮颜色")
        self._update_color_btn_style()
        self.color_btn.clicked.connect(self._on_color_changed)
        toolbar_layout.addWidget(self.color_btn)

        main_layout.addLayout(toolbar_layout)

        # ===== 歌曲信息区域 =====
        self.title_label = QLabel("未在播放")
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: #333333; padding: 4px;")
        main_layout.addWidget(self.title_label)

        self.artist_label = QLabel("")
        artist_font = QFont()
        artist_font.setPointSize(10)
        self.artist_label.setFont(artist_font)
        self.artist_label.setAlignment(Qt.AlignCenter)
        self.artist_label.setStyleSheet("color: #666666; padding: 2px;")
        main_layout.addWidget(self.artist_label)

        # ===== 歌词列表区域 =====
        self.lyrics_list = QListWidget()
        self.lyrics_list.setFocusPolicy(Qt.NoFocus)
        self.lyrics_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lyrics_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.lyrics_list.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: transparent;
                outline: none;
            }
            QListWidget::item {
                border: none;
                padding: 6px 4px;
            }
        """)
        main_layout.addWidget(self.lyrics_list, 1)

    # ================== 外观调节 ==================

    def _on_font_size_changed(self, size: int):
        """字号改变"""
        self._font_size = size
        self._refresh_all_items_font()

    def _on_color_changed(self):
        """颜色按钮点击"""
        color = QColorDialog.getColor(self._highlight_color, self, "选择高亮颜色")
        if color.isValid():
            self._highlight_color = color
            self._update_color_btn_style()
            self._refresh_highlight()

    def _update_color_btn_style(self):
        """更新颜色按钮的样式以反映当前颜色"""
        hex_color = self._highlight_color.name()
        self.color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {hex_color};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {hex_color};
                opacity: 0.8;
            }}
        """)

    def _refresh_all_items_font(self):
        """刷新所有行的字体大小"""
        font = QFont()
        font.setPointSize(self._font_size)
        for i in range(self.lyrics_list.count()):
            item = self.lyrics_list.item(i)
            item.setFont(font)
        # 高亮行加粗
        if self._current_index >= 0:
            self._set_item_highlight(self._current_index, True)

    def _refresh_highlight(self):
        """刷新当前高亮（颜色变化后）"""
        if self._current_index >= 0:
            self._set_item_highlight(self._current_index, True)

    # ================== 歌词数据 ==================

    def set_song_info(self, title: str, artist: str):
        """设置当前歌曲信息"""
        self.title_label.setText(title if title else "未知歌曲")
        self.artist_label.setText(artist if artist else "未知歌手")

    def set_lyrics(self, lyrics: str):
        """解析并显示歌词"""
        self.lyrics_list.clear()
        self._lrc_lines = []
        self._is_lrc = False
        self._current_index = -1

        if not lyrics or not lyrics.strip():
            self._add_plain_item("暂无歌词")
            return

        # 尝试解析 LRC
        parsed = self._parse_lrc(lyrics)
        if parsed:
            self._lrc_lines = parsed
            self._is_lrc = True
            for _, text in parsed:
                self._add_plain_item(text)
        else:
            # 纯文本模式
            for line in lyrics.strip().splitlines():
                line = line.strip()
                if line:
                    self._add_plain_item(line)

    def clear_lyrics(self):
        """清空歌词显示"""
        self.title_label.setText("未在播放")
        self.artist_label.setText("")
        self.lyrics_list.clear()
        self._lrc_lines = []
        self._is_lrc = False
        self._current_index = -1
        self.save_btn.setVisible(False)

    def show_save_button(self):
        """显示保存歌词按钮"""
        self.save_btn.setVisible(True)

    def hide_save_button(self):
        """隐藏保存歌词按钮"""
        self.save_btn.setVisible(False)

    # ================== LRC 解析 ==================

    @staticmethod
    def _parse_lrc(text: str) -> list:
        """解析 LRC 歌词，返回 [(time_ms, line_text), ...]

        支持一行多标签，如：[00:15.29][00:16.00]歌词
        """
        pattern = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')
        result = []

        for raw_line in text.splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            # 查找所有时间标签
            tags = pattern.findall(raw_line)
            if not tags:
                continue

            # 标签后的正文
            # 取最后一个标签结束位置之后的字符串
            last_tag_end = raw_line.rfind(']') + 1
            line_text = raw_line[last_tag_end:].strip()

            for minutes, seconds, millis in tags:
                # 毫秒处理：可能是 2 位或 3 位
                ms_str = millis.ljust(3, '0')[:3]
                time_ms = int(minutes) * 60000 + int(seconds) * 1000 + int(ms_str)
                result.append((time_ms, line_text))

        if not result:
            return []

        # 按时间排序并去重
        result.sort(key=lambda x: x[0])
        # 相同时间只保留一条（去重）
        deduped = []
        prev_time = -1
        for t, txt in result:
            if t != prev_time:
                deduped.append((t, txt))
                prev_time = t
        return deduped

    # ================== 列表辅助 ==================

    def _add_plain_item(self, text: str):
        """向列表添加一行歌词"""
        item = QListWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(self._font_size)
        item.setFont(font)
        item.setForeground(self._normal_color)
        self.lyrics_list.addItem(item)

    def _set_item_highlight(self, index: int, active: bool):
        """设置某一行的高亮状态"""
        if index < 0 or index >= self.lyrics_list.count():
            return
        item = self.lyrics_list.item(index)
        font = QFont()
        font.setPointSize(self._font_size)
        if active:
            font.setBold(True)
            item.setFont(font)
            item.setForeground(self._highlight_color)
        else:
            font.setBold(False)
            item.setFont(font)
            item.setForeground(self._normal_color)

    # ================== 播放进度同步 ==================

    def update_position(self, position_ms: int, duration_ms: int):
        """根据播放进度高亮对应歌词行

        Args:
            position_ms: 当前播放位置（毫秒）
            duration_ms: 总时长（毫秒），暂不使用
        """
        if not self._is_lrc or not self._lrc_lines:
            return

        # 二分查找当前应高亮的行
        target_index = self._find_current_line(position_ms)
        if target_index == self._current_index:
            return

        # 取消旧高亮
        if self._current_index >= 0:
            self._set_item_highlight(self._current_index, False)

        self._current_index = target_index

        # 设置新高亮
        if target_index >= 0:
            self._set_item_highlight(target_index, True)
            # 平滑滚动到该行（尽量居中）
            self.lyrics_list.scrollToItem(
                self.lyrics_list.item(target_index),
                QListWidget.PositionAtCenter
            )

    def _find_current_line(self, position_ms: int) -> int:
        """根据时间找到当前应高亮的歌词行索引"""
        # 找到最后一个 time <= position_ms 的行
        idx = -1
        for i, (t, _) in enumerate(self._lrc_lines):
            if t <= position_ms:
                idx = i
            else:
                break
        return idx
