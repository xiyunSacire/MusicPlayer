"""
播放列表组件
"""
import os
import json
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QListWidget, 
                             QLabel, QHBoxLayout, QPushButton, QListWidgetItem, QMenu)
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
    
    # 设置播放列表界面    
    def setup_ui(self):
        """设置播放列表界面"""
        # 主布局
        main_layout = QVBoxLayout(self) 
        main_layout.setContentsMargins(5, 10, 5, 10)  # 设置边距
        main_layout.setSpacing(10)  # 设置组件间距
    
        # ===== 标题区域 =====
        title_layout = QHBoxLayout()
        
        # 标题文字
        title_label = QLabel("播放列表")
        # 设置字体
        font = QFont()
        font.setPointSize(16)  # 字体大小
        font.setBold(True)     # 加粗
        title_label.setFont(font)
        
        # 设置样式
        title_label.setStyleSheet("color: #333333; padding: 5px;")
        
        # 添加占位空间，让标题左对齐
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        # 清空按钮
        clear_btn = QPushButton("清空")
        clear_btn.setFixedSize(50, 30)
        clear_btn.setToolTip("清空播放列表")
        clear_btn.setEnabled(True)  # 启用按钮
        clear_btn.clicked.connect(self.on_clear_clicked)  # 连接清空函数
        title_layout.addWidget(clear_btn)   
        
        main_layout.addLayout(title_layout)
        # ===== 播放列表区域 =====
        self.playlist = QListWidget()
        # 设置列表样式
        self.playlist.setStyleSheet(
            """
            QListWidget {
                border: 1px solid #cccccc;
                border-radius: 5px;
                padding: 5px;
                background-color: white;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eeeeee;
            }
            QListWidget::item:selected {
                background-color: #e0e0e0;
                color: black;
            }
            QListWidget::item:hover {
                background-color: #f0f0f0;
            }
            /* 当前播放项高亮样式 */
            QListWidget::item:!selected:!hover:current {
                background-color: #b0d4f0;
                color: black;
            }
            /* 滚动条样式（可选） */
            QScrollBar:vertical {
                border: none;
                background: #f0f0f0;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #c0c0c0;
                border-radius: 5px;
                min-height: 20px;
            }
            """
        )
        self.playlist.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.playlist.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist.customContextMenuRequested.connect(self.show_context_menu)
        # 添加到布局
        main_layout.addLayout(title_layout)
        main_layout.addWidget(self.playlist)
    
    # ========== 槽函数 ==========
    # 清空按钮点击
    def on_clear_clicked(self):
        """清空按钮点击"""
        self.clear_requested.emit()    
    
    # 双击列表项
    def on_item_double_clicked(self, item):
        """双击列表项"""
        file_path = item.data(Qt.UserRole)
        if file_path:
            self.item_double_clicked.emit(file_path)    
    
    # 右键菜单
    def show_context_menu(self, pos):
        """右键菜单"""
        menu = QMenu()
        remove_action = menu.addAction("从列表移除")
        action = menu.exec_(self.playlist.mapToGlobal(pos))
        if action == remove_action:
            current_item = self.playlist.currentItem()
            if current_item:
                file_path = current_item.data(Qt.UserRole)
                if file_path in self.file_paths:
                    self.file_paths.remove(file_path)
                self.playlist.takeItem(self.playlist.row(current_item))
                # 如果移除的是当前播放项，可能需要通知主窗口（暂不处理）    
    
    # 添加文件到播放列表（自动去重）    
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
                # 存储完整路径到用户角色，方便后续播放
                item.setData(Qt.UserRole, path)  # 完整路径
                item.setData(Qt.UserRole + 1, meta)  # 元数据（可选）
                self.playlist.addItem(item)
    
    # 清空播放列表
    def clear(self):
        """清空播放列表"""
        self.playlist.clear()
        self.file_paths.clear()
    
    # 获取当前选中项的完整路径（供播放功能使用）
    def get_selected_file(self):
        """获取当前选中项的完整路径（供播放功能使用）"""
        current_item = self.playlist.currentItem()
        if current_item:
            return current_item.data(Qt.UserRole)
        return None
    
    # 获取所有文件的完整路径列表
    def get_all_files(self):
        """获取所有文件的完整路径列表"""
        return self.file_paths.copy()    
    
    # 设置当前播放项高亮
    def set_current_playing(self, file_path):
        """高亮当前播放的项，并取消上一个的高亮"""
        # 先取消上一个的高亮（如果需要更复杂的样式，可以在这里处理）
        # QListWidget 默认选中就是高亮，这里主要确保滚动和选中
        for i in range(self.playlist.count()):
            item = self.playlist.item(i)
            if item.data(Qt.UserRole) == file_path:
                self.playlist.setCurrentItem(item)   # 设置当前项（会应用 :current 样式）
                self.playlist.scrollToItem(item)      # 滚动到当前项
                break    
    
    # 根据索引设置当前播放
    def set_current_index(self, index):
        """根据索引设置当前播放项"""
        if 0 <= index < self.playlist.count():
            item = self.playlist.item(index)
            self.playlist.setCurrentItem(item)
            self.playlist.scrollToItem(item)