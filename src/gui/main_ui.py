# -*- coding: utf-8 -*-
"""
主窗口模块 - 基础窗口框架
"""
import os
import json
import sys
import time
from src.player import MusicPlayer
from src.audio_utils import get_audio_metadata, get_audio_cover_bytes
from src import lyrics_service
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QStatusBar, QSplitter,
                             QLabel)  # 添加 QLabel 导入
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QMediaPlaylist
from PyQt5.QtCore import Qt, QEvent, pyqtSignal, QTimer
from PyQt5.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtGui import QKeySequence

# 支持的音频格式扩展名（可根据需要增减）
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.ape', '.opus'}

# 导入其他UI组件（实现中）
try:
    from .ui_widget import PlaylistWidget
    from .ui_controls import PlayerControls
    from .lyrics_widget import LyricsWidget
    from .lyrics_editor import LyricsEditorDialog
    from .desktop_lyrics import DesktopLyricsWindow
except ImportError:
    # 保留占位类以便窗口仍能构建，但必须把真实原因打印出来。
    # 静默吞掉 ImportError 会让整个界面悄悄退化成空面板，且无从排查。
    import traceback
    traceback.print_exc()
    print("[警告] UI 组件导入失败，已退化为占位控件，请检查上面的 ImportError 堆栈。")

    # 定义空类作为占位符
    class PlaylistWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumWidth(300)
    
    class PlayerControls(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumHeight(80)

    class LyricsWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumWidth(400)

    class LyricsEditorDialog(QWidget):
        pass

    class DesktopLyricsWindow(QWidget):
        pass

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
        self._retired_fetch_threads = []   # 已取消但仍在退出的歌词线程（保引用防回收）
        # 界面事件追踪（排查"最小化很久后卡死"这类无法稳定复现的问题，默认关闭）
        self._trace_enabled = os.environ.get('MP_UI_DEBUG', '0') != '0'
        self._trace_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'debug')
        self._trace_path = os.path.join(self._trace_dir, 'ui_trace.log')
        if self._trace_enabled:
            try:
                os.makedirs(self._trace_dir, exist_ok=True)
                with open(self._trace_path, 'w', encoding='utf-8') as f:
                    f.write("=== 本次运行 %s ===\n" % time.strftime('%Y-%m-%d %H:%M:%S'))
            except Exception:
                self._trace_enabled = False
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
        
        # 应用初始音量与播放模式设置
        if hasattr(self, '_init_volume'):
            self.player.set_volume(self._init_volume)
        if hasattr(self, '_init_playback_mode'):
            self.player.set_playback_mode(self._init_playback_mode)
            self.controls.set_playback_mode(self._init_playback_mode)
        
        # 连接UI组件的信号
        self._connect_ui_signals()
        
        # 恢复桌面歌词（窗口按需创建）
        self._restore_desktop_lyrics()
        
        # 自动加载上次文件夹的音乐
        self._load_last_folder_music()

        # 可选的心跳日志：记录界面线程是否卡顿（仅在 MP_UI_DEBUG=1 时启用）
        if getattr(self, '_trace_enabled', False):
            self._last_heartbeat = time.time()
            self._heartbeat_timer = QTimer(self)
            self._heartbeat_timer.setInterval(5000)
            self._heartbeat_timer.timeout.connect(self._on_heartbeat)
            self._heartbeat_timer.start()

    def _on_heartbeat(self):
        """每 5 秒记录一次界面线程存活状态；若上一条距现在明显超时，说明界面刚卡住过"""
        now = time.time()
        gap = now - getattr(self, '_last_heartbeat', now)
        self._last_heartbeat = now
        if gap > 8.0:
            self._trace("界面停顿 %.1f 秒后恢复（最小化=%s）" % (gap, self.isMinimized()))
        else:
            state = self.player.state() if hasattr(self, 'player') else 'n/a'
            self._trace("心跳 最小化=%s 状态=%s" % (self.isMinimized(), state))


