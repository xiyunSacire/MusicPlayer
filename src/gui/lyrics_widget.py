# -*- coding: utf-8 -*-
"""
歌词显示组件与专辑封面/频谱可视化整合面板

支持：
- LRC 格式解析与逐行高亮
- 字体大小与高亮颜色自选调节
- 音频元数据专辑封面高保真渲染与默认唱片托底
- 28 频段音频动态频谱可视化 (Spectrum Visualizer)
- 手动获取歌词与本地保存歌词功能
- 现代精致浅色主题
"""
import os
import re
import time
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel,
                             QHBoxLayout, QPushButton, QListWidget,
                             QListWidgetItem, QSpinBox, QColorDialog,
                             QStyledItemDelegate, QStyle, QStyleOptionViewItem,
                             QApplication)
from PyQt5.QtCore import (Qt, pyqtSignal, QRect, QRectF, QPropertyAnimation,
                          QEasingCurve, QTimer, QSize)
from PyQt5.QtGui import (QFont, QColor, QPixmap, QImage, QFontMetrics,
                         QPainter, QPainterPath, QPen, QPalette, QBrush)

from .visualizer import SpectrumVisualizer

# 歌词项上存放翻译文本的自定义数据角色
TRANSLATION_ROLE = Qt.UserRole + 1


class LyricsItemDelegate(QStyledItemDelegate):
    """歌词行绘制：原文一行，若有翻译则在下方用小一号、更淡的字绘制"""

    @staticmethod
    def _fonts(option, index):
        base = QFont(index.data(Qt.FontRole) or option.font)
        translation = QFont(base)
        translation.setBold(False)
        size = base.pointSizeF()
        if size <= 0:
            size = 11.0
        translation.setPointSizeF(max(8.0, size * 0.76))
        return base, translation

    def sizeHint(self, option, index):
        base, translation = self._fonts(option, index)
        # 行高按"非加粗"计算，避免高亮切换时行高变化导致列表跳动
        base.setBold(False)
        height = QFontMetrics(base).height()
        if index.data(TRANSLATION_ROLE):
            height += QFontMetrics(translation).height() + 2
        width = super().sizeHint(option, index).width()
        return QSize(width, height + 10)

    def paint(self, painter, option, index):
        text = str(index.data(Qt.DisplayRole) or "")
        translated = str(index.data(TRANSLATION_ROLE) or "")

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""      # 背景/选中态交给样式画，文字自己排版
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        base, translation_font = self._fonts(option, index)
        color = index.data(Qt.ForegroundRole)
        if isinstance(color, QBrush):
            color = color.color()
        if color is None:
            color = opt.palette.color(QPalette.Text)
        color = QColor(color)

        rect = opt.rect
        fm_main = QFontMetrics(base)
        painter.save()
        painter.setFont(base)
        painter.setPen(color)
        if translated:
            fm_sub = QFontMetrics(translation_font)
            total = fm_main.height() + fm_sub.height() + 2
            top = rect.top() + (rect.height() - total) / 2
        else:
            fm_sub = None
            top = rect.top() + (rect.height() - fm_main.height()) / 2

        painter.drawText(
            QRect(rect.left(), int(top), rect.width(), fm_main.height()),
            Qt.AlignCenter, text
        )

        if translated and fm_sub is not None:
            sub_color = QColor(color)
            sub_color.setAlpha(150)
            painter.setFont(translation_font)
            painter.setPen(sub_color)
            sub_top = top + fm_main.height() + 2
            painter.drawText(
                QRect(rect.left(), int(sub_top), rect.width(), fm_sub.height()),
                Qt.AlignCenter, translated
            )
        painter.restore()


def _render_rounded_cover(img_or_pixmap, size=210, radius=12):
    """生成带圆角与微边框的高保真专辑封面"""
    target = QPixmap(size, size)
    target.fill(Qt.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(path)

    pix = QPixmap.fromImage(img_or_pixmap) if isinstance(img_or_pixmap, QImage) else img_or_pixmap
    scaled = pix.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)

    painter.setClipping(False)
    painter.setPen(QPen(QColor("#cbd5e1"), 1))
    painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), radius, radius)
    painter.end()
    return target


