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

def main():
    """程序主入口"""
    try:
        # 创建应用
        app = QApplication(sys.argv)
        app.setApplicationName("MusicPlayer")
        app.setApplicationDisplayName("音乐播放器")
        
        # 设置窗口图标（可选，需要先创建图标文件）
        # icon_path = os.path.join("src", "resources", "icons", "app_icon.ico")
        # if os.path.exists(icon_path):
        #     app.setWindowIcon(QIcon(icon_path))
        
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