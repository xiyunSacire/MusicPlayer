# -*- coding: utf-8 -*-
"""
主窗口模块 - 基础窗口框架
"""
import os
import json
import sys
from src.player import MusicPlayer
from src.audio_utils import get_audio_metadata
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QStatusBar, QSplitter,
                             QLabel)  # 添加 QLabel 导入
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QMediaPlaylist
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtGui import QKeySequence

# 支持的音频格式扩展名（可根据需要增减）
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.ape', '.opus'}

# 导入其他UI组件（实现中）
try:
    from .ui_widget import PlaylistWidget
    from .ui_controls import PlayerControls
except ImportError:
    # 定义空类作为占位符
    class PlaylistWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumWidth(300)
    
    class PlayerControls(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumHeight(80)

class MainWindow(QMainWindow):
    """主窗口类"""
    
    # 信号定义
    app_quit = pyqtSignal()
    settings_changed = pyqtSignal(dict)
    # 构造(初始化)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("音乐播放器")
        
        # 初始化属性
        self.last_folder = ""
        self.config = {}
        self.config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config.json"
        )
        # 加载配置，设置 self.last_folder
        self.load_config()               
        
        # 创建播放列表组件
        self.setup_ui()                  
        self.setup_menus()
        
        # 先创建状态栏，使 status_label 可用
        self.setup_statusbar()            
        
        # 创建播放器实例
        self.player = MusicPlayer()
        self._connect_player_signals()
        
        # 应用初始音量设置
        if hasattr(self, '_init_volume'):
            self.player.set_volume(self._init_volume)
        
        # 连接UI组件的信号
        self._connect_ui_signals()
        
        # 自动加载上次文件夹的音乐
        self._load_last_folder_music()    


# 设置主界面布局        
    def setup_ui(self):
        """设置主界面布局"""
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建水平分割器
        self.splitter = QSplitter(Qt.Horizontal)
        
        # 左侧：播放列表（占1/5）
        self.playlist_widget = PlaylistWidget()
        self.splitter.addWidget(self.playlist_widget)
        
        # 右侧：暂时留空（未来可能放专辑封面等）
        self.right_panel = QWidget()
        self.right_panel.setMinimumWidth(400)
        self.splitter.addWidget(self.right_panel)
        
        # 给右侧面板添加一些临时内容，方便看到比例效果
        right_layout = QVBoxLayout(self.right_panel)
        right_label = QLabel("内容区域")
        right_label.setAlignment(Qt.AlignCenter)
        right_label.setStyleSheet("font-size: 20px; color: gray;")
        right_layout.addWidget(right_label)

        
        # 设置分割器初始比例（左:右 = 1:4）
        # 计算方式：总宽度800，左占1/5 = 160，右占4/5 = 640
        total_width = self.width()  # 获取当前窗口宽度
        left_width = int(total_width * 0.2)  # 20% = 1/5
        right_width = total_width - left_width
        
        self.splitter.setSizes([left_width, right_width])
        
        # 底部：控制面板
        self.controls = PlayerControls()
        
        # 添加到主布局
        main_layout.addWidget(self.splitter, 1)  # 1表示可伸缩
        main_layout.addWidget(self.controls, 0)  # 0表示固定高度

