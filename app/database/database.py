"""SQLite 连接管理与数据库初始化 / 迁移。"""
from __future__ import annotations

import os
import sqlite3
from threading import local

from app.database import models

# 数据库文件存放位置:用户目录下,避免随项目移动丢失
DB_DIR = os.path.join(os.path.expanduser("~"), ".college_finance")
DB_PATH = os.path.join(DB_DIR, "finance.db")

_local = local()


def _connect() -> sqlite3.Connection:
    """每个线程一个连接。开启外键约束 + WAL。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(DB_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        _local.conn = conn
    return conn


def get_connection() -> sqlite3.Connection:
    return _connect()


def get_db_path() -> str:
    return DB_PATH


def init_db() -> None:
    """创建表、写入默认数据、执行迁移。幂等可重复调用。"""
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(models.SCHEMA_SQL)

    # 默认分类(仅在 categories 表为空时插入)
    row = cur.execute("SELECT COUNT(*) AS c FROM categories").fetchone()
    if row["c"] == 0:
        order_idx = 0
        for name, icon in models.DEFAULT_EXPENSE_CATEGORIES:
            cur.execute(
                "INSERT INTO categories(name,icon,type,is_default,sort_order) "
                "VALUES(?,?,?,?,?)",
                (name, icon, "expense", 1, order_idx),
            )
            order_idx += 1
        order_idx = 0
        for name, icon in models.DEFAULT_INCOME_CATEGORIES:
            cur.execute(
                "INSERT INTO categories(name,icon,type,is_default,sort_order) "
                "VALUES(?,?,?,?,?)",
                (name, icon, "income", 1, order_idx),
            )
            order_idx += 1

    # 默认预算(仅在 budgets 表为空时插入):2500,自然月
    row = cur.execute("SELECT COUNT(*) AS c FROM budgets").fetchone()
    if row["c"] == 0:
        cur.execute(
            "INSERT INTO budgets(amount,period_type,start_day,is_active) "
            "VALUES(2500,'natural_month',1,1)"
        )

    # 默认设置项
    cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('schema_version', ?)",
                (str(models.SCHEMA_VERSION),))
    cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('first_run','1')")

    conn.commit()
