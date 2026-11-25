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


APP_USER_MODEL_ID = "MusicPlayer.Desktop.1"
APP_DISPLAY_NAME = "音乐播放器"


def _set_windows_app_id():
    """声明本进程的应用标识

    Windows 任务栏按 AppUserModelID 归组并决定显示哪个图标。用 python.exe 启动时
    不设置它，任务栏会把它当成 Python 进程。必须在创建任何窗口之前调用。
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def _register_taskbar_icon(icon_path):
    """把任务栏图标登记到 AppUserModelID 名下（仅写 HKCU，不需要管理员）

    只调用 setWindowIcon() 能改标题栏和 Alt-Tab 图标，但**任务栏**按钮用的是
    AppUserModelID 关联的图标；不登记就会回退到 python.exe 的图标。
    """
    if sys.platform != 'win32' or not icon_path:
        return False
    try:
        import winreg
    except Exception:
        return False

    key_path = r"Software\Classes\AppUserModelId\%s" % APP_USER_MODEL_ID
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_DISPLAY_NAME)
            winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, icon_path)
            # 固定到任务栏后从固定项启动时用得到（缺了会退化成启动 python.exe）
            entry_script = os.path.abspath(__file__)
            interpreter = sys.executable or ""
            pythonw = os.path.join(os.path.dirname(interpreter), "pythonw.exe")
            if os.path.exists(pythonw):
                interpreter = pythonw
            if interpreter and entry_script:
                winreg.SetValueEx(key, "RelaunchCommand", 0, winreg.REG_SZ,
                                  f'"{interpreter}" "{entry_script}"')
                winreg.SetValueEx(key, "RelaunchIconResource", 0, winreg.REG_SZ, icon_path)
                winreg.SetValueEx(key, "RelaunchDisplayNameResource", 0, winreg.REG_SZ,
                                  APP_DISPLAY_NAME)
        return True
    except Exception as e:
        print(f"[警告] 注册任务栏图标失败: {e}")
        return False


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
        app.setApplicationDisplayName(APP_DISPLAY_NAME)

        # 标题栏 / Alt-Tab 图标（Qt 会按场景从多尺寸 ICO 里挑合适的）
        icon_path = _app_icon_path()
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            _register_taskbar_icon(icon_path)
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