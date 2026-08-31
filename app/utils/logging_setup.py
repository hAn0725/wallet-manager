"""轻量滚动日志。

- 位置: ~/.college_finance/logs/app.log
- 大小轮转:单个 1MB,最多保留 3 份(backupCount=3),不会无限增长
- 不记录密码等敏感信息;默认 INFO 级,平时无额外开销
- 记录:启动、数据库错误/恢复、自动备份、导入导出错误、未捕获异常
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """初始化根日志(幂等)。建议在程序入口调用一次。"""
    global _configured
    if _configured:
        return
    try:
        from app.database.database import DB_DIR
        log_dir = os.path.join(DB_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)
        handler = RotatingFileHandler(
            os.path.join(log_dir, "app.log"),
            maxBytes=1_000_000, backupCount=3, encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root = logging.getLogger()
        root.setLevel(level)
        root.addHandler(handler)
    except Exception:
        # 日志失败绝不能影响程序启动
        pass
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def install_excepthook() -> None:
    """未捕获异常写入日志,避免静默丢失(不阻止程序行为)。"""
    def _hook(etype, value, tb):
        logging.getLogger("uncaught").error(
            "未捕获异常", exc_info=(etype, value, tb))
        # 仍然调用默认钩子,保留原行为
        sys.__excepthook__(etype, value, tb)
    sys.excepthook = _hook