# 设置主界面布局        
    def setup_ui(self):
        """设置主界面布局"""
        # 全局现代浅色主题样式（浅粉色交互强调）
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8fafc;
            }
            QWidget {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei UI", sans-serif;
            }
            QMenuBar {
                background-color: #ffffff;
                color: #334155;
                border-bottom: 1px solid #e2e8f0;
                padding: 4px 10px;
                font-size: 19px;
                font-weight: normal;
            }
            QMenuBar::item {
                background: transparent;
                padding: 6px 14px;
                border-radius: 6px;
                color: #334155;
                font-size: 19px;
                font-weight: normal;
            }
            QMenuBar::item:selected {
                background-color: #fdf2f8;
                color: #be185d;
            }
            QMenuBar::item:pressed {
                background-color: #fce7f3;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid #fbcfe8;
                border-radius: 8px;
                padding: 6px;
                font-size: 18px;
                font-weight: normal;
            }
            QMenu::item {
                padding: 8px 24px 8px 14px;
                border-radius: 6px;
                color: #334155;
                font-size: 18px;
                font-weight: normal;
            }
            QMenu::item:selected {
                background-color: #fdf2f8;
                color: #db2777;
            }
            QMenu::separator {
                height: 1px;
                background-color: #f1f5f9;
                margin: 4px 6px;
            }
            QSplitter::handle:horizontal {
                background-color: #e2e8f0;
                width: 1px;
            }
            QSplitter::handle:horizontal:hover {
                background-color: #f472b6;
            }
            QSplitter::handle:vertical {
                background-color: #e2e8f0;
                height: 2px;
            }
            QSplitter::handle:vertical:hover {
                background-color: #f472b6;
            }
            QStatusBar {
                background-color: #ffffff;
                border-top: 1px solid #e2e8f0;
                color: #64748b;
                font-size: 12px;
                padding: 2px 10px;
            }
            QStatusBar::item {
                border: none;
            }
            QToolTip {
                background-color: #1e293b;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QMessageBox {
                background-color: #ffffff;
            }
            QMessageBox QPushButton {
                background-color: #f8fafc;
                color: #334155;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 500;
                min-width: 60px;
            }
            QMessageBox QPushButton:hover {
                background-color: #ec4899;
                color: #ffffff;
                border-color: #ec4899;
            }
        """)

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建垂直分割器（上层主视窗 vs 底部播放控制栏，支持上下拖拽调节高度）
        self.v_splitter = QSplitter(Qt.Vertical)
        self.v_splitter.setHandleWidth(2)

        # 创建水平分割器（左侧播放列表 vs 右侧歌词展示区）
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        
        # 左侧：播放列表（占1/5）
        self.playlist_widget = PlaylistWidget()
        self.splitter.addWidget(self.playlist_widget)
        
        # 右侧：歌词显示区域
        self.lyrics_widget = LyricsWidget()
        self.lyrics_widget.setMinimumWidth(400)
        self.splitter.addWidget(self.lyrics_widget)

        # 设置水平分割器初始比例（左:右 = 1:4）
        total_width = self.width()
        left_width = int(total_width * 0.2)
        right_width = total_width - left_width
        self.splitter.setSizes([left_width, right_width])
        
        # 底部：控制面板
        self.controls = PlayerControls()
        
        # 组装到垂直分割器
        self.v_splitter.addWidget(self.splitter)
        self.v_splitter.addWidget(self.controls)
        
        # 设置垂直分割器尺寸（上层区域自适应，控制面板恢复上次高度）
        controls_h = getattr(self, '_init_controls_height', 110)
        upper_h = max(200, self.height() - controls_h)
        self.v_splitter.setSizes([upper_h, controls_h])
        self.v_splitter.setStretchFactor(0, 1)  # 上部优先拉伸
        self.v_splitter.setStretchFactor(1, 0)  # 底部固定相对高度
        
        # 添加到主布局
        main_layout.addWidget(self.v_splitter)

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
        
        self.editor_action = play_menu.addAction("制作/微调歌词(&L)...")
        self.editor_action.setShortcut(QKeySequence("Ctrl+L"))
        self.editor_action.triggered.connect(self.on_open_lyrics_editor)

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
        self.status_label.setStyleSheet("background-color: #ffffff; color: #334155; font-size: 12px; font-weight: 500; padding-left: 4px;")
        self.status_bar.addWidget(self.status_label, 1)  # 1表示可伸缩
        
        # 歌词获取状态（网络搜索进度与结果，紧靠在播放状态徽章左侧）
        self.lyrics_status_label = QLabel("")
        self.lyrics_status_label.setVisible(False)
        self._set_lyrics_status("", "idle")
        self.status_bar.addPermanentWidget(self.lyrics_status_label)

        # 播放状态标签（精致小徽章）
        self.play_status_label = QLabel("停止")
        self._update_play_status_badge("停止")
        self.status_bar.addPermanentWidget(self.play_status_label)
        
        # 时间标签
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #64748b; font-size: 12px; font-family: 'Segoe UI', 'Consolas', sans-serif; font-weight: 500; padding-right: 4px;")
        self.status_bar.addPermanentWidget(self.time_label)

    def _set_lyrics_status(self, text, state="idle"):
        """更新"歌词获取"状态显示

        state: busy（搜索中）/ ok（获取成功）/ fail（失败）/ idle（空闲）
        """
        label = getattr(self, 'lyrics_status_label', None)
        if label is None:
            return
        palette = {
            "busy": ("#eff6ff", "#2563eb", "#bfdbfe"),
            "ok": ("#ecfdf5", "#047857", "#a7f3d0"),
            "fail": ("#fef2f2", "#b91c1c", "#fecaca"),
            "idle": ("#f1f5f9", "#64748b", "#e2e8f0"),
        }
        bg, fg, border = palette.get(state, palette["idle"])
        text = text or ""
        if len(text) > 72:
            text = text[:70] + "…"
        label.setText(text)
        label.setStyleSheet(
            "QLabel {"
            f" background-color: {bg}; color: {fg};"
            f" border: 1px solid {border}; border-radius: 9px;"
            " padding: 1px 9px; font-size: 11px; font-weight: 600;"
            " margin-right: 6px;"
            "}"
        )
        label.setVisible(bool(text))

    def _on_lyrics_fetch_progress(self, message):
        """歌词获取线程上报阶段进度"""
        text = message or ""
        self._set_lyrics_status(f"歌词：{text}" if text else "", "busy")

    def _update_play_status_badge(self, state_text):
        """更新播放状态小徽章样式"""
        if state_text == "播放中":
            bg, fg = "#fce7f3", "#db2777"
        elif state_text == "暂停":
            bg, fg = "#fef3c7", "#d97706"
        else:  # 停止
            bg, fg = "#f1f5f9", "#64748b"
        self.play_status_label.setText(state_text)
        self.play_status_label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border-radius: 9px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
                margin-right: 6px;
            }}
        """)

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
                self.player.sync_files(self.playlist_widget.get_all_files())
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
                self.player.sync_files(self.playlist_widget.get_all_files())
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
            self._cancel_active_lyrics_fetch()
            self.playlist_widget.clear()
            # 同时清空播放器的列表
            self.player.clear_playlist()  
            self.status_label.setText("播放列表已清空")
            # 停止播放
            self.player.stop()              
            self._current_playing_file = None
            # 清空歌词显示
            self.lyrics_widget.clear_lyrics()
            # 确实没有媒体了：显式复位进度与时间（时间清零只允许出现在这类场景）
            self.controls.reset_display()
            self.time_label.setText("00:00 / 00:00")
            
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
        self._cancel_active_lyrics_fetch()
        self.player.previous()
        # player 会通过延迟的 media_changed 信号自动更新状态栏

