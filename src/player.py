"""
播放器核心类
使用 PyQt5 的 QMediaPlayer 和 QMediaPlaylist
"""
import os
from PyQt5.QtCore import QObject, pyqtSignal, QUrl, QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QMediaPlaylist

class MusicPlayer(QObject):
    """音乐播放器核心类"""

    # 定义信号
    position_changed = pyqtSignal(int, int)          # 当前播放位置（毫秒），总时长（毫秒）
    state_changed = pyqtSignal(str)                   # 播放状态：playing, paused, stopped
    volume_changed = pyqtSignal(int)                   # 音量变化
    media_changed = pyqtSignal(dict)                   # 当前媒体信息变化（传入元数据字典）
    playlist_current_index_changed = pyqtSignal(int)   # 播放列表当前索引变化
    error_occurred = pyqtSignal(str)                   # 错误信息

    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer()
        self.playlist = QMediaPlaylist()

        # 设置播放列表为循环模式
        self.playlist.setPlaybackMode(QMediaPlaylist.Loop)

        # 连接播放器信号
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.stateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.error.connect(self._on_player_error)

        # 连接播放列表信号
        self.playlist.currentIndexChanged.connect(self._on_playlist_index_changed)

        # 将播放列表设置给播放器
        self.player.setPlaylist(self.playlist)

        # 内部变量
        self.current_metadata = {}  # 当前媒体元数据

    # ================== 公共控制接口 ==================

    def load_file(self, file_path):
        """加载单个文件到播放列表（会清空现有列表）"""
        self.playlist.clear()
        self.add_file(file_path)

    def add_file(self, file_path):
        """添加单个文件到播放列表末尾"""
        url = QUrl.fromLocalFile(file_path)
        content = QMediaContent(url)
        self.playlist.addMedia(content)
        # 如果这是第一个添加的媒体，自动设为当前
        if self.playlist.mediaCount() == 1:
            self.playlist.setCurrentIndex(0)

    def add_files(self, file_paths):
        """批量添加文件"""
        for path in file_paths:
            self.add_file(path)

    def play(self):
        """播放"""
        if self.playlist.mediaCount() == 0:
            return
        self.player.play()

    def pause(self):
        """暂停"""
        self.player.pause()

    def stop(self):
        """停止"""
        self.player.stop()

    def play_pause(self):
        """播放/暂停切换"""
        if self.player.state() == QMediaPlayer.PlayingState:
            self.pause()
        else:
            self.play()

    def next(self):
        """下一首"""
        # 直接使用 QMediaPlaylist 的 next 方法
        # 它会自动处理循环模式(Loop/Random)和索引变化
        self.playlist.next()
        # 注意：不要在这里手动 play() 或 setCurrentIndex()
        # 状态变化由 _on_playlist_index_changed 信号驱动

    def previous(self):
        """上一首"""
        self.playlist.previous()

    def set_volume(self, volume):
        """设置音量 (0-100)"""
        self.player.setVolume(volume)

    def volume(self):
        """获取当前音量"""
        return self.player.volume()

    def set_position(self, position_ms):
        """设置播放位置（毫秒）"""
        self.player.setPosition(position_ms)

    def clear_playlist(self):
        """清空播放列表"""
        self.playlist.clear()

    def get_current_media_path(self):
        """获取当前播放媒体的本地路径"""
        media = self.player.currentMedia()
        if media.isNull():
            return None
        return media.canonicalUrl().toLocalFile()

    # ================== 内部槽函数 ==================

    def _on_position_changed(self, position):
        """播放位置变化时发出信号"""
        duration = self.player.duration()
        self.position_changed.emit(position, duration)

    def _on_duration_changed(self, duration):
        """总时长变化时（加载新媒体后触发），可更新元数据中的时长"""
        # 可选：更新 current_metadata 中的时长
        if self.current_metadata:
            self.current_metadata['duration'] = duration // 1000  # 转换为秒
            self.media_changed.emit(self.current_metadata)

    def _on_state_changed(self, state):
        """播放状态变化"""
        state_map = {
            QMediaPlayer.StoppedState: 'stopped',
            QMediaPlayer.PlayingState: 'playing',
            QMediaPlayer.PausedState: 'paused'
        }
        self.state_changed.emit(state_map.get(state, 'unknown'))

    def _on_media_status_changed(self, status):
        """媒体状态变化，可用于加载元数据"""
        # 当媒体加载完成时，获取元数据（如果有）
        if status == QMediaPlayer.LoadedMedia:
            # 可以尝试获取元数据，但 QMediaPlayer 的元数据支持有限
            # 这里我们通过自定义方式在外部设置元数据
            pass

    def _on_player_error(self, error):
        """播放器错误"""
        if error != QMediaPlayer.NoError:
            self.error_occurred.emit(self.player.errorString())

    def _on_playlist_index_changed(self, index):
        """播放列表当前索引变化"""
        self.playlist_current_index_changed.emit(index)
        # 使用延迟确保媒体对象已完全切换，然后再获取路径
        # 不延迟的话 get_current_media_path() 会返回旧媒体
        QTimer.singleShot(10, self._emit_media_changed_for_index)

    def _emit_media_changed_for_index(self):
        """延迟发送媒体变化信号，确保媒体对象已切换"""
        path = self.get_current_media_path()
        if path:
            # 此时媒体已经切换，发出准确的信号
            self.media_changed.emit({'path': path, 'title': os.path.basename(path)})

    def set_metadata_for_current(self, metadata):
        """供外部设置当前媒体的元数据，然后发出 media_changed 信号"""
        self.current_metadata = metadata
        self.media_changed.emit(metadata)
    
    def is_playing(self):
        """检查是否正在播放"""
        return self.player.state() == QMediaPlayer.PlayingState
    
    def set_shuffle(self, enabled):
        """设置随机播放模式"""
        if enabled:
            self.playlist.setPlaybackMode(QMediaPlaylist.Random)
        else:
            self.playlist.setPlaybackMode(QMediaPlaylist.Sequential)
        
