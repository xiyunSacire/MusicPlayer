"""
播放器核心类
使用 PyQt5 的 QMediaPlayer 和 QMediaPlaylist
"""
import os
import time
import traceback
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
    playback_mode_changed = pyqtSignal(str)            # 播放模式变化：loop, random, sequential
    error_occurred = pyqtSignal(str)                   # 错误信息

    # ===== 跳转状态机判定参数 =====
    # 全项目唯一定义处。UI 层禁止再各自复制一份 500ms / 1000ms / 2000ms / 0.4s 之类的阈值。
    SEEK_CONFIRM_TOLERANCE_MS = 1500   # 驱动回吐位置进入目标±该值，即判定跳转完成
    SEEK_BACKWARD_JUMP_MS = 500        # 正常播放中位置倒退超过该值，视为无来源的异常回退
    SEEK_LOOP_END_MARGIN_MS = 3000     # 上一位置距总时长小于该值时，允许把倒退解释为循环重播
    SEEK_CONFIRM_TIMEOUT_MS = 3000     # 绝对兜底：长时间没有任何可判定的报告时才放弃
    SEEK_RETRY_TIMES = 1               # 判定未生效后重发一次（WMF 偶尔整个吞掉 seek）
    SEEK_SETTLE_S = 2.0                # 跳转后的落点校正窗口（这段时间内以驱动为准，允许回退）
    SEEK_LANDING_TOLERANCE_MS = 5000   # 落点校正允许的最大偏差：超出即判为驱动异常而非落点

    RENDER_INTERVAL_MS = 50            # 界面位置渲染间隔（20Hz）

    def __init__(self):
        super().__init__()

        # 内部状态必须在任何信号连接之前初始化：
        # setPlaylist() 阶段底层驱动就可能回吐 positionChanged，若此时状态变量尚未
        # 就绪，槽函数会直接抛 AttributeError（在 Qt 槽里属于致命错误）。
        self.current_metadata = {}  # 当前媒体元数据
        self._cached_duration = 0   # 缓存已知有效总时长（毫秒）

        # 跳转状态机：None 为正常态；非 None 表示已登记跳转意图、正在等待驱动确认
        self._seek_target_ms = None
        self._seek_pending_since = 0.0
        self._last_position_ms = 0          # 最近一次驱动上报的位置（用于判定）
        # 渲染时钟：锚点 + 对外已派发的最大位置（保证界面单调不回退）
        self._anchor_position_ms = 0
        self._anchor_time = time.time()
        self._render_position_ms = 0
        # 跳转落点校正：记录最近的跳转目标与时间
        self._seek_reference_ms = None
        self._seek_reference_time = 0.0
        self._confirm_candidate_ms = None   # 跳转确认的第一帧候选（需连续两帧一致）
        self._seek_retry_left = 0           # 剩余重发次数（判定未生效时使用）
        self._seek_far_reports = 0          # 跳转等待期内"远离目标"的报告计数

        self.player = QMediaPlayer()
        self.playlist = QMediaPlaylist()

        # 默认设置为列表循环模式
        self._playback_mode = 'loop'
        self.playlist.setPlaybackMode(QMediaPlaylist.Loop)

        # 连接播放器信号
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.stateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.error.connect(self._on_player_error)

        # 连接播放列表信号
        self.playlist.currentIndexChanged.connect(self._on_playlist_index_changed)

        # 位置渲染时钟：
        # 后端的 positionChanged 只有约 1 秒一次的粒度，直接拿它刷界面必然一闪一闪。
        # 因此界面位置改由这里以 50ms 的节奏推进：以最后一次可信位置为锚点，按墙钟
        # 1:1 插值；驱动上报只负责把时钟"往前拨"，永不回退。
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(self.RENDER_INTERVAL_MS)
        self._render_timer.timeout.connect(self._on_render_tick)
        self._render_timer.start()

        # 诊断日志：默认开启，每次启动重写，写在项目 debug/seek.log
        # （*.log 已被 .gitignore 忽略；设置环境变量 MP_SEEK_DEBUG=0 可完全关闭）
        self._debug_enabled = os.environ.get('MP_SEEK_DEBUG', '0') != '0'
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        debug_dir = os.path.join(project_root, 'debug')
        self._debug_path = os.path.join(debug_dir, 'seek.log')
        if self._debug_enabled:
            try:
                os.makedirs(debug_dir, exist_ok=True)
                with open(self._debug_path, 'w', encoding='utf-8') as f:
                    f.write('=== MusicPlayer 诊断日志  本次运行 %s ===\n'
                            % time.strftime('%Y-%m-%d %H:%M:%S'))
            except Exception:
                self._debug_enabled = False
            print('[诊断] seek 日志: %s' % self._debug_path)

        # 将播放列表设置给播放器
        self.player.setPlaylist(self.playlist)

    # ================== 诊断与渲染时钟 ==================

    def _debug(self, message):
        """可选诊断日志（MP_SEEK_DEBUG=1 时写入 %TEMP%\\musicplayer-seek.log）"""
        if not self._debug_enabled:
            return
        try:
            now = time.time()
            stamp = '%s.%03d' % (time.strftime('%H:%M:%S', time.localtime(now)),
                                 int(now * 1000) % 1000)
            with open(self._debug_path, 'a', encoding='utf-8') as f:
                f.write('%s  %s\n' % (stamp, message))
        except Exception:
            pass

    def _project_position(self, now):
        """由锚点按墙钟推算当前应显示的位置（毫秒）"""
        projected = self._anchor_position_ms + int((now - self._anchor_time) * 1000.0)
        dur = self.get_duration()
        if dur > 0:
            projected = min(projected, dur)
        return max(projected, 0)

    def _emit_position(self, position_ms, dur_ms, allow_backward=False):
        """对外派发位置的唯一出口：默认保证单调不回退"""
        if not allow_backward and position_ms < self._render_position_ms:
            return
        self._render_position_ms = position_ms
        self.position_changed.emit(position_ms, dur_ms)

    def _on_render_tick(self):
        """50ms 渲染：正常播放且没有跳转悬挂时，按墙钟推进界面"""
        now = time.time()
        if (self._seek_reference_ms is not None
                and (now - self._seek_reference_time) > self.SEEK_SETTLE_S):
            # 落点校正窗口已过，恢复正常判定
            self._seek_reference_ms = None
        if self.player.state() != QMediaPlayer.PlayingState:
            return
        if self._seek_target_ms is not None:
            return
        self._emit_position(self._project_position(now), self.get_duration())

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

    def sync_files(self, file_paths):
        """同步批量设置播放列表文件，避免频繁触发信号风暴"""
        self.playlist.blockSignals(True)
        self.playlist.clear()
        for p in file_paths:
            content = QMediaContent(QUrl.fromLocalFile(p))
            self.playlist.addMedia(content)
        self.playlist.blockSignals(False)

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

    def get_duration(self) -> int:
        """获取当前音频总时长（毫秒），具备高鲁棒性缓存兜底"""
        dur = self.player.duration()
        if dur > 0:
            self._cached_duration = dur
            return dur
        return getattr(self, '_cached_duration', 0)

    def set_position(self, position_ms):
        """登记一次跳转意图（毫秒）

        这里只负责"告诉驱动"和"进入等待确认状态"，不向 UI 回吐未经确认的位置。
        UI 的即时反馈（滑块/时间/高亮）由发起方自己完成，这里只把渲染时钟对齐到
        目标位置，跳转确认后再以驱动的真实值校正。
        """
        if position_ms < 0:
            position_ms = 0
        if self._debug_enabled:
            stack = traceback.extract_stack()
            caller = 'unknown'
            if len(stack) >= 2:
                frame = stack[-2]
                caller = '%s:%d %s' % (os.path.basename(frame.filename), frame.lineno, frame.name)
            self._debug('set_position(%d) 来源=%s' % (position_ms, caller))
        self._seek_target_ms = position_ms
        self._seek_pending_since = time.time()
        # 以目标位置作为基线，避免跳转完成后回吐位置被误判为"位置倒退"
        self._last_position_ms = position_ms
        self._anchor_position_ms = position_ms
        self._anchor_time = self._seek_pending_since
        # 渲染时钟允许回退（这是用户显式要求的跳转），但不主动 emit：
        # 界面已经由发起方设成目标状态，后续由渲染时钟从目标位置继续推进
        self._render_position_ms = position_ms
        # 落点校正窗口：驱动随后报出与目标相近但不同的位置时，以驱动为准
        self._seek_reference_ms = position_ms
        self._seek_reference_time = self._seek_pending_since
        self._confirm_candidate_ms = None
        self._seek_retry_left = self.SEEK_RETRY_TIMES
        self._seek_far_reports = 0
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

    def _is_driver_flush_position(self, position):
        """判断某个回吐位置是否是驱动 flush 抛出的"归零脉冲"

        Windows 多媒体后端在 setPosition 期间会上报 0。0 只有在目标本身就在开头附近时
        才是合法值；目标在别处时，0 必然是不可信的 flush 脉冲。这条判断让
        "点第一句歌词（目标 300ms）"与"点后面的歌词（目标 60s）"用同一套规则处理，
        不需要为开头附近的跳转单独开洞。
        """
        return position <= 200 and self._seek_target_ms is not None and self._seek_target_ms > 200

    def _on_position_changed(self, position):
        """驱动上报的位置：只用于校验与把渲染时钟往前拨，不直接决定界面

        判定只有两层，全部基于状态，不含任何时间窗魔数：

        1) 跳转等待期：只接受落入目标容差窗口、且不是 flush 归零脉冲的回吐；
           超时说明这次跳转没生效，以驱动位置重新起算。
        2) 正常播放期：驱动上报只能把时钟"往前拨"。落后于墙钟推算的值一律忽略，
           因此驱动把位置时钟重置到低位的情况，界面不动；而渲染时钟自己继续走。
           唯一需要整段重来的情况是曲目播到末尾后循环回开头（此时推算位置贴近总时长）。
        """
        dur = self.get_duration()
        now = time.time()

        # 无媒体等情况下驱动会吐出垃圾负值，直接忽略
        if position < 0:
            return

        # ---- 第一层：跳转等待期 ----
        if self._seek_target_ms is not None:
            near_target = abs(position - self._seek_target_ms) <= self.SEEK_CONFIRM_TOLERANCE_MS
            if near_target and not self._is_driver_flush_position(position):
                if self._confirm_candidate_ms is None:
                    # 第一帧先不作数：驱动在 seek 后常先吐一个跳转前的旧位置
                    self._debug('确认候选 position=%d target=%d' % (position, self._seek_target_ms))
                    self._confirm_candidate_ms = position
                    return
                # 连续两帧都落在目标附近，以第二帧（更接近真实落点）为准
                self._debug('确认跳转 position=%d target=%d' % (position, self._seek_target_ms))
                self._seek_target_ms = None
                self._seek_pending_since = 0.0
                self._confirm_candidate_ms = None
                self._seek_far_reports = 0
                self._last_position_ms = position
                self._anchor_position_ms = position
                self._anchor_time = now
                self._emit_position(position, dur, allow_backward=True)
                return

            # 远离目标的报告 = 这次 seek 还没生效。用"连续两帧远离"代替时间窗判定：
            # 第一帧先重发一次 seek（后端偶尔整个吞掉请求），第二帧仍远离才判失败。
            if not self._is_driver_flush_position(position):
                self._seek_far_reports += 1
                if self._seek_far_reports == 1 and self._seek_retry_left > 0:
                    self._seek_retry_left -= 1
                    self._seek_pending_since = now
                    self._confirm_candidate_ms = None
                    self._debug('跳转未生效，重发 set_position(%d)' % self._seek_target_ms)
                    self.player.setPosition(self._seek_target_ms)
                    return
                if self._seek_far_reports >= 2:
                    self._debug('跳转确认失败 position=%d target=%d' % (position, self._seek_target_ms))
                    self._seek_target_ms = None
                    self._seek_pending_since = 0.0
                    self._confirm_candidate_ms = None
                    self._seek_far_reports = 0
                    self._last_position_ms = position
                    self._anchor_position_ms = position
                    self._anchor_time = now
                    self._emit_position(position, dur, allow_backward=True)
                    return

            elapsed_ms = (now - self._seek_pending_since) * 1000.0
            if elapsed_ms < self.SEEK_CONFIRM_TIMEOUT_MS:
                self._debug('等待中丢弃 position=%d target=%d elapsed=%dms'
                            % (position, self._seek_target_ms, elapsed_ms))
                return
            # 绝对兜底：长时间没有任何可判定的报告
            self._debug('跳转等待兜底超时 position=%d target=%d' % (position, self._seek_target_ms))
            self._seek_target_ms = None
            self._seek_pending_since = 0.0
            self._confirm_candidate_ms = None
            self._seek_far_reports = 0
            self._last_position_ms = position
            self._anchor_position_ms = position
            self._anchor_time = now
            self._emit_position(position, dur, allow_backward=True)
            return
            return

        # ---- 第二层：跳转落点校正 ----
        # 只处理一种情况：跳转刚发生不久，驱动报出一个"比当前显示更早、但仍在目标附近"
        # 的位置——那才是它真实的落点（回吐的目标值可能和实际落点不符）。
        # 正常前进的报告不会走到这里。
        if (self._seek_reference_ms is not None
                and (now - self._seek_reference_time) <= self.SEEK_SETTLE_S
                and position < self._last_position_ms - self.SEEK_BACKWARD_JUMP_MS
                and abs(position - self._seek_reference_ms) <= self.SEEK_LANDING_TOLERANCE_MS):
            self._debug('落点校正 position=%d 目标=%d 已显示=%d'
                        % (position, self._seek_reference_ms, self._last_position_ms))
            self._last_position_ms = position
            self._anchor_position_ms = position
            self._anchor_time = now
            self._emit_position(position, dur, allow_backward=True)
            return

        # ---- 第三层：正常播放期 ----
        est = self._project_position(now)
        if position < est - self.SEEK_BACKWARD_JUMP_MS:
            # 大幅倒退且没有任何登记来源：丢弃（曲目切换由播放列表索引信号负责重置）
            self._debug('丢弃无来源回退 position=%d 推算=%d dur=%d' % (position, est, dur))
            return

        if abs(position - est) <= self.SEEK_CONFIRM_TOLERANCE_MS:
            # 与墙钟推算相差不大：视为固定偏移（例如开播瞬间的锚点误差），
            # 用驱动值微调锚点消除偏差；界面不因此跳动，由渲染时钟继续推进。
            self._anchor_position_ms = position
            self._anchor_time = now
            self._last_position_ms = position
            if position > self._render_position_ms:
                self._emit_position(position, dur)
            return

        # 驱动明显领先于推算（> 容差）：直接向前拨并上报
        self._anchor_position_ms = position
        self._anchor_time = now
        self._last_position_ms = position
        self._emit_position(position, dur)

    def _on_duration_changed(self, duration):
        """总时长变化时（加载新媒体后触发），更新缓存并通知元数据"""
        if duration <= 0:
            return  # 彻底忽略 seek 期间或底层缓冲时释放的 -1 或 0 脉冲信号，避免引发UI状态重置
        self._cached_duration = duration
        if self.current_metadata:
            old_dur = self.current_metadata.get('duration', 0)
            new_dur = duration // 1000
            if abs(new_dur - old_dur) > 1:
                self.current_metadata['duration'] = new_dur
                self.media_changed.emit(self.current_metadata)

    def _on_state_changed(self, state):
        """播放状态变化"""
        state_map = {
            QMediaPlayer.StoppedState: 'stopped',
            QMediaPlayer.PlayingState: 'playing',
            QMediaPlayer.PausedState: 'paused'
        }
        # 状态切换时重设锚点：暂停期间不能把时间算进插值，恢复播放要从当前位置起算。
        # 锚点取"当前渲染位置"，保证暂停时界面停在原处、恢复后从原处继续。
        self._anchor_position_ms = self._render_position_ms
        self._anchor_time = time.time()
        self._last_position_ms = self._render_position_ms
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
        # 切曲：跳转状态、锚点、渲染时钟与落点校正全部复位
        self._seek_target_ms = None
        self._seek_pending_since = 0.0
        self._last_position_ms = 0
        self._anchor_position_ms = 0
        self._anchor_time = time.time()
        self._render_position_ms = 0
        self._seek_reference_ms = None
        self._confirm_candidate_ms = None
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
    
    def set_playback_mode(self, mode: str):
        """设置播放模式：'loop'(循环播放), 'random'(随机播放), 'sequential'(顺序播放)"""
        mode_lower = (mode or '').lower()
        if mode_lower == 'sequential':
            self._playback_mode = 'sequential'
            self.playlist.setPlaybackMode(QMediaPlaylist.Sequential)
        elif mode_lower == 'random':
            self._playback_mode = 'random'
            self.playlist.setPlaybackMode(QMediaPlaylist.Random)
        else:
            self._playback_mode = 'loop'
            self.playlist.setPlaybackMode(QMediaPlaylist.Loop)
        self.playback_mode_changed.emit(self._playback_mode)

    def playback_mode(self) -> str:
        """获取当前播放模式：'loop', 'random', 'sequential'"""
        return getattr(self, '_playback_mode', 'loop')

    def set_shuffle(self, enabled):
        """设置随机播放模式（兼容旧接口）"""
        self.set_playback_mode('random' if enabled else 'loop')
        