def _render_default_cover(size=210, radius=12):
    """生成优雅现代的默认黑胶唱片质感封面"""
    target = QPixmap(size, size)
    target.fill(Qt.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.Antialiasing)

    # 浅灰底卡片
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.fillPath(path, QColor("#f8fafc"))

    # 唱片外圈
    cx = size / 2.0
    cy = size / 2.0
    disc_r = size * 0.42
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#1e293b"))
    painter.drawEllipse(QRectF(cx - disc_r, cy - disc_r, disc_r * 2, disc_r * 2))

    # 唱片同心反光凹槽
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255, 32), 1))
    for ratio in [0.88, 0.76, 0.64, 0.52]:
        rg = disc_r * ratio
        painter.drawEllipse(QRectF(cx - rg, cy - rg, rg * 2, rg * 2))

    # 唱片粉色中心标贴
    label_r = disc_r * 0.34
    painter.setBrush(QColor("#ec4899"))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QRectF(cx - label_r, cy - label_r, label_r * 2, label_r * 2))

    # 中轴孔
    hole_r = label_r * 0.28
    painter.setBrush(QColor("#f8fafc"))
    painter.drawEllipse(QRectF(cx - hole_r, cy - hole_r, hole_r * 2, hole_r * 2))

    # 卡片外轮廓边框
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor("#e2e8f0"), 1))
    painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), radius, radius)
    painter.end()
    return target


class InteractiveLyricsList(QListWidget):
    """支持感知鼠标滚轮手动翻阅歌词的列表控件"""
    manual_scrolled = pyqtSignal()

    def wheelEvent(self, event):
        self.manual_scrolled.emit()
        super().wheelEvent(event)