# 下一首回调        
    def on_next(self):
        """下一首回调"""
        self._cancel_active_lyrics_fetch()
        self.player.next()
        # player 会通过延迟的 media_changed 信号自动更新状态栏

# 播放模式切换回调
    def on_mode_changed(self, mode: str):
        """播放模式切换回调"""
        self.player.set_playback_mode(mode)
        mode_names = {'loop': '循环播放', 'random': '随机播放', 'sequential': '顺序播放'}
        name = mode_names.get(mode, '循环播放')
        self.status_label.setText(f"播放模式已切换为: {name}")
        if hasattr(self, 'shuffle_action'):
            self.shuffle_action.blockSignals(True)
            self.shuffle_action.setChecked(mode == 'random')
            self.shuffle_action.blockSignals(False)
        self.save_config()

# 随机播放切换回调          
    def on_shuffle_toggled(self, checked):
        """随机播放切换回调"""
        target_mode = 'random' if checked else 'loop'
        self.on_mode_changed(target_mode)
        self.controls.set_playback_mode(target_mode)
  
# 关于对话框（待实现） 
    def on_about(self):
        """关于对话框（待实现）"""
        QMessageBox.about(self, "关于", "音乐播放器 v0.1.0\n\n这是一个简单的音乐播放器")

# 窗口关闭事件
    def _trace(self, message):
        """可选的界面事件追踪：仅 MP_UI_DEBUG=1 时写入 debug/ui_trace.log

        用于排查"最小化很久后卡死"这类无法稳定复现的问题——日志最后一条
        就是卡死前发生的最后一个事件。
        """
        if not getattr(self, '_trace_enabled', False):
            return
        try:
            with open(self._trace_path, 'a', encoding='utf-8') as f:
                f.write("%s %s\n" % (time.strftime('%H:%M:%S'), message))
        except Exception:
            pass

    def changeEvent(self, event):
        """窗口状态变化：最小化/恢复时记录日志并重建窗口状态"""
        super().changeEvent(event)
        if event.type() != QEvent.WindowStateChange:
            return
        minimized = self.isMinimized()
        was_minimized = getattr(self, '_was_minimized', False)
        self._was_minimized = minimized
        if minimized:
            self._trace("窗口最小化")
            return
        if not was_minimized:
            return      # 只是最大化/还原，不需要特殊处理
        self._trace("窗口恢复")
        # 恢复时强制把状态、可见性与焦点重走一遍，避免停留在"看不见也点不开"的状态
        try:
            if self.windowState() & Qt.WindowMinimized:
                self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    def closeEvent(self, event):
        """窗口关闭事件"""
        self._cancel_active_lyrics_fetch()
        # 保存桌面歌词状态并关掉悬浮窗
        self._save_desktop_lyrics_state()
        window = getattr(self, 'desktop_lyrics', None)
        if window is not None:
            window.hide()
            window.deleteLater()
            self.desktop_lyrics = None
        # 保存窗口配置
        self.save_config()
        # 停止播放
        if hasattr(self, 'player'):
            self.player.stop()
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
        
        # 记录上次播放控制栏高度（支持降至55px最小高度）
        self._init_controls_height = self.config.get('layout', {}).get('controls_height', 110)
        self._init_controls_height = max(55, self._init_controls_height)
        
        # 应用播放器配置（如音量、播放模式）
        volume = self.config.get('player', {}).get('volume', 70)
        playback_mode = self.config.get('player', {}).get('playback_mode', 'loop')
        self._init_playback_mode = playback_mode
        if hasattr(self, 'player'):
            self.player.set_volume(volume)
            self.player.set_playback_mode(playback_mode)
        else:
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
                self.player.sync_files(self.playlist_widget.get_all_files())
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
        
        # 确保 player 部分存在，并保存音量、播放模式等设置
        if 'player' not in self.config:
            self.config['player'] = {}
        self.config['player']['volume'] = self.player.volume() if hasattr(self, 'player') else 70
        if hasattr(self, 'player'):
            self.config['player']['playback_mode'] = self.player.playback_mode()

        # 保存播放控制栏拖拽后的自定义高度
        if 'layout' not in self.config:
            self.config['layout'] = {}
        if hasattr(self, 'controls'):
            self.config['layout']['controls_height'] = self.controls.height()

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
        self.player.position_changed.connect(self.lyrics_widget.update_position)
        self.player.position_changed.connect(self._on_player_position_changed)
        self.player.state_changed.connect(self.controls.update_play_state)
        self.player.state_changed.connect(self.lyrics_widget.update_play_state)
        self.player.state_changed.connect(self._on_player_state_changed)
        self.player.volume_changed.connect(self.controls.update_volume)
        self.player.media_changed.connect(self.on_media_changed)
        self.player.error_occurred.connect(lambda err: self.status_label.setText(f"错误: {err}"))
        self.player.playlist_current_index_changed.connect(self.on_playlist_index_changed)
        self.player.playback_mode_changed.connect(self.controls.set_playback_mode)

    def _on_player_position_changed(self, pos_ms, dur_ms):
        """更新状态栏时间显示（位置由播放器以 50ms 节奏推送）"""
        text = self._format_time_pair(pos_ms, dur_ms)
        if self.time_label.text() != text:
            self.time_label.setText(text)

    @staticmethod
    def _format_time_pair(pos_ms, dur_ms):
        """把毫秒格式化为状态栏使用的 mm:ss / mm:ss 文本"""
        cur_sec = max(0, int(pos_ms)) // 1000
        tot_sec = max(0, int(dur_ms)) // 1000
        return f"{cur_sec // 60:02d}:{cur_sec % 60:02d} / {tot_sec // 60:02d}:{tot_sec % 60:02d}"

    def _on_player_state_changed(self, state):
        """播放状态变化回调

        只更新状态徽章，不再在 stopped 分支清空时间标签。
        Windows 多媒体后端在 setPosition 期间会瞬态抛出 StoppedState，
        原实现会因此把时间刷成 00:00 / 00:00，这正是"时间标签闪回开头"的来源。
        时间清零现在只允许发生在确实没有媒体的显式场景（如清空播放列表）。
        """
        if state == "playing":
            self._update_play_status_badge("播放中")
        elif state == "paused":
            self._update_play_status_badge("暂停")
        else:
            self._update_play_status_badge("停止")
        self._trace("播放状态 -> %s（最小化=%s）" % (state, self.isMinimized()))

