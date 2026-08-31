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
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
        except sqlite3.DatabaseError:
            # 文件损坏等:关闭坏连接再抛出,避免在 Windows 上锁住文件
            try:
                conn.close()
            except Exception:
                pass
            raise
        _local.conn = conn
    return conn


def get_connection() -> sqlite3.Connection:
    return _connect()


def init_db() -> None:
    """创建表、写入默认数据、执行迁移。幂等可重复调用。
    数据库损坏时自动尝试从最近的有效自动备份恢复,保证历史数据不丢。"""
    try:
        conn = get_connection()
        check = conn.execute("PRAGMA integrity_check").fetchone()
        if check is None or check[0] != "ok":
            import logging
            recovered = _recover_from_backup()
            logging.getLogger("database").warning(
                "数据库损坏,尝试从备份恢复: %s", "成功" if recovered else "无有效备份,重建空库")
            conn = get_connection()
    except sqlite3.DatabaseError:
        import logging
        recovered = _recover_from_backup()
        logging.getLogger("database").warning(
            "数据库异常,尝试从备份恢复: %s", "成功" if recovered else "无有效备份,重建空库")
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


def _close() -> None:
    """关闭当前线程连接。"""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None


def _recover_from_backup() -> bool:
    """数据库损坏时,用最近的有效自动备份覆盖当前库。
    无有效备份则删除损坏文件,让 init 重建空库(至少不崩溃)。"""
    import glob
    import shutil
    _close()
    bak_dir = os.path.join(DB_DIR, "backups")
    baks = sorted(glob.glob(os.path.join(bak_dir, "autobackup_*.db")), reverse=True)
    for bak in baks:
        try:
            test = sqlite3.connect(bak)
            ok = test.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            test.close()
            if ok:
                # 清理侧文件后覆盖,避免旧 WAL 作用到恢复出的新库上
                for ext in ("", "-wal", "-shm"):
                    p = DB_PATH + ext
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except OSError:
                            pass
                shutil.copy2(bak, DB_PATH)
                return True
        except sqlite3.DatabaseError:
            continue
    # 无有效备份:移除损坏文件,重建空库(用户至少能继续使用)
    for ext in ("", "-wal", "-shm"):
        p = DB_PATH + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    return False
