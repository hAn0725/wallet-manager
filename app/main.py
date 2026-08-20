"""程序入口。

运行方式(任选其一):
  uv run python -m app.main
  uv run python app/main.py
  Windows 双击 启动.bat
"""
from __future__ import annotations

import os
import sys

# 让 `python app/main.py` 也能正确导入 app 包(把项目根加入 sys.path)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PySide6.QtWidgets import QApplication

from app.database.database import init_db
from app.ui.main_window import MainWindow


def main():
    # 初始化数据库(幂等)
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("大学生个人财务管理助手")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