# 连接UI组件的信号到播放器
    def _connect_ui_signals(self):
        """连接UI组件的信号到播放器"""
        # 控制面板
        self.controls.play_clicked.connect(self.player.play)
        self.controls.pause_clicked.connect(self.player.pause)
        self.controls.next_clicked.connect(self.player.next)
        self.controls.prev_clicked.connect(self.player.previous)
        self.controls.volume_changed.connect(self.player.set_volume)
        self.controls.position_changed.connect(self.player.set_position)
        self.controls.mode_changed.connect(self.on_mode_changed)
        self.controls.desktop_lyrics_toggled.connect(self.on_desktop_lyrics_toggled)
        
        # 播放列表
        self.playlist_widget.item_double_clicked.connect(self.on_playlist_double_clicked)
        self.playlist_widget.clear_requested.connect(self.on_clear_playlist)

        # 歌词组件
        self.lyrics_widget.fetch_lyrics_clicked.connect(self._on_manual_fetch_lyrics)
        self.lyrics_widget.ai_extract_clicked.connect(self._on_ai_extract_lyrics)
        self.lyrics_widget.save_lyrics_clicked.connect(self._on_save_lyrics)
        self.lyrics_widget.seek_requested.connect(self.on_seek_requested)
        self.lyrics_widget.open_editor_clicked.connect(self.on_open_lyrics_editor)    

    # ================== 桌面歌词 ==================

    def _ensure_desktop_lyrics(self):
        """按需创建桌面歌词窗口，并把数据源接上（只创建一次）"""
        window = getattr(self, 'desktop_lyrics', None)
        if window is not None:
            return window

        window = DesktopLyricsWindow()
        window.closed.connect(self._on_desktop_lyrics_closed)
        window.lock_changed.connect(self._on_desktop_lyrics_lock_changed)
        window.style_changed.connect(self._on_desktop_lyrics_style_changed)
        self.desktop_lyrics = window

        # 位置流（20Hz 渲染时钟）与歌词数据（复用歌词组件的解析结果）
        self.player.position_changed.connect(window.update_position)
        self.lyrics_widget.lyrics_parsed.connect(window.set_lyrics)

        # 恢复上次的位置、字号、颜色、锁定状态
        window.restore_state(self.config.get('desktop_lyrics', {}))
        window.set_lyrics(getattr(self.lyrics_widget, '_lrc_lines', []))
        return window

    def _restore_desktop_lyrics(self):
        """启动时按配置恢复桌面歌词"""
        state = self.config.get('desktop_lyrics', {})
        if not state.get('enabled'):
            return
        self.controls.set_desktop_lyrics_checked(True)
        window = self._ensure_desktop_lyrics()
        window.show()
        window.raise_()

    def on_desktop_lyrics_toggled(self, enabled):
        """底部开关：显示/隐藏桌面歌词

        锁定后鼠标穿不透，悬浮窗点不到，所以"解锁"也走这个按钮：
        锁定状态下第一次点击先解锁，再点一次才关闭。
        """
        window = self._ensure_desktop_lyrics()
        if enabled:
            window.show()
            window.raise_()
            self.status_label.setText("桌面歌词已开启（拖动可移动，双击锁定）")
            self._save_desktop_lyrics_state()
            return

        if window.is_locked():
            window.set_locked(False)
            self.controls.set_desktop_lyrics_checked(True)
            self.status_label.setText("桌面歌词已解锁（再次点击按钮可关闭）")
            return

        window.hide()
        self.status_label.setText("桌面歌词已关闭")
        self._save_desktop_lyrics_state()

    def _on_desktop_lyrics_closed(self):
        self.controls.set_desktop_lyrics_checked(False)
        self.status_label.setText("桌面歌词已关闭")
        self._save_desktop_lyrics_state()

    def _on_desktop_lyrics_lock_changed(self, locked):
        btn = getattr(self.controls, 'desktop_lyrics_btn', None)
        if btn is not None:
            btn.setText("桌面歌词(已锁)" if locked else "桌面歌词")
            btn.setToolTip("桌面歌词已锁定并鼠标穿透，点击本按钮解锁"
                           if locked else
                           "在桌面上显示悬浮歌词（置顶、可拖动，双击锁定后鼠标穿透）")
        if locked:
            self.status_label.setText("桌面歌词已锁定（点击下方【桌面歌词】按钮解锁）")
        else:
            self.status_label.setText("桌面歌词已解锁")
        self._save_desktop_lyrics_state()

    def _on_desktop_lyrics_style_changed(self, font_size, color):
        self._save_desktop_lyrics_state()

    def _save_desktop_lyrics_state(self):
        """把桌面歌词的显示状态、几何与样式写回配置"""
        window = getattr(self, 'desktop_lyrics', None)
        if window is None:
            return
        self.config['desktop_lyrics'] = window.get_state()
        self.save_config()