# 创建菜单栏        
    def setup_menus(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        
        # 添加文件动作
        self.open_file_action = file_menu.addAction("打开文件(&O)...")
        self.open_file_action.setShortcut(QKeySequence.Open)
        self.open_file_action.triggered.connect(self.on_open_file)
        
        self.open_folder_action = file_menu.addAction("打开文件夹(&D)...")
        self.open_folder_action.triggered.connect(self.on_open_folder)
        
        self.clear_playlist_action = file_menu.addAction("清空播放列表")
        self.clear_playlist_action.triggered.connect(self.on_clear_playlist)
        
        file_menu.addSeparator()
        
        self.exit_action = file_menu.addAction("退出(&X)")
        self.exit_action.setShortcut(QKeySequence.Quit)
        self.exit_action.triggered.connect(self.close)
        
        # 播放菜单
        play_menu = menubar.addMenu("播放(&P)")
        
        self.play_action = play_menu.addAction("播放/暂停(&P)")
        self.play_action.setShortcut(QKeySequence("Space"))
        self.play_action.triggered.connect(self.on_play_pause)
        
        self.prev_action = play_menu.addAction("上一首(&B)")
        self.prev_action.setShortcut(QKeySequence("Ctrl+Left"))
        self.prev_action.triggered.connect(self.on_prev)
        
        self.next_action = play_menu.addAction("下一首(&N)")
        self.next_action.setShortcut(QKeySequence("Ctrl+Right"))
        self.next_action.triggered.connect(self.on_next)
        
        play_menu.addSeparator()
        
        self.shuffle_action = play_menu.addAction("随机播放(&S)")
        self.shuffle_action.setCheckable(True)
        self.shuffle_action.toggled.connect(self.on_shuffle_toggled)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        
        self.about_action = help_menu.addAction("关于(&A)...")
        self.about_action.triggered.connect(self.on_about)
 
# 设置状态栏       
    def setup_statusbar(self):
        """设置状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # 状态标签
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label, 1)  # 1表示可伸缩
        
        # 播放状态标签
        self.play_status_label = QLabel("停止")
        self.status_bar.addPermanentWidget(self.play_status_label)
        
        # 时间标签
        self.time_label = QLabel("00:00 / 00:00")
        self.status_bar.addPermanentWidget(self.time_label)

# 打开文件回调
    def on_open_file(self):
        """打开文件回调"""
        # 获取上次打开的路径（可选），这里简单用空字符串
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择音频文件",
            "",  # 起始目录，可优化为记住上次路径
            f"音频文件 ({' '.join('*' + ext for ext in AUDIO_EXTENSIONS)});;所有文件 (*.*)"
        )
        if file_paths:
            # 过滤（理论上对话框已过滤，但确保）
            audio_files = [f for f in file_paths if self.is_audio_file(f)]
            if audio_files:
                self.playlist_widget.add_files(audio_files)
                # 更新 last_folder 为第一个文件所在目录
                self.last_folder = os.path.dirname(audio_files[0])
                self.save_config()
                self.status_label.setText(f"已添加 {len(audio_files)} 个文件")
            else:
                QMessageBox.information(self, "提示", "没有选择有效的音频文件")

# 打开文件夹回调  
    def on_open_folder(self):
        """打开文件夹回调"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择音乐文件夹",
            self.last_folder  # 使用上次路径
        )
        if folder:
            # 递归遍历文件夹收集所有音频文件
            audio_files = []
            for root, dirs, files in os.walk(folder):
                for file in files:
                    if self.is_audio_file(file):
                        full_path = os.path.join(root, file)
                        audio_files.append(full_path)

            if audio_files:
                self.playlist_widget.add_files(audio_files)
                self.last_folder = folder
                self.save_config()
                self.status_label.setText(f"已从文件夹添加 {len(audio_files)} 个文件")
            else:
                QMessageBox.information(self, "提示", "该文件夹中没有找到音频文件")

# 清空播放列表回调
    def on_clear_playlist(self):
        """清空播放列表"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空播放列表吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.playlist_widget.clear()
            # 同时清空播放器的列表
            self.player.clear_playlist()  
            self.status_label.setText("播放列表已清空")
            # 停止播放
            self.player.stop()              
            
# 播放/暂停回调      
    def on_play_pause(self):
        """播放/暂停回调"""
        if self.player.is_playing():
            self.player.pause()
            self.status_label.setText("已暂停")
        else:
            self.player.play()
            self.status_label.setText("正在播放")

# 上一首回调        
    def on_prev(self):
        """上一首回调"""
        self.player.previous()
        # player 会通过延迟的 media_changed 信号自动更新状态栏

# 下一首回调        
    def on_next(self):
        """下一首回调"""
        self.player.next()
        # player 会通过延迟的 media_changed 信号自动更新状态栏

# 随机播放切换回调          
    def on_shuffle_toggled(self, checked):
        """随机播放切换回调"""
        self.player.set_shuffle(checked)
        status = "开启" if checked else "关闭"
        self.status_label.setText(f"随机播放已{status}")
  
# 关于对话框（待实现） 
    def on_about(self):
        """关于对话框（待实现）"""
        QMessageBox.about(self, "关于", "音乐播放器 v0.1.0\n\n这是一个简单的音乐播放器")

# 窗口关闭事件
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 保存窗口配置
        self.save_config()
        # 发送退出信号
        self.app_quit.emit()
        # 接受关闭事件
        event.accept()

# 检查文件是否为音频（供打开文件功能使用）            
    def is_audio_file(self, filename):
        """检查文件是否为音频"""
        ext = os.path.splitext(filename)[1].lower()
        return ext in AUDIO_EXTENSIONS

# 加载配置文件并应用设置                
    def load_config(self):
        """加载所有配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = {}
        except Exception as e:
            print(f"加载配置失败: {e}")
            self.config = {}

        # 应用窗口配置
        window_config = self.config.get('window', {})
        self.resize(window_config.get('width', 800), window_config.get('height', 600))
        if window_config.get('maximized'):
            self.showMaximized()
        else:
            x = window_config.get('x')
            y = window_config.get('y')
            if x is not None and y is not None:
                self.move(x, y)

        # 记住上次打开的文件夹
        self.last_folder = self.config.get('playlist', {}).get('last_folder', '')
        
        # 应用播放器配置（如音量）
        volume = self.config.get('player', {}).get('volume', 70)
        if hasattr(self, 'player'):
            self.player.set_volume(volume)
        else:
            # 暂时保存，等 player 创建后再设置（可以在创建后调用）
            self._init_volume = volume

# 启动时自动加载上次文件夹中的音乐
    def _load_last_folder_music(self):
        """启动时自动加载上次文件夹中的音乐"""
        if self.last_folder and os.path.exists(self.last_folder):
            # 复用文件夹扫描逻辑，但不弹出对话框
            audio_files = []
            for root, dirs, files in os.walk(self.last_folder):
                for file in files:
                    if self.is_audio_file(file):
                        audio_files.append(os.path.join(root, file))
            if audio_files:
                self.playlist_widget.add_files(audio_files)
                self.status_label.setText(f"已自动加载 {len(audio_files)} 个文件")
        else:
            # 可选：提示上次文件夹无效，但不强制
            print(f"上次文件夹不存在: {self.last_folder}")

# 保存配置文件
    def save_config(self):
        """保存所有配置"""
        # 更新窗口配置
        if 'window' not in self.config:
            self.config['window'] = {}
        self.config['window'].update({
            'width': self.width(),
            'height': self.height(),
            'maximized': self.isMaximized(),
            'x': self.x() if not self.isMaximized() else None,
            'y': self.y() if not self.isMaximized() else None
        })

        # 确保 playlist 部分存在
        if 'playlist' not in self.config:
            self.config['playlist'] = {}
        self.config['playlist']['last_folder'] = self.last_folder
        
        # 确保 player 部分存在，并保存音量等设置
        if 'player' not in self.config:
            self.config['player'] = {}
        self.config['player']['volume'] = self.player.volume() if hasattr(self, 'player') else 70

        # 写入文件
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置失败: {e}")

# 连接播放器的信号到UI
    def _connect_player_signals(self):
        """连接播放器的信号到UI"""
        self.player.position_changed.connect(self.controls.update_position)
        self.player.state_changed.connect(self.controls.update_play_state)
        self.player.volume_changed.connect(self.controls.update_volume)
        self.player.media_changed.connect(self.on_media_changed)
        self.player.error_occurred.connect(lambda err: self.status_label.setText(f"错误: {err}"))
        self.player.playlist_current_index_changed.connect(self.on_playlist_index_changed)
        self.player.playlist_current_index_changed.connect(self.on_player_index_changed)

