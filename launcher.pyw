# -*- coding: utf-8 -*-
"""
启动器（供桌面/开始菜单快捷方式使用）

为什么需要它：
    Explorer 从快捷方式拉起进程时，会给该进程强加一个"快捷方式派生"的
    AppUserModelID；此时程序内部再调用 SetCurrentProcessExplicitAppUserModelID
    无法覆盖它，任务栏就查不到我们在注册表里登记的图标，只能显示默认图标。
    这里改为"由本启动器再以分离进程方式拉起主程序"，主程序就没有被强加的
    AppUserModelID，内部设置生效，任务栏图标正常。

   快捷方式配置（pythonw.exe 启动，无控制台窗口）：
       目标: <Python 环境>\\pythonw.exe
       参数: "<项目目录>\\launcher.pyw"
       起始位置: <项目目录>
       图标: <项目目录>\\src\\resources\\icons\\app.ico
"""

import os
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_SCRIPT = os.path.join(PROJECT_DIR, "main.py")

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def _pythonw():
    """优先用 pythonw.exe，避免拉起主程序时闪出控制台窗口"""
    candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(candidate):
        return candidate
    return sys.executable


def main():
    subprocess.Popen(
        [_pythonw(), MAIN_SCRIPT],
        cwd=PROJECT_DIR,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