# 播放列表双击事件：加载并播放该文件
    def on_playlist_double_clicked(self, file_path):
        """播放列表双击事件：加载并播放该文件"""
        self._cancel_active_lyrics_fetch()
        all_files = self.playlist_widget.get_all_files()
        if not all_files:
            return

        norm_files = [os.path.normpath(f) for f in all_files]
        norm_target = os.path.normpath(file_path)
        try:
            index = norm_files.index(norm_target)
        except ValueError:
            index = 0

        # 如果底层播放列表媒体数不一致，进行一次性批量静默同步
        if self.player.playlist.mediaCount() != len(all_files):
            self.player.sync_files(all_files)

        self.player.playlist.setCurrentIndex(index)
        self.player.play()

# 媒体变化事件：更新状态栏等信息
    def on_media_changed(self, metadata):
        """当前媒体变化时更新状态栏、专辑封面、频谱与歌词等信息"""
        # 获取当前播放文件的本地路径
        file_path = metadata.get('path') or self.player.get_current_media_path()
        if not file_path and self.playlist_widget.playlist.count() > 0:
            file_path = self.playlist_widget.get_selected_file()

        # 防抖：避免短时间内同一曲目被重复解析或由于时长变化导致歌词重新加载
        # 注意：取消在跑的歌词任务必须放在防抖判断之后——同一首歌的重复通知
        # （WMF 在缓冲/状态切换时会重复发 mediaChanged）不该把用户刚点的获取任务掐掉
        if file_path:
            norm_path = os.path.normpath(file_path)
            if hasattr(self, '_current_playing_file') and self._current_playing_file:
                if os.path.normpath(self._current_playing_file) == norm_path:
                    return
            self._current_playing_file = file_path

        # 真正切歌时才中断此前正在获取中的网络歌词
        self._cancel_active_lyrics_fetch()

        if file_path and os.path.exists(file_path):
            full_meta = get_audio_metadata(file_path)
            title = full_meta.get('title') or metadata.get('title') or os.path.basename(file_path)
            artist = full_meta.get('artist') or metadata.get('artist') or '未知艺术家'
            # 如果标题含有后缀，去除扩展名
            if title.lower().endswith(tuple(AUDIO_EXTENSIONS)):
                title = os.path.splitext(title)[0]
        else:
            title = metadata.get('title', '未知')
            artist = metadata.get('artist', '未知')

        self.status_label.setText(f"正在播放: {title} - {artist}")
        self.setWindowTitle(f"{title} - 音乐播放器")

        # 读取并更新专辑封面
        if file_path:
            cover_data = get_audio_cover_bytes(file_path)
            self.lyrics_widget.set_cover(cover_data)
            # 传递给频谱组件以解析音频
            self.lyrics_widget.load_audio(file_path)
        else:
            self.lyrics_widget.set_cover(None)

        # 更新歌词组件的歌曲信息
        self.lyrics_widget.set_song_info(title, artist)
        # 触发歌词加载（仅本地/内置，不自动请求网络）
        # 必须把本次解析到的 file_path 传下去：切歌瞬间 player.currentMedia() 还是旧曲目，
        # 若让它自己去取，会拿旧文件名去命中旧歌的 .lrc / 内置歌词，表现为"切歌后仍显示上一首歌词"
        self.update_lyrics(title, artist, file_path)

