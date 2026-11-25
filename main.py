#!/usr/bin/env python3
"""
音乐播放器 - 主程序入口
"""
import sys
import os

# 【关键】强制 Qt 使用 Windows Media Foundation 后端
# WMF 在 Windows 10/11 中自带 FLAC/AAC 等解码器支持
os.environ['QT_MULTIMEDIA_PREFERRED_PLUGINS'] = 'windowsmediafoundation'

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from src.gui.main_ui import MainWindow


def _set_windows_app_id():
    """声明本进程的应用标识

    Windows 任务栏按 AppUserModelID 归组并决定显示哪个图标。用 python.exe 启动时
    不设置它，任务栏会显示 Python 的图标。必须在创建任何窗口之前调用。
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "MusicPlayer.Desktop.1")
    except Exception:
        pass


def _app_icon_path():
    """应用图标路径（多尺寸 ICO）"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'src', 'resources', 'icons', 'app.ico')


def main():
    """程序主入口"""
    try:
        _set_windows_app_id()

        # 创建应用
        app = QApplication(sys.argv)
        app.setApplicationName("MusicPlayer")
        app.setApplicationDisplayName("音乐播放器")

        # 任务栏 / 标题栏 / Alt-Tab 图标（Qt 会按场景从多尺寸 ICO 里挑合适的）
        icon_path = _app_icon_path()
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
        else:
            print(f"[警告] 找不到应用图标: {icon_path}")
        
        # 创建主窗口
        window = MainWindow()
        window.show()
        
        # 运行应用
        return app.exec_()
        
    except Exception as e:
        print(f"程序启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())