"""应用设置键值存取 + 数据导入导出 / 备份恢复。"""
from __future__ import annotations

import csv
import io
import json
import os
import shutil
from datetime import datetime
from typing import Optional

from app.database.database import DB_PATH, get_connection


# ---------------------------------------------------------------------------
# 设置键值
# ---------------------------------------------------------------------------

def get_setting(key: str, default=None):
    row = get_connection().execute(
        "SELECT value FROM settings WHERE key=?", (key,)
    ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    conn.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))
    conn.commit()


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

def export_json(path: str) -> int:
    """导出全库为 JSON,返回记录数(账单条数)。"""
    conn = get_connection()
    data = {
        "version": 1,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "categories": [dict(r) for r in conn.execute("SELECT * FROM categories ORDER BY id")],
        "transactions": [dict(r) for r in conn.execute("SELECT * FROM transactions ORDER BY id")],
        "budgets": [dict(r) for r in conn.execute("SELECT * FROM budgets ORDER BY id")],
        "savings_goals": [dict(r) for r in conn.execute("SELECT * FROM savings_goals ORDER BY id")],
        "settings": [dict(r) for r in conn.execute("SELECT * FROM settings")],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(data["transactions"])


def export_csv(path: str) -> int:
    """仅导出账单为 CSV(便于用 Excel 查看)。"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT t.id, t.date, t.type, t.amount,
               COALESCE(c.name,'') AS category, t.note, t.created_at
        FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
        ORDER BY t.date DESC, t.id DESC
        """
    ).fetchall()
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "日期", "类型", "金额", "分类", "备注", "创建时间"])
        for r in rows:
            w.writerow([
                r["id"], r["date"],
                "收入" if r["type"] == "income" else "支出",
                round(r["amount"], 2), r["category"], r["note"], r["created_at"],
            ])
    return len(rows)


# ---------------------------------------------------------------------------
# 导入
# ---------------------------------------------------------------------------

def import_json(path: str, mode: str = "merge") -> int:
    """从 JSON 导入。mode:
       'merge' —— 按 id 存在则更新,不存在则插入;
       'replace' —— 清空目标表后全量导入。
    返回导入账单条数。
    """
    if mode not in ("merge", "replace"):
        raise ValueError("mode 必须是 merge 或 replace")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("JSON 格式不正确:根对象应为对象")

    conn = get_connection()
    try:
        if mode == "replace":
            for tbl in ("transactions", "categories", "budgets", "savings_goals"):
                conn.execute(f"DELETE FROM {tbl}")

        def upsert(table, cols, row_dict, conflict_col="id"):
            cols_sql = ", ".join(cols)
            ph = ", ".join("?" for _ in cols)
            vals = [row_dict.get(c) for c in cols]
            conn.execute(
                f"INSERT INTO {table}({cols_sql}) VALUES({ph}) "
                f"ON CONFLICT({conflict_col}) DO UPDATE SET "
                + ", ".join(f"{c}=excluded.{c}" for c in cols if c != conflict_col),
                vals,
            )

        for r in data.get("categories", []):
            upsert("categories",
                   ["id", "name", "icon", "type", "is_default", "sort_order", "created_at"], r)
        for r in data.get("transactions", []):
            upsert("transactions",
                   ["id", "amount", "category_id", "type", "date", "note",
                    "created_at", "updated_at"], r)
        for r in data.get("budgets", []):
            upsert("budgets",
                   ["id", "amount", "period_type", "start_day", "is_active",
                    "created_at", "updated_at"], r)
        for r in data.get("savings_goals", []):
            upsert("savings_goals",
                   ["id", "name", "target_amount", "current_amount", "note",
                    "created_at", "updated_at"], r)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(data.get("transactions", []))


# ---------------------------------------------------------------------------
# 备份 / 恢复
# ---------------------------------------------------------------------------

def backup_database(dest_path: str) -> str:
    """复制数据库文件到目标路径。返回实际路径。"""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError("数据库文件不存在")
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    shutil.copy2(DB_PATH, dest_path)
    # WAL/SHM 可能含未提交内容,使用在线备份更稳妥
    return dest_path


def backup_via_sqlite(dest_path: str) -> str:
    """用 SQLite 在线备份 API(确保 WAL 已落盘),更可靠。"""
    import sqlite3
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    src = get_connection()
    dst = sqlite3.connect(dest_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
    return dest_path


def restore_database(src_path: str) -> None:
    """从备份恢复:用备份覆盖当前库。调用前需让其他连接关闭。
    本应用使用线程局部连接,恢复后重建数据库会丢弃旧连接缓存。"""
    import sqlite3
    if not os.path.exists(src_path):
        raise FileNotFoundError("备份文件不存在")
    # 先验证备份是合法 sqlite 库
    test = sqlite3.connect(src_path)
    try:
        test.execute("SELECT name FROM sqlite_master LIMIT 1")
    except sqlite3.DatabaseError as e:
        raise ValueError(f"备份文件不是有效的数据库: {e}")
    finally:
        test.close()

    # 关闭当前连接,再覆盖文件
    from app.database.database import _local
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
    shutil.copy2(src_path, DB_PATH)


def get_db_path() -> str:
    return DB_PATH