# 播放列表索引变化事件：同步UI选中状态
    def on_playlist_index_changed(self, index):
        """当播放器内部索引改变时（如切歌），同步UI"""
        if index >= 0 and self.playlist_widget.playlist.count() > 0:
            # 1. 同步播放列表选中状态
            self.playlist_widget.set_current_index(index)
            
            # 2. 获取当前文件路径，触发元数据更新
            current_file = self.playlist_widget.get_selected_file()
            if current_file:
                meta = get_audio_metadata(current_file)
                meta['path'] = current_file
                self.on_media_changed(meta)

# 根据文件路径设置当前播放项
    def update_status_info(self):
        """获取当前播放文件的元数据并更新状态栏与封面"""
        current_path = self.player.get_current_media_path()
        if current_path and os.path.exists(current_path):
            meta = get_audio_metadata(current_path)
            meta['path'] = current_path
            self.on_media_changed(meta)
        else:
            self.status_label.setText("就绪")
            self.lyrics_widget.clear_lyrics()

# 播放器索引变化事件：同步UI选中状态
    def on_player_index_changed(self, index):
        """播放器切歌（上一首/下一首）时触发"""
        if index >= 0:
            self.playlist_widget.set_current_index(index)
        else:
            self.status_label.setText("就绪")
            self.lyrics_widget.clear_lyrics()

