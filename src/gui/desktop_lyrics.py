# -*- coding: utf-8 -*-
"""
桌面歌词悬浮窗

设计参考开源实现 SPlayer（Electron）的桌面歌词窗口：
独立无边框透明窗口、置顶、不进任务栏、不抢焦点；位置与样式持久化；
锁定后鼠标穿透（解锁入口留在主界面按钮上）。

与主程序的关系：
    MusicPlayer.position_changed (20Hz) -> update_position()  只做换行判断
    LyricsWidget.lyrics_parsed          -> set_lyrics()       复用同一份 LRC 解析结果
"""

from PyQt5.QtCore import QEasingCurve, Qt, QVariantAnimation, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget


class OutlinedLabel(QLabel):
    """带描边的文本标签：保证在任意桌面背景上都清晰可读

    用 QPainterPath 先描边再填充，比窗口级阴影/模糊更稳（不依赖合成器）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setTextFormat(Qt.PlainText)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._text_color = QColor(255, 255, 255)
        self._stroke_color = QColor(0, 0, 0, 215)
        self._alpha = 1.0

    def set_text_color(self, color):
        self._text_color = QColor(color)
        self.update()

    def set_alpha(self, alpha):
        self._alpha = max(0.0, min(1.0, float(alpha)))
        self.update()

    def paintEvent(self, event):
        text = self.text()
        if not text:
            return
        font = self.font()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        metrics = QFontMetrics(font)
        rows = text.split("\n")
        line_h = metrics.height()
        y = (self.height() - line_h * len(rows)) / 2.0 + metrics.ascent()

        path = QPainterPath()
        for row in rows:
            width = metrics.width(row)
            path.addText((self.width() - width) / 2.0, y, font, row)
            y += line_h

        stroke = QColor(self._stroke_color)
        stroke.setAlpha(int(stroke.alpha() * self._alpha))
        pen = QPen(stroke)
        pen.setWidthF(max(2.0, font.pointSizeF() * 0.12))
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        painter.strokePath(path, pen)

        fill = QColor(self._text_color)
        fill.setAlpha(int(fill.alpha() * self._alpha))
        painter.fillPath(path, fill)
        painter.end()


class DesktopLyricsWindow(QWidget):
    """桌面歌词悬浮窗（双行：当前句 + 下一句）"""

    closed = pyqtSignal()
    lock_changed = pyqtSignal(bool)
    style_changed = pyqtSignal(int, str)

    DEFAULT_FONT_SIZE = 26
    MIN_FONT_SIZE = 14
    MAX_FONT_SIZE = 54
    DEFAULT_COLOR = "#ffffff"
    DEFAULT_SIZE = (760, 150)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("桌面歌词")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)

        self._lines = []
        self._current_index = -1
        self._locked = False
        self._font_size = self.DEFAULT_FONT_SIZE
        self._color = QColor(self.DEFAULT_COLOR)
        self._drag_offset = None

        self._build_ui()
        self._apply_font()
        self.resize(*self.DEFAULT_SIZE)

    # ================== 构建 ==================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 12, 28, 12)
        layout.setSpacing(2)

        self.current_label = OutlinedLabel(self)
        self.translation_label = OutlinedLabel(self)
        self.translation_label.set_text_color(QColor(226, 232, 240))
        self.translation_label.set_alpha(0.85)
        self.translation_label.setVisible(False)
        self.next_label = OutlinedLabel(self)
        self.next_label.set_text_color(QColor(235, 235, 235))
        self.next_label.set_alpha(0.62)

        layout.addWidget(self.current_label, 3)
        layout.addWidget(self.translation_label, 2)
        layout.addWidget(self.next_label, 2)

        # 换行时当前句做一次淡入，避免生硬跳变
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(180)
        self._fade.setStartValue(0.25)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade.valueChanged.connect(self.current_label.set_alpha)

    # ================== 数据 ==================

    def set_lyrics(self, lines):
        """接收 [(time_ms, text[, translation]), ...]（与歌词组件同一份解析结果）

        当前句有翻译时，在它下方多显示一行译文。
        """
        normalized = []
        for item in (lines or []):
            try:
                if len(item) >= 2:
                    translation = str(item[2]) if len(item) >= 3 and item[2] else ""
                    normalized.append((int(item[0]), str(item[1]), translation))
            except Exception:
                continue
        self._lines = normalized
        self._current_index = -1
        self._refresh(first=True)

    def clear_lyrics(self):
        self.set_lyrics([])

    def update_position(self, pos_ms, duration_ms=0):
        """播放进度变化：只判断是否需要换行，不做逐帧重绘"""
        if not self._lines:
            return
        index = self._line_index(pos_ms)
        if index == self._current_index:
            return
        self._current_index = index
        self._refresh()

    def _line_index(self, pos_ms):
        idx = -1
        for i, (t, _text, _trans) in enumerate(self._lines):
            if t <= pos_ms:
                idx = i
            else:
                break
        return idx

    def _refresh(self, first=False):
        if not self._lines:
            self.current_label.setText("♪ 暂无歌词")
            self.translation_label.setText("")
            self.translation_label.setVisible(False)
            self.next_label.setText("")
            return

        index = self._current_index
        if index < 0:
            self.current_label.setText("♪ 准备播放")
            translation = ""
            self.next_label.setText(self._lines[0][1])
        else:
            self.current_label.setText(self._lines[index][1])
            translation = self._lines[index][2]
            self.next_label.setText(
                self._lines[index + 1][1] if index + 1 < len(self._lines) else ""
            )

        # 当前句有译文时额外显示一行，否则让出空间给当前句/下一句
        self.translation_label.setText(translation)
        self.translation_label.setVisible(bool(translation))

        if not first:
            self._fade.stop()
            self._fade.start()

    # ================== 样式 ==================

    def set_font_size(self, size):
        size = max(self.MIN_FONT_SIZE, min(self.MAX_FONT_SIZE, int(size)))
        if size == self._font_size:
            return
        self._font_size = size
        self._apply_font()
        self.style_changed.emit(self._font_size, self._color.name())

    def set_color(self, color):
        color = QColor(color)
        if not color.isValid() or color.name() == self._color.name():
            return
        self._color = color
        self.current_label.set_text_color(color)
        self.style_changed.emit(self._font_size, self._color.name())

    def _apply_font(self):
        current = QFont("Microsoft YaHei UI", self._font_size)
        current.setBold(True)
        self.current_label.setFont(current)

        smaller = max(10, int(self._font_size * 0.66))
        translation = QFont("Microsoft YaHei UI", smaller)
        self.translation_label.setFont(translation)

        upcoming = QFont("Microsoft YaHei UI", max(10, int(self._font_size * 0.62)))
        self.next_label.setFont(upcoming)

        # 预留"原句 + 译文 + 下一句"三行的高度，避免出现译文时窗口跳动
        height = max(96, int(self._font_size * 3.05) + 26)
        self.resize(max(360, self.width()), height)

    # ================== 锁定 / 位置 ==================

    def is_locked(self):
        return self._locked

    def set_locked(self, locked):
        locked = bool(locked)
        if locked == self._locked:
            return
        self._locked = locked
        self.setAttribute(Qt.WA_TransparentForMouseEvents, locked)
        self.setWindowFlag(Qt.WindowTransparentForInput, locked)
        # 修改窗口标志会重建原生窗口，必须重新应用透明属性并显示
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.show()
        self.lock_changed.emit(locked)

    def move_to_default(self):
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.move(area.center().x() - self.width() // 2,
                  area.bottom() - self.height() - 80)

    def _screen_area(self):
        screen = QGuiApplication.screenAt(self.geometry().center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _clamp_to_screen(self):
        # 用 geometry() 而不是 frameGeometry()：无边框窗口的 frameGeometry 在 Windows
        # 上会多出不可见的窗口边框（实测 +24px），存下来再恢复会让窗口每次启动都变大
        rect = self.geometry()
        area = self._screen_area()
        x = max(area.left(), min(rect.left(), area.right() - rect.width()))
        y = max(area.top(), min(rect.top(), area.bottom() - rect.height()))
        if (x, y) != (rect.left(), rect.top()):
            self.move(x, y)

    # ================== 状态持久化 ==================

    def get_state(self):
        rect = self.geometry()
        return {
            "enabled": self.isVisible(),
            "locked": self._locked,
            "x": rect.x(),
            "y": rect.y(),
            "w": rect.width(),
            "h": rect.height(),
            "font_size": self._font_size,
            "color": self._color.name(),
        }

    def restore_state(self, state):
        if not isinstance(state, dict):
            self.move_to_default()
            return
        self.set_font_size(state.get("font_size", self.DEFAULT_FONT_SIZE))
        self.set_color(state.get("color", self.DEFAULT_COLOR))
        self.resize(max(320, int(state.get("w") or self.DEFAULT_SIZE[0])),
                    max(70, int(state.get("h") or self.DEFAULT_SIZE[1])))

        x, y = state.get("x"), state.get("y")
        if isinstance(x, int) and isinstance(y, int):
            self.move(x, y)
            self._clamp_to_screen()
        else:
            self.move_to_default()

        if state.get("locked"):
            self.set_locked(True)

    # ================== 交互 ==================

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._locked:
            self._drag_offset = event.globalPos() - self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPos() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_offset is not None:
            self._drag_offset = None
            self._clamp_to_screen()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击锁定：锁定后交给主界面按钮解锁"""
        if event.button() == Qt.LeftButton and not self._locked:
            self.set_locked(True)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if self._locked:
            return

        menu = QMenu(self)

        font_menu = menu.addMenu("字号")
        act = font_menu.addAction("增大")
        act.triggered.connect(lambda: self.set_font_size(self._font_size + 2))
        act = font_menu.addAction("减小")
        act.triggered.connect(lambda: self.set_font_size(self._font_size - 2))
        act = font_menu.addAction("恢复默认")
        act.triggered.connect(lambda: self.set_font_size(self.DEFAULT_FONT_SIZE))

        color_menu = menu.addMenu("颜色")
        for name, value in (("白色", "#ffffff"), ("粉色", "#f9a8d4"),
                            ("天蓝", "#93c5fd"), ("鹅黄", "#fde68a"),
                            ("浅绿", "#86efac")):
            act = color_menu.addAction(name)
            act.triggered.connect(lambda _checked=False, v=value: self.set_color(v))

        menu.addSeparator()
        act = menu.addAction("锁定（鼠标穿透）")
        act.triggered.connect(lambda: self.set_locked(True))
        act = menu.addAction("回到默认位置")
        act.triggered.connect(self.move_to_default)

        menu.addSeparator()
        act = menu.addAction("关闭桌面歌词")
        act.triggered.connect(self._request_close)

        menu.exec_(event.globalPos())

    def _request_close(self):
        self.hide()
        self.closed.emit()

    def closeEvent(self, event):
        """关闭时只隐藏，不影响主程序退出流程"""
        event.ignore()
        self._request_close()
