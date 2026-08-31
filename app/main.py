"""程序入口。

运行方式(任选其一):
  uv run python -m app.main
  uv run python app/main.py
  Windows 双击 启动.bat
"""
from __future__ import annotations

import logging
import os
import sys

# 让 `python app/main.py` 也能正确导入 app 包(把项目根加入 sys.path)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PySide6.QtWidgets import QApplication

from app.database.database import init_db
from app.ui.main_window import MainWindow

# ---- 启动计时探针(仅当 CFA_PROFILE_STARTUP=1 时生效,正常使用零影响)----
_PROFILE = os.environ.get("CFA_PROFILE_STARTUP") == "1"
_PROFILE_T0 = __import__("time").perf_counter()


def _ptag(tag: str) -> None:
    if _PROFILE:
        ms = (__import__("time").perf_counter() - _PROFILE_T0) * 1000
        print(f"[profile] {tag} {ms:.1f}ms", flush=True)


# 单实例 mutex 句柄(保持引用防止 GC,进程退出时 OS 自动释放)
_SINGLE_INSTANCE_MUTEX = None


def _ensure_single_instance() -> bool:
    """单实例锁:Windows named mutex。已有实例运行时激活其窗口并返回 False。"""
    global _SINGLE_INSTANCE_MUTEX
    if sys.platform != "win32":
        return True  # 非 Windows 不做单实例锁
    import ctypes
    kernel32 = ctypes.windll.kernel32
    mutex_name = "Global\\CollegeFinanceAssistant_v1"
    _SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, mutex_name)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        # 已有实例:查找并激活其主窗口
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "大学生个人财务管理助手")
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
        return False
    return True


def main():
    # 单实例锁:防止重复双击快捷方式启动多个实例
    if not _ensure_single_instance():
        return 0  # 已有实例,本实例退出

    # 日志(失败不影响启动)+ 初始化数据库(幂等;损坏时自动从最近备份恢复)
    try:
        from app.utils.logging_setup import setup_logging, install_excepthook
        setup_logging()
        install_excepthook()
    except Exception:
        pass
    logging.getLogger("main").info("应用启动")
    init_db()
    _ptag("db_ready")
    # 每 7 天自动备份一次(保留最近 5 个);备份失败绝不影响启动
    try:
        from app.services.settings_service import auto_backup
        path = auto_backup()
        if path:
            logging.getLogger("backup").info("自动备份完成: %s", path)
    except Exception:
        logging.getLogger("backup").exception("自动备份失败")

    app = QApplication(sys.argv)
    app.setApplicationName("大学生个人财务管理助手")

    window = MainWindow()
    _ptag("window_created")
    window.show()
    _ptag("window_shown")
    if _PROFILE:
        # 首屏事件处理完成后打点,并自动退出,便于独立进程测温
        app.processEvents()
        _ptag("dashboard_ready")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