# 根据歌曲信息更新歌词显示（仅本地，不自动发起网络请求）
    def update_lyrics(self, title: str, artist: str, file_path: str = None):
        """根据歌曲信息更新歌词显示

        逻辑顺序：
        1. 先尝试读取音频文件内置歌词
        2. 再尝试读取项目本地 lyrics 文件夹缓存及同级目录.lrc
        3. 无本地歌词则提示用户手动点击【获取歌词】获取，不自动发起请求

        Args:
            title: 歌曲标题
            artist: 歌手名称
            file_path: 该歌曲的真实文件路径。切歌时为**新**曲目路径——不能省略，
                       否则会退化成读取播放器当前媒体（切歌瞬间仍是旧曲目）而串歌词
        """
        if not file_path:
            file_path = self.player.get_current_media_path()
        if not file_path and self.playlist_widget.playlist.count() > 0:
            file_path = self.playlist_widget.get_selected_file()

        # 换歌后上一次的"获取结果"提示已无意义
        self._set_lyrics_status("", "idle")

        # 1. 先尝试读取内置歌词
        if file_path:
            embedded_lyrics = lyrics_service.get_embedded_lyrics(file_path)
            if embedded_lyrics and embedded_lyrics.strip():
                self.lyrics_widget.set_lyrics(embedded_lyrics)
                self.lyrics_widget.hide_save_button()
                return

        # 2. 尝试读取项目本地或同名缓存歌词
        local_lyrics = lyrics_service.get_local_lyrics(title, artist, file_path)
        if local_lyrics and local_lyrics.strip():
            self.lyrics_widget.set_lyrics(local_lyrics)
            self.lyrics_widget.hide_save_button()
            return

        # 3. 没有本地歌词，不自动触发网络请求！提示用户可手动获取
        self.lyrics_widget.set_lyrics("未检测到本地歌词\n\n可点击右上角【获取歌词】手动从网络获取")
        self.lyrics_widget.hide_save_button()

    def _cancel_active_lyrics_fetch(self):
        """切换歌曲或清空列表时，自动安全中断当前正在后台异步获取中的网络歌词"""
        if hasattr(self, '_lyrics_fetch_thread') and self._lyrics_fetch_thread:
            thread = self._lyrics_fetch_thread
            self._lyrics_fetch_thread = None
            try:
                thread.fetched.disconnect()
            except Exception:
                pass
            try:
                thread.failed.disconnect()
            except Exception:
                pass
            try:
                thread.progress.disconnect()
            except Exception:
                pass
            if thread.isRunning():
                # 不调用 terminate()：强杀正在做网络 IO 的线程可能让进程在之后某次
                # 内存分配/加锁时卡死。这里只置取消标记，线程自己会安静退出。
                thread.cancel()
                self._retired_fetch_threads.append(thread)
                thread.finished.connect(
                    lambda t=thread: self._retired_fetch_threads.remove(t)
                    if t in self._retired_fetch_threads else None
                )
            # 有任务被中断时才更新状态，避免普通切歌也清掉提示
            self._set_lyrics_status("歌词：已取消获取", "idle")

        self._current_fetching_file = None
        if hasattr(self, 'lyrics_widget'):
            self.lyrics_widget.set_fetch_loading(False)

    def _on_manual_fetch_lyrics(self):
        """用户点击【获取歌词】按钮手动从网络获取"""
        current_path = self.player.get_current_media_path()
        if not current_path and self.playlist_widget.playlist.count() > 0:
            current_path = self.playlist_widget.get_selected_file()

        if not current_path:
            QMessageBox.information(self, "提示", "请先从左侧列表选择或播放歌曲")
            return

        meta = get_audio_metadata(current_path)
        title = meta.get('title', os.path.basename(current_path))
        artist = meta.get('artist', '')
        if artist == '未知艺术家':
            artist = ''

        # 启动新获取前先中断此前可能正在执行的旧曲目获取任务
        self._cancel_active_lyrics_fetch()
        self._current_fetching_file = current_path

        self.lyrics_widget.set_fetch_loading(True)
        self.lyrics_widget.set_lyrics("正在从网络搜索并获取匹配歌词...")
        self.lyrics_widget.hide_save_button()

        # 底部状态：先给出明确的"正在搜索"反馈，后续由线程逐段上报
        query = f"{title} {artist}".strip()
        self._set_lyrics_status(f"歌词：正在从网易云音乐搜索「{query}」…", "busy")

        # 启动后台线程异步获取，彻底杜绝界面阻塞卡顿
        self._lyrics_fetch_thread = lyrics_service.LyricsFetchThread(title, artist, current_path)
        self._lyrics_fetch_thread.fetched.connect(self._on_lyrics_fetched_success)
        self._lyrics_fetch_thread.failed.connect(self._on_lyrics_fetched_failed)
        self._lyrics_fetch_thread.progress.connect(self._on_lyrics_fetch_progress)
        self._lyrics_fetch_thread.start()

    def _on_lyrics_fetched_success(self, lyrics: str, title: str, artist: str, file_path: str):
        """歌词获取成功回调"""
        self.lyrics_widget.set_fetch_loading(False)
        # 严格校验：获取返回的歌曲必须与当前正在播放或选中的歌曲一致，杜绝切歌后串歌词
        current_path = self.player.get_current_media_path() or (self.playlist_widget.get_selected_file() if self.playlist_widget.playlist.count() > 0 else None)
        if file_path and current_path:
            if os.path.normpath(file_path) != os.path.normpath(current_path):
                return

        self.lyrics_widget.set_lyrics(lyrics)
        self.lyrics_widget.show_save_button()
        self._pending_lyrics_title = title
        self._pending_lyrics_artist = artist
        self._pending_lyrics_text = lyrics
        self._pending_lyrics_filepath = file_path
        lines = getattr(self.lyrics_widget, '_lrc_lines', []) or []
        self._set_lyrics_status(
            f"歌词：已从网易云音乐获取（{len(lines)} 行），点击【保存歌词】可存入本地", "ok"
        )
        self.status_label.setText("网络歌词获取成功，点击右上角【保存歌词】可保存至本地")

    def _on_lyrics_fetched_failed(self, error_msg: str):
        """歌词获取失败回调"""
        self.lyrics_widget.set_fetch_loading(False)
        # 若发起该请求的歌曲已不再是当前曲目，静默忽略旧曲目失败信息
        if hasattr(self, '_current_fetching_file') and self._current_fetching_file:
            current_path = self.player.get_current_media_path() or (self.playlist_widget.get_selected_file() if self.playlist_widget.playlist.count() > 0 else None)
            if current_path and os.path.normpath(self._current_fetching_file) != os.path.normpath(current_path):
                return

        self.lyrics_widget.set_lyrics(f"未检索到匹配歌词\n\n提示: {error_msg}\n请确认歌曲名称或艺术家信息是否准确后重试。")
        self.lyrics_widget.hide_save_button()
        self._set_lyrics_status(f"歌词：获取失败 - {error_msg}", "fail")
        self.status_label.setText("未检索到匹配歌词")

    def _fetch_netease_lyrics(self, title: str, artist: str, file_path: str):
        """兼容旧接口"""
        self._on_manual_fetch_lyrics()

    def _on_ai_extract_lyrics(self):
        """AI 提取歌词按钮点击（兼容旧调用）"""
        self._on_manual_fetch_lyrics()

    def _on_save_lyrics(self):
        """保存歌词按钮点击"""
        if (hasattr(self, '_pending_lyrics_title') and
            hasattr(self, '_pending_lyrics_artist') and
            hasattr(self, '_pending_lyrics_text')):
            file_path = getattr(self, '_pending_lyrics_filepath', '')
            success = lyrics_service.save_lyrics_to_file(
                self._pending_lyrics_title,
                self._pending_lyrics_artist,
                self._pending_lyrics_text,
                file_path
            )
            if success:
                QMessageBox.information(
                    self, "保存成功",
                    f"歌词已成功保存至本地！\n\n"
                    f"保存目录: {lyrics_service.LYRICS_DIR}"
                )
                self.lyrics_widget.hide_save_button()
                self.status_label.setText("歌词已成功保存至本地")
            else:
                QMessageBox.warning(
                    self, "保存失败",
                    "歌词保存失败，请检查目录权限"
                )
        else:
            QMessageBox.warning(self, "保存失败", "没有可保存的歌词内容")

    def on_seek_requested(self, pos_ms: int):
        """点击歌词→检查对应时间戳→等效于操作播放条跳转音乐

        顺序不能颠倒：Windows 多媒体后端在 StoppedState 下会忽略 setPosition，
        必须先激活播放状态再跳转，否则会从头开始播放（与歌词编辑器 _listen_row 保持一致）。
        """
        if pos_ms < 0:
            return

        # 先激活播放状态，再登记跳转意图
        if not self.player.is_playing():
            self.player.play()

        # 通过播放控制栏设置目标进度；跳转保护由 MusicPlayer 的跳转状态机统一负责
        self.controls.seek_to_ms(pos_ms)

        # 状态栏时间立即反映跳转意图，不必等驱动回吐确认
        dur_ms = self.player.get_duration()
        if dur_ms > 0:
            self.time_label.setText(self._format_time_pair(min(pos_ms, dur_ms), dur_ms))

        sec = pos_ms // 1000
        self.status_label.setText(f"已跳转播放进度至 {sec // 60:02d}:{sec % 60:02d}")

    def on_open_lyrics_editor(self):
        """打开 LRC 歌词制作与微调工具"""
        file_path = self.player.get_current_media_path()
        if not file_path and self.playlist_widget.playlist.count() > 0:
            file_path = self.playlist_widget.get_selected_file()

        title = ""
        artist = ""
        if file_path and os.path.exists(file_path):
            meta = get_audio_metadata(file_path)
            title = meta.get('title') or os.path.splitext(os.path.basename(file_path))[0]
            artist = meta.get('artist') or ""
            if artist == "未知艺术家":
                artist = ""
        elif hasattr(self, '_pending_lyrics_title'):
            title = self._pending_lyrics_title
            artist = getattr(self, '_pending_lyrics_artist', "")

        # 尝试获取当前可用的歌词内容作为初始内容
        initial_lyrics = ""
        if hasattr(self, '_pending_lyrics_text') and self._pending_lyrics_text:
            initial_lyrics = self._pending_lyrics_text
        elif title:
            initial_lyrics = lyrics_service.get_local_lyrics(title, artist, file_path)
            if not initial_lyrics and file_path:
                initial_lyrics = lyrics_service.get_embedded_lyrics(file_path)

        # 若主播放器正在播放，先暂停避免声音冲突
        if self.player.is_playing():
            self.player.pause()

        # 打开独立的歌词编辑器
        editor = LyricsEditorDialog(
            parent=self,
            audio_file=file_path or "",
            title=title,
            artist=artist,
            initial_lyrics=initial_lyrics or ""
        )

        def _on_editor_saved(lrc_text, saved_title, saved_artist, saved_audio_path):
            # 当编辑器中保存歌词后，立即同步到主界面歌词组件
            if not file_path or (saved_audio_path and os.path.normpath(saved_audio_path) == os.path.normpath(file_path)):
                self.lyrics_widget.set_lyrics(lrc_text)
                self.lyrics_widget.hide_save_button()
                self.status_label.setText(f"歌词已更新并应用: {saved_title}")

        editor.lyrics_saved.connect(_on_editor_saved)
        editor.exec_()

