# 连接UI组件的信号到播放器
    def _connect_ui_signals(self):
        """连接UI组件的信号到播放器"""
        # 控制面板
        self.controls.play_clicked.connect(self.player.play) # 连接播放按钮信号到播放器播放方法
        self.controls.pause_clicked.connect(self.player.pause) # 连接暂停按钮信号到播放器暂停方法
        self.controls.next_clicked.connect(self.player.next) # 连接下一首按钮信号到播放器下一首方法
        self.controls.prev_clicked.connect(self.player.previous) # 连接上一首按钮信号到播放器上一首方法
        self.controls.volume_changed.connect(self.player.set_volume) # 连接音量改变信号到播放器设置音量方法
        self.controls.position_changed.connect(self.player.set_position) # 连接进度条位置改变信号到播放器设置位置方法
        
        # 播放列表
        self.player.media_changed.connect(self.update_status_info) # 每次媒体变化时更新状态栏信息
        self.player.error_occurred.connect(lambda err: self.status_label.setText(f"错误: {err}")) # 错误信息显示
        self.player.playlist_current_index_changed.connect(self.on_player_index_changed) # 同步UI选中状态
        self.playlist_widget.item_double_clicked.connect(self.on_playlist_double_clicked) # 双击播放事件
        self.playlist_widget.clear_requested.connect(self.on_clear_playlist) # 连接清空播放列表信号

        # 清空菜单已经连接了 on_clear_playlist，但还需要清空播放器列表
        # 可以在 on_clear_playlist 中调用 player.clear_playlist() (已调用)    

# 播放列表双击事件：加载并播放该文件
    def on_playlist_double_clicked(self, file_path):
        """播放列表双击事件：加载并播放该文件"""
        self.player.clear_playlist()
        all_files = self.playlist_widget.get_all_files()
        
        if not all_files: # 防御性编程
            return
            
        for file in all_files:
            self.player.add_file(file)
            
        try:
            index = all_files.index(file_path)
            self.player.playlist.setCurrentIndex(index)
            self.player.play()
            self.update_status_info()
            # 注意：这里不再需要手动 set_current_playing，
            # 因为 setCurrentIndex 会触发上面的 on_playlist_index_changed 信号自动同步
        except ValueError:
            print("文件不在列表中")

# 媒体变化事件：更新状态栏等信息
    def on_media_changed(self, metadata):
        """当前媒体变化时更新状态栏等信息"""
        title = metadata.get('title', '未知')
        artist = metadata.get('artist', '未知')
        self.status_label.setText(f"正在播放: {title} - {artist}")
        # 可以设置窗口标题等
        self.setWindowTitle(f"{title} - 音乐播放器")

# 播放列表索引变化事件：同步UI选中状态
    def on_playlist_index_changed(self, index):
        """当播放器内部索引改变时（如切歌），同步UI"""
        if index >= 0 and self.playlist_widget.playlist.count() > 0:
            # 1. 同步播放列表选中状态
            self.playlist_widget.set_current_index(index)
            
            # 2. 获取当前文件路径，触发元数据更新
            # 这会触发 player 的 media_changed 信号，进而更新左下角信息
            current_file = self.playlist_widget.get_selected_file()
            if current_file:
                # 这里可以触发重新加载元数据，或者如果你有缓存机制更好
                # 简单做法：直接调用 player 的方法（如果 player 有缓存逻辑）
                # 或者直接在这里更新状态栏
                meta = get_audio_metadata(current_file)
                self.on_media_changed(meta) # 强制更新状态栏信息

# 根据文件路径设置当前播放项
    def update_status_info(self):
        """获取当前播放文件的元数据并更新状态栏"""
        # 1. 获取播放器当前播放的文件路径
        current_path = self.player.get_current_media_path()
        
        if current_path and os.path.exists(current_path):
            # 2. 读取元数据
            meta = get_audio_metadata(current_path)
            title = meta['title']
            artist = meta['artist']
            
            # 3. 更新状态栏
            self.status_label.setText(f"正在播放: {title} - {artist}")
            # 可选：更新窗口标题
            self.setWindowTitle(f"{title} - 音乐播放器")
        else:
            # 文件不存在或未播放
            self.status_label.setText("就绪")

# 播放器索引变化事件：同步UI选中状态
    def on_player_index_changed(self, index):
        """播放器切歌（上一首/下一首）时触发"""
        # 只负责同步播放列表的选中状态
        # 状态栏的更新由 media_changed 信号处理（已使用延迟机制）
        if index >= 0:
            self.playlist_widget.set_current_index(index)
        else:
            self.status_label.setText("就绪")
        