class LyricsWidget(QWidget):
    """歌词与专辑封面/频谱一体化组件"""

    # 定义信号
    fetch_lyrics_clicked = pyqtSignal()    # 手动获取歌词按钮点击
    save_lyrics_clicked = pyqtSignal()     # 保存歌词按钮点击
    open_editor_clicked = pyqtSignal()     # 打开歌词制作与微调编辑器
    seek_requested = pyqtSignal(int)       # 点击歌词跳转播放进度（毫秒）
    ai_extract_clicked = pyqtSignal()      # 兼容旧信号
    lyrics_parsed = pyqtSignal(list)       # 歌词解析结果 [(time_ms, text), ...]（供桌面歌词复用）

    def __init__(self, parent=None):
        super().__init__(parent)

        # 歌词数据
        self._lrc_lines = []        # [(time_ms, text, translation), ...]
        self._is_lrc = False        # 是否为标准LRC格式
        self._current_index = -1    # 当前高亮行索引
        self._lyrics_text = None    # 当前已显示的歌词原文（用于 set_lyrics 幂等判断）

        # 手动滚动10秒保护机制
        self._last_user_scroll_time = 0.0   # 上次手动使用滚轮或拖动滚动条的时间戳
        self._recenter_timer = QTimer(self) # 10秒后自动回正定时器
        self._recenter_timer.setSingleShot(True)
        self._recenter_timer.timeout.connect(self._on_recenter_timeout)

        # 外观设置
        self._font_size = 14
        self._highlight_color = QColor("#ec4899")  # 默认柔美淡粉色
        self._normal_color = QColor("#64748b")     # 现代灰色（ Slate 500 ）

        self.setup_ui()

    # ================== UI 构建 ==================

    def setup_ui(self):
        """设置界面"""
        self.setStyleSheet("""
            LyricsWidget {
                background-color: #ffffff;
            }
        """)

        # 主垂直布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ===== 顶部整合导航栏（通栏平铺透明浅蓝渐变背景，无外边距） =====
        header_container = QWidget()
        header_container.setObjectName("lyricsHeader")
        header_container.setStyleSheet("""
            QWidget#lyricsHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(37, 99, 235, 0.12), stop:1 rgba(96, 165, 250, 0.18));
                border-bottom: 1px solid rgba(37, 99, 235, 0.18);
                border-radius: 0px;
            }
        """)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(10)

        # 标题文字（深蓝优雅字色，不加粗，24px）
        header_label = QLabel("歌词")
        font = QFont("Microsoft YaHei UI", 24)
        font.setBold(False)
        header_label.setFont(font)
        header_label.setStyleSheet("color: #1e40af; background: transparent; font-size: 24px; font-weight: normal;")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # 字号微调标签（深蓝雅致字色，21px）
        size_label = QLabel("字号:")
        size_label.setStyleSheet("color: #1e40af; background: transparent; font-size: 21px; font-weight: normal;")
        header_layout.addWidget(size_label)

        self.font_spin = QSpinBox()
        self.font_spin.setRange(9, 36)
        self.font_spin.setValue(self._font_size)
        self.font_spin.setFixedWidth(80)
        self.font_spin.setFixedHeight(36)
        self.font_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid rgba(37, 99, 235, 0.3);
                border-radius: 6px;
                padding: 1px 4px;
                background-color: #ffffff;
                color: #1e293b;
                font-size: 21px;
                font-weight: normal;
            }
            QSpinBox:hover {
                border-color: #2563eb;
            }
            QSpinBox:focus {
                border-color: #2563eb;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 14px;
                border: none;
                background: transparent;
            }
        """)
        self.font_spin.valueChanged.connect(self._on_font_size_changed)
        header_layout.addWidget(self.font_spin)

        # 颜色选择（20px）
        self.color_btn = QPushButton("高亮色")
        self.color_btn.setFixedHeight(36)
        self.color_btn.setToolTip("选择歌词高亮颜色")
        self.color_btn.setCursor(Qt.PointingHandCursor)
        self._update_color_btn_style()
        self.color_btn.clicked.connect(self._on_color_changed)
        header_layout.addWidget(self.color_btn)

        # 手动获取歌词按钮（精致磨砂白底搭配蓝字，20px）
        self.fetch_btn = QPushButton("获取歌词")
        self.fetch_btn.setFixedSize(116, 36)
        self.fetch_btn.setToolTip("从网易云音乐手动获取匹配歌词")
        self.fetch_btn.setCursor(Qt.PointingHandCursor)
        self.fetch_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.85);
                color: #2563eb;
                border: 1px solid rgba(37, 99, 235, 0.25);
                border-radius: 6px;
                font-size: 20px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #eff6ff;
                border-color: #2563eb;
            }
            QPushButton:pressed {
                background-color: #dbeafe;
            }
            QPushButton:disabled {
                background-color: #f1f5f9;
                color: #94a3b8;
                border-color: #e2e8f0;
            }
        """)
        self.fetch_btn.clicked.connect(self._on_fetch_clicked)
        self.ai_btn = self.fetch_btn  # 保持属性兼容
        header_layout.addWidget(self.fetch_btn)

        # 保存歌词按钮（20px，绿色科技胶囊）
        self.save_btn = QPushButton("保存歌词")
        self.save_btn.setFixedSize(116, 36)
        self.save_btn.setToolTip("将当前获取的歌词保存到本地 .lrc 文件")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                border: 1px solid #059669;
                border-radius: 6px;
                font-size: 20px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.save_btn.clicked.connect(self.save_lyrics_clicked.emit)
        self.save_btn.setVisible(False)
        header_layout.addWidget(self.save_btn)

        # 制作/微调歌词按钮（雅致浅粉边框，20px）
        self.edit_btn = QPushButton("制作歌词")
        self.edit_btn.setFixedSize(116, 36)
        self.edit_btn.setToolTip("打开歌词制作与微调工具（可导入TXT打点、添加翻译、微调时间戳）")
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.9);
                color: #be185d;
                border: 1px solid rgba(244, 114, 182, 0.45);
                border-radius: 6px;
                font-size: 20px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #fdf2f8;
                border-color: #ec4899;
                color: #db2777;
            }
            QPushButton:pressed {
                background-color: #fce7f3;
            }
        """)
        self.edit_btn.clicked.connect(self.open_editor_clicked.emit)
        header_layout.addWidget(self.edit_btn)

        main_layout.addWidget(header_container)

        # ===== 主体内容容器：左右分栏（左侧封面与频谱可视化，右侧歌词滚动） =====
        content_container = QWidget()
        content_layout = QHBoxLayout(content_container)
        content_layout.setContentsMargins(16, 12, 16, 12)
        content_layout.setSpacing(20)

        # --- 左侧：歌曲信息 + 专辑封面 + 频谱可视化 ---
        self.visual_panel = QWidget()
        self.visual_panel.setFixedWidth(240)
        self.visual_panel.setStyleSheet("background: transparent;")
        visual_layout = QVBoxLayout(self.visual_panel)
        visual_layout.setContentsMargins(0, 0, 0, 0)
        visual_layout.setSpacing(8)

        # 歌曲标题（单行或双行，17px，不加粗）
        self.title_label = QLabel("未在播放")
        title_font = QFont("Microsoft YaHei UI", 16)
        title_font.setBold(False)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("color: #0f172a; padding: 2px 0; font-weight: normal;")
        visual_layout.addWidget(self.title_label)

        # 艺术家
        self.artist_label = QLabel("未知艺术家")
        artist_font = QFont("Microsoft YaHei UI", 12)
        artist_font.setBold(False)
        self.artist_label.setFont(artist_font)
        self.artist_label.setAlignment(Qt.AlignCenter)
        self.artist_label.setWordWrap(True)
        self.artist_label.setStyleSheet("color: #64748b; padding-bottom: 4px; font-weight: normal;")
        visual_layout.addWidget(self.artist_label)

        # 专辑封面容器
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(210, 210)
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setStyleSheet("background: transparent; border: none;")
        self.cover_label.setPixmap(_render_default_cover(210, 12))
        visual_layout.addWidget(self.cover_label, alignment=Qt.AlignCenter)

        # 音频频谱可视化控件
        self.visualizer = SpectrumVisualizer(self.visual_panel, num_bars=28)
        self.visualizer.setFixedWidth(210)
        self.visualizer.setFixedHeight(65)
        visual_layout.addWidget(self.visualizer, alignment=Qt.AlignCenter)

        visual_layout.addStretch()
        content_layout.addWidget(self.visual_panel)

        # --- 右侧：歌词滚动列表区域 ---
        lyrics_panel = QWidget()
        lyrics_panel_layout = QVBoxLayout(lyrics_panel)
        lyrics_panel_layout.setContentsMargins(0, 0, 0, 0)
        lyrics_panel_layout.setSpacing(0)

        self.lyrics_list = InteractiveLyricsList()
        self.lyrics_list.setItemDelegate(LyricsItemDelegate(self.lyrics_list))
        self.lyrics_list.setFocusPolicy(Qt.NoFocus)
        self.lyrics_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lyrics_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.lyrics_list.viewport().setCursor(Qt.PointingHandCursor)
        self.lyrics_list.itemClicked.connect(self._on_item_clicked)
        self.lyrics_list.manual_scrolled.connect(self._on_user_manual_scrolled)
        self.lyrics_list.verticalScrollBar().sliderMoved.connect(lambda _: self._on_user_manual_scrolled())
        self.lyrics_list.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: transparent;
                outline: none;
            }
            QListWidget::item {
                border: none;
                padding: 7px 6px;
                border-radius: 6px;
            }
            QListWidget::item:hover {
                background-color: #fdf2f8;
                color: #be185d;
            }
            /* 纤细现代滚动条 */
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 2px 0px 2px 0px;
            }
            QScrollBar::handle:vertical {
                background: #e2e8f0;
                border-radius: 3px;
                min-height: 25px;
            }
            QScrollBar::handle:vertical:hover {
                background: #f472b6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        lyrics_panel_layout.addWidget(self.lyrics_list)
        content_layout.addWidget(lyrics_panel, 1)

        main_layout.addWidget(content_container, 1)

    # ================== 事件与槽函数 ==================

    def _on_fetch_clicked(self):
        """点击手动获取歌词"""
        self.fetch_lyrics_clicked.emit()
        self.ai_extract_clicked.emit()

    def set_fetch_loading(self, loading: bool):
        """切换获取按钮加载状态"""
        if loading:
            self.fetch_btn.setEnabled(False)
            self.fetch_btn.setText("获取中...")
        else:
            self.fetch_btn.setEnabled(True)
            self.fetch_btn.setText("获取歌词")

    def show_save_button(self):
        """显示保存歌词按钮"""
        self.save_btn.setVisible(True)

    def hide_save_button(self):
        """隐藏保存歌词按钮"""
        self.save_btn.setVisible(False)

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
                border: 1px solid rgba(255, 255, 255, 0.6);
                border-radius: 6px;
                font-size: 20px;
                font-weight: normal;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)

    def _refresh_all_items_font(self):
        """刷新所有行的字体大小"""
        font = QFont("Microsoft YaHei UI", self._font_size)
        for i in range(self.lyrics_list.count()):
            item = self.lyrics_list.item(i)
            item.setFont(font)
        if self._current_index >= 0:
            self._set_item_highlight(self._current_index, True)

    def _refresh_highlight(self):
        """刷新当前高亮（颜色变化后）"""
        if self._current_index >= 0:
            self._set_item_highlight(self._current_index, True)

    # ================== 歌曲元数据与封面 ==================

    def set_song_info(self, title: str, artist: str):
        """设置当前歌曲信息"""
        self.title_label.setText(title if title else "未知歌曲")
        self.artist_label.setText(artist if artist else "未知艺术家")

    def set_cover(self, cover_bytes):
        """设置专辑封面（支持 bytes、QImage、QPixmap，为 None 时显示默认唱片）"""
        if cover_bytes:
            if isinstance(cover_bytes, (bytes, bytearray)):
                img = QImage()
                if img.loadFromData(cover_bytes):
                    pix = _render_rounded_cover(img, 210, 12)
                    self.cover_label.setPixmap(pix)
                    return
            elif isinstance(cover_bytes, (QImage, QPixmap)):
                pix = _render_rounded_cover(cover_bytes, 210, 12)
                self.cover_label.setPixmap(pix)
                return
        # 默认唱片封面
        self.cover_label.setPixmap(_render_default_cover(210, 12))

    def load_audio(self, file_path: str):
        """传递音频文件给频谱可视化控件进行 PCM 解析"""
        if hasattr(self, 'visualizer'):
            self.visualizer.load_audio(file_path)

    def update_play_state(self, state: str):
        """更新播放状态至频谱组件"""
        if hasattr(self, 'visualizer'):
            self.visualizer.set_playing(state == 'playing')

    # ================== 歌词数据 ==================

    def set_lyrics(self, lyrics: str):
        """解析并显示歌词

        幂等：文本与当前显示完全一致时直接返回，不重建列表。
        重建列表会把 _current_index 重置为 -1 并把滚动条带回顶部，
        因此同一次切曲被重复通知（播放列表索引信号 + 延迟 media_changed）
        曾表现为"歌词闪回第一行"。
        """
        text = lyrics or ""
        if text == getattr(self, '_lyrics_text', None):
            return
        self._lyrics_text = text

        if hasattr(self, '_scroll_anim') and self._scroll_anim:
            self._scroll_anim.stop()
        if hasattr(self, '_recenter_timer'):
            self._recenter_timer.stop()
        self.lyrics_list.clear()
        self._lrc_lines = []
        self._is_lrc = False
        self._current_index = -1
        self._last_user_scroll_time = 0.0

        if not text.strip():
            self._add_plain_item("暂无歌词")
            self.lyrics_parsed.emit([])
            return

        parsed = self._parse_lrc(text)
        if parsed:
            self._lrc_lines = parsed
            self._is_lrc = True
            for time_ms, line, translated in parsed:
                self._add_lrc_item(time_ms, line, translated)
            self.lyrics_parsed.emit(list(parsed))
        else:
            for line in text.strip().splitlines():
                line = line.strip()
                if line:
                    self._add_plain_item(line)
            self.lyrics_parsed.emit([])

    def clear_lyrics(self):
        """清空歌词显示"""
        if hasattr(self, '_scroll_anim') and self._scroll_anim:
            self._scroll_anim.stop()
        if hasattr(self, '_recenter_timer'):
            self._recenter_timer.stop()
        self.title_label.setText("未在播放")
        self.artist_label.setText("从左侧播放列表选择歌曲即可同步显示")
        self.set_cover(None)
        if hasattr(self, 'visualizer'):
            self.visualizer.set_playing(False)
            self.visualizer.set_position(0, 0)
        self.lyrics_list.clear()
        self._lrc_lines = []
        self._is_lrc = False
        self._current_index = -1
        self._lyrics_text = None
        self._last_user_scroll_time = 0.0
        self.save_btn.setVisible(False)
        self.lyrics_parsed.emit([])

    # ================== LRC 解析 ==================

    @staticmethod
    def _parse_lrc(text: str) -> list:
        """解析 LRC 歌词，返回 [(time_ms, line_text, translation), ...]

        双语 LRC 的惯例是：原文与翻译使用**同一个时间戳**，原文在前、翻译在后
        （歌词制作工具就是这么保存的）。因此同一时间戳出现多行时，第一行作原文、
        第二行作翻译，而不是像以前那样直接去重丢弃翻译。
        """
        pattern = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')
        result = []

        for raw_line in text.splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            tags = pattern.findall(raw_line)
            if not tags:
                continue

            last_tag_end = raw_line.rfind(']') + 1
            line_text = raw_line[last_tag_end:].strip()

            for minutes, seconds, millis in tags:
                ms_str = millis.ljust(3, '0')[:3]
                time_ms = int(minutes) * 60000 + int(seconds) * 1000 + int(ms_str)
                result.append((time_ms, line_text))

        if not result:
            return []

        result.sort(key=lambda x: x[0])   # 稳定排序，保留同一时间戳内的先后顺序
        merged = []
        for t, txt in result:
            if merged and merged[-1][0] == t:
                # 同一时间戳的第二行起视为翻译（与原文完全相同则忽略）
                if not merged[-1][2] and txt and txt != merged[-1][1]:
                    merged[-1] = (t, merged[-1][1], txt)
                continue
            merged.append((t, txt, ""))
        return merged

    # ================== 列表辅助 ==================

    def _add_lrc_item(self, time_ms: int, text: str, translation: str = ""):
        """向列表添加一行带有时间戳元数据的歌词项（可带翻译）"""
        item = QListWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        font = QFont("Microsoft YaHei UI", self._font_size)
        item.setFont(font)
        item.setForeground(self._normal_color)
        m = (time_ms // 1000) // 60
        s = (time_ms // 1000) % 60
        tooltip = f"[{m:02d}:{s:02d}] 点击可跳转至该时间点播放"
        if translation:
            item.setData(TRANSLATION_ROLE, translation)
            tooltip += f"\n{translation}"
        item.setToolTip(tooltip)
        item.setData(Qt.UserRole, time_ms)
        self.lyrics_list.addItem(item)

    def _add_plain_item(self, text: str):
        """向列表添加普通无时间戳歌词"""
        item = QListWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        font = QFont("Microsoft YaHei UI", self._font_size)
        item.setFont(font)
        item.setForeground(self._normal_color)
        item.setData(Qt.UserRole, None)
        self.lyrics_list.addItem(item)

    def _on_item_clicked(self, item):
        """用户点击歌词行时，通过时间戳委托播放条逻辑链路跳转"""
        time_ms = item.data(Qt.UserRole)
        if time_ms is not None and isinstance(time_ms, int) and time_ms >= 0:
            # 用户主动点击歌词行：重置手动滚轮保护与自动回正计时器
            self._last_user_scroll_time = 0.0
            if hasattr(self, '_recenter_timer'):
                self._recenter_timer.stop()

            # 1. 立即在UI上高亮所点击的行，并平滑滚动到该行，实现零延迟反馈
            clicked_idx = self.lyrics_list.row(item)
            if clicked_idx >= 0:
                if self._current_index >= 0 and self._current_index != clicked_idx:
                    self._set_item_highlight(self._current_index, False)
                self._current_index = clicked_idx
                self._set_item_highlight(clicked_idx, True)
                self._smooth_scroll_to_index(clicked_idx)

            # 2. 将跳转时间戳直接发射出去，交给播放控制栏链路处理
            #    歌词侧不再自建跳转锁：位置回填只由播放器确认后派发，
            #    确认值必然落在点击的这行附近，高亮不会被 0 脉冲或旧位置覆盖。
            self.seek_requested.emit(time_ms)

    def _on_user_manual_scrolled(self):
        """用户手动使用滚轮或拖拽滚动条查看歌词时触发"""
        # 立即停止当前正在运行的自动平滑滚动动画，交还滚动控制权给用户
        if hasattr(self, '_scroll_anim') and self._scroll_anim and self._scroll_anim.state() == QPropertyAnimation.Running:
            self._scroll_anim.stop()

        self._last_user_scroll_time = time.time()
        if hasattr(self, '_recenter_timer'):
            self._recenter_timer.stop()
            self._recenter_timer.start(10000)  # 至少10秒内不要自动回正

    def _on_recenter_timeout(self):
        """10秒保护时间到期后，平滑回正到当前正在播放的歌词行"""
        self._last_user_scroll_time = 0.0
        if self._current_index >= 0:
            self._smooth_scroll_to_index(self._current_index)

    def _set_item_highlight(self, index: int, active: bool):
        """设置某一行的高亮状态"""
        if index < 0 or index >= self.lyrics_list.count():
            return
        item = self.lyrics_list.item(index)
        font = QFont("Microsoft YaHei UI", self._font_size)
        if active:
            font.setBold(True)
            item.setFont(font)
            item.setForeground(self._highlight_color)
        else:
            font.setBold(False)
            item.setFont(font)
            item.setForeground(self._normal_color)

    # ================== 播放进度同步与平滑滚动 ==================

    def _smooth_scroll_to_index(self, index: int):
        """平滑缓动滚动歌词到指定行居中位置"""
        if index < 0 or index >= self.lyrics_list.count():
            return

        item = self.lyrics_list.item(index)
        item_rect = self.lyrics_list.visualItemRect(item)
        scrollbar = self.lyrics_list.verticalScrollBar()
        current_scroll = scrollbar.value()

        # 计算让当前行垂直居中的滚动差值
        viewport_h = self.lyrics_list.viewport().height()
        item_center_y = item_rect.center().y()
        delta = item_center_y - (viewport_h / 2.0)
        target_scroll = int(current_scroll + delta)
        target_scroll = max(scrollbar.minimum(), min(scrollbar.maximum(), target_scroll))

        if abs(target_scroll - current_scroll) < 2:
            return

        if not hasattr(self, '_scroll_anim') or self._scroll_anim is None:
            self._scroll_anim = QPropertyAnimation(scrollbar, b"value")
            self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._scroll_anim.stop()
        self._scroll_anim.setDuration(350)  # 350毫秒舒适平滑过渡
        self._scroll_anim.setStartValue(current_scroll)
        self._scroll_anim.setEndValue(target_scroll)
        self._scroll_anim.start()

    def update_position(self, position_ms: int, duration_ms: int):
        """根据播放进度更新歌词与频谱可视化控件

        position_ms 已由 MusicPlayer 的跳转状态机确认过，这里不再做任何
        阈值过滤（原先的 seek 锁与 position_ms <= 500 判定已全部移除）。
        """
        if hasattr(self, 'visualizer'):
            self.visualizer.set_position(position_ms, duration_ms)

        if not self._is_lrc or not self._lrc_lines:
            return

        target_index = self._find_current_line(position_ms)
        if target_index == self._current_index:
            return

        if self._current_index >= 0:
            self._set_item_highlight(self._current_index, False)

        self._current_index = target_index

        if target_index >= 0:
            self._set_item_highlight(target_index, True)
            # 手动滚轮滚动保护：10秒内不自动回正滚动条
            if time.time() - getattr(self, '_last_user_scroll_time', 0.0) >= 10.0:
                self._smooth_scroll_to_index(target_index)

    def _find_current_line(self, position_ms: int) -> int:
        """根据时间找到当前应高亮的歌词行索引"""
        idx = -1
        for i, (t, _text, _trans) in enumerate(self._lrc_lines):
            if t <= position_ms:
                idx = i
            else:
                break
        return idx
