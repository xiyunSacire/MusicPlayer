"""
播放列表组件
"""
import os
import json
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QListWidget, 
                             QLabel, QHBoxLayout, QPushButton, QListWidgetItem, 
                             QMenu, QLineEdit)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from src.audio_utils import get_audio_metadata, format_duration

class PlaylistWidget(QWidget):
    """播放列表组件"""
    # 定义信号
    item_double_clicked = pyqtSignal(str)  # 双击时发出文件路径
    clear_requested = pyqtSignal()          # 清空请求
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_paths = []  # 存储完整路径，避免重复
        self.current_playing_item = None  # 当前播放的项（用于高亮）
        self.setup_ui()
    
    def setup_ui(self):
        """设置播放列表界面"""
        # 主布局：0外边距使顶部横梁铺满无缝衔接
        main_layout = QVBoxLayout(self) 
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.setStyleSheet("""
            PlaylistWidget {
                background-color: #ffffff;
            }
        """)
    
        # ===== 顶部标题容器（通栏平铺透明浅蓝渐变背景，无外边距） =====
        header_container = QWidget()
        header_container.setObjectName("playlistHeader")
        header_container.setStyleSheet("""
            QWidget#playlistHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(37, 99, 235, 0.12), stop:1 rgba(96, 165, 250, 0.18));
                border-bottom: 1px solid rgba(37, 99, 235, 0.18);
                border-radius: 0px;
            }
        """)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(10)
        
        # 标题文字（深蓝优雅字色，不加粗，24px）
        title_label = QLabel("播放列表")
        font = QFont("Microsoft YaHei UI", 24)
        font.setBold(False)
        title_label.setFont(font)
        title_label.setStyleSheet("color: #1e40af; background: transparent; font-size: 24px; font-weight: normal;")
        header_layout.addWidget(title_label)
        
        # 歌曲数量徽章（柔和透明蓝背景与深蓝字体，20px）
        self.count_badge = QLabel("0 首")
        self.count_badge.setStyleSheet("""
            QLabel {
                color: #1d4ed8;
                background-color: rgba(37, 99, 235, 0.12);
                border-radius: 14px;
                padding: 2px 10px;
                font-size: 20px;
                font-weight: normal;
                margin-left: 2px;
            }
        """)
        header_layout.addWidget(self.count_badge)
        header_layout.addStretch()
        
        # 清空按钮（精致磨砂白底搭配蓝字，20px）
        clear_btn = QPushButton("清空")
        clear_btn.setFixedSize(76, 36)
        clear_btn.setToolTip("清空播放列表")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.85);
                color: #2563eb;
                border: 1px solid rgba(37, 99, 235, 0.25);
                border-radius: 6px;
                font-size: 20px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #fee2e2;
                color: #ef4444;
                border-color: #fca5a5;
            }
            QPushButton:pressed {
                background-color: #fecaca;
            }
        """)
        clear_btn.clicked.connect(self.on_clear_clicked)
        header_layout.addWidget(clear_btn)   
        
        main_layout.addWidget(header_container)
        
        # 下方内容容器（包含搜索框与列表，保留舒适内容边距）
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(10, 10, 8, 10)
        content_layout.setSpacing(8)
        
        # ===== 搜索功能框（无 emoji 图标） =====
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索歌曲标题、歌手...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setStyleSheet("""
            QLineEdit {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 6px 10px;
                background-color: #f8fafc;
                color: #334155;
                font-size: 13px;
            }
            QLineEdit:hover {
                border-color: #93c5fd;
                background-color: #ffffff;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
                background-color: #ffffff;
            }
        """)
        self.search_box.textChanged.connect(self._on_search_changed)
        content_layout.addWidget(self.search_box)
        
        # ===== 播放列表区域 =====
        self.playlist = QListWidget()
        self.playlist.setFocusPolicy(Qt.NoFocus)
        self.playlist.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.playlist.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # 现代浅粉色交互高亮列表样式
        self.playlist.setStyleSheet(
            """
            QListWidget {
                border: 1px solid #f1f5f9;
                border-radius: 8px;
                padding: 4px;
                background-color: #ffffff;
                outline: none;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 6px;
                margin-bottom: 2px;
                color: #334155;
                border: none;
                font-size: 12px;
            }
            QListWidget::item:hover {
                background-color: #fff1f2;
                color: #be185d;
            }
            QListWidget::item:selected {
                background-color: #fce7f3;
                color: #be185d;
                font-weight: bold;
            }
            /* 纤细滚动条样式 */
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 2px 0px 2px 0px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
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
            """
        )
        self.playlist.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.playlist.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist.customContextMenuRequested.connect(self.show_context_menu)
        content_layout.addWidget(self.playlist)
        main_layout.addWidget(content_container, 1)
    
    def _on_search_changed(self, keyword):
        """搜索歌曲标题、歌手及文件名并即时过滤"""
        keyword = keyword.strip().lower()
        visible_count = 0
        total_count = self.playlist.count()
        keywords = keyword.split() if keyword else []

        for i in range(total_count):
            item = self.playlist.item(i)
            meta = item.data(Qt.UserRole + 1)
            file_path = item.data(Qt.UserRole) or ""

            title = ""
            artist = ""
            if isinstance(meta, dict):
                title = str(meta.get('title', ''))
                artist = str(meta.get('artist', ''))

            filename = os.path.basename(file_path)
            display_text = item.text()

            # 聚合搜索目标：歌曲标题、艺术家、文件名与显示文本
            search_corpus = f"{title} {artist} {filename} {display_text}".lower()

            if not keywords or all(k in search_corpus for k in keywords):
                item.setHidden(False)
                visible_count += 1
            else:
                item.setHidden(True)

        if keyword:
            self.count_badge.setText(f"{visible_count}/{total_count} 首")
        else:
            self.count_badge.setText(f"{total_count} 首")

    def _update_count(self):
        """更新歌曲数量显示并维护当前检索状态"""
        self._on_search_changed(self.search_box.text())

    # ========== 槽函数 ==========
    def on_clear_clicked(self):
        """清空按钮点击"""
        self.clear_requested.emit()    
    
    def on_item_double_clicked(self, item):
        """双击列表项"""
        file_path = item.data(Qt.UserRole)
        if file_path:
            self.item_double_clicked.emit(file_path)    
    
    def show_context_menu(self, pos):
        """右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px 6px 12px;
                border-radius: 4px;
                color: #334155;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #fee2e2;
                color: #ef4444;
            }
        """)
        remove_action = menu.addAction("从列表移除")
        action = menu.exec_(self.playlist.mapToGlobal(pos))
        if action == remove_action:
            current_item = self.playlist.currentItem()
            if current_item:
                file_path = current_item.data(Qt.UserRole)
                if file_path in self.file_paths:
                    self.file_paths.remove(file_path)
                self.playlist.takeItem(self.playlist.row(current_item))
                self._update_count()
    
    def add_files(self, file_paths):
        """添加文件到播放列表（自动去重）"""
        for path in file_paths:
            if path not in self.file_paths:
                self.file_paths.append(path)
                
                # 读取元数据
                meta = get_audio_metadata(path)
                title = meta['title']
                artist = meta['artist']
                duration_str = format_duration(meta['duration'])
                
                # 构建显示文本
                display_text = f"{title} - {artist} [{duration_str}]"
                
                item = QListWidgetItem(display_text)
                item.setToolTip(f"{title}\n歌手: {artist}\n路径: {path}")
                # 存储完整路径到用户角色，方便后续播放
                item.setData(Qt.UserRole, path)  # 完整路径
                item.setData(Qt.UserRole + 1, meta)  # 元数据
                self.playlist.addItem(item)
        self._update_count()
    
    def clear(self):
        """清空播放列表"""
        self.playlist.clear()
        self.file_paths.clear()
        self.search_box.clear()
        self._update_count()
    
    def get_selected_file(self):
        """获取当前选中项的完整路径（供播放功能使用）"""
        current_item = self.playlist.currentItem()
        if current_item:
            return current_item.data(Qt.UserRole)
        return None
    
    def get_all_files(self):
        """获取所有文件的完整路径列表"""
        return self.file_paths.copy()    
    
    def set_current_playing(self, file_path):
        """高亮当前播放的项，并取消上一个的高亮"""
        for i in range(self.playlist.count()):
            item = self.playlist.item(i)
            if item.data(Qt.UserRole) == file_path:
                self.playlist.setCurrentItem(item)
                self.playlist.scrollToItem(item)
                break    
    
    def set_current_index(self, index):
        """根据索引设置当前播放项"""
        if 0 <= index < self.playlist.count():
            item = self.playlist.item(index)
            self.playlist.setCurrentItem(item)
            self.playlist.scrollToItem(item)
