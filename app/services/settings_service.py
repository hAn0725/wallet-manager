"""应用设置键值存取 + 数据导入导出 / 备份恢复。"""
from __future__ import annotations

import csv
import glob
import json
import os
import shutil
from datetime import datetime

from app.database.database import get_connection


def _db_path() -> str:
    """运行时读取数据库路径(避免 import 时快照,支持测试动态切换 DB 位置)。"""
    from app.database.database import DB_PATH
    return DB_PATH

# 常用记账模板默认值:{icon, label, type, category, note}
DEFAULT_TEMPLATES = [
    {"icon": "🍜", "label": "午饭", "type": "expense", "category": "餐饮", "note": "午饭"},
    {"icon": "🧋", "label": "奶茶", "type": "expense", "category": "餐饮", "note": "奶茶"},
    {"icon": "🚇", "label": "地铁", "type": "expense", "category": "交通", "note": "地铁"},
    {"icon": "🛒", "label": "购物", "type": "expense", "category": "购物", "note": "购物"},
]


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
# 常用记账模板(轻量:存 settings JSON,不建新表)
# ---------------------------------------------------------------------------

def get_templates() -> list[dict]:
    """返回常用记账模板列表,首次使用默认模板。"""
    raw = get_setting("quick_templates", None)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
        except (ValueError, TypeError):
            pass
    # 首次使用:写入默认模板
    save_templates(DEFAULT_TEMPLATES)
    return list(DEFAULT_TEMPLATES)


def save_templates(templates: list[dict]) -> None:
    set_setting("quick_templates", json.dumps(templates, ensure_ascii=False))


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

def export_json(path: str) -> int:
    """导出全库为 JSON,返回记录数(账单条数)。"""
    conn = get_connection()
    data = {
        "version": 2,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "categories": [dict(r) for r in conn.execute("SELECT * FROM categories ORDER BY id")],
        "transactions": [dict(r) for r in conn.execute("SELECT * FROM transactions ORDER BY id")],
        "budgets": [dict(r) for r in conn.execute("SELECT * FROM budgets ORDER BY id")],
        "savings_goals": [dict(r) for r in conn.execute("SELECT * FROM savings_goals ORDER BY id")],
        "recurring": [dict(r) for r in conn.execute("SELECT * FROM recurring ORDER BY id")],
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

    兼容 v1 导出文件；v2 起额外包含固定收支与应用设置。
    返回导入账单条数。
    """
    if mode not in ("merge", "replace"):
        raise ValueError("mode 必须是 merge 或 replace")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("JSON 格式不正确:根对象应为对象")
    for key in ("categories", "transactions", "budgets", "savings_goals", "recurring", "settings"):
        if key in data and not isinstance(data[key], list):
            raise ValueError(f"JSON 格式不正确:{key} 应为数组")

    conn = get_connection()
    try:
        if mode == "replace":
            # 先删引用分类的表，再删分类，避免外键把中间状态变成未分类。
            for tbl in ("transactions", "recurring", "categories", "budgets", "savings_goals", "settings"):
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
        for r in data.get("recurring", []):
            upsert("recurring",
                   ["id", "name", "amount", "type", "category_id", "day_of_month",
                    "note", "enabled", "last_applied", "created_at", "updated_at"], r)
        for r in data.get("settings", []):
            upsert("settings", ["key", "value"], r, conflict_col="key")
        # v1 文件没有 settings；补回应用运行所需的基础键。
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('schema_version', '1')")
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('first_run', '1')")
        conn.commit()
    except Exception:
        import logging
        logging.getLogger("data").exception("导入失败: %s", path)
        conn.rollback()
        raise
    return len(data.get("transactions", []))


# ---------------------------------------------------------------------------
# 备份 / 恢复
# ---------------------------------------------------------------------------

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


def _remove_sidecars(path: str) -> None:
    """删除数据库的 WAL/SHM 侧文件(恢复/覆盖前必须清理,否则旧 WAL 会作用到新文件)。"""
    for ext in ("-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


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

    # 关闭当前连接,清理侧文件,再覆盖文件
    from app.database.database import _local
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
    _remove_sidecars(_db_path())
    shutil.copy2(src_path, _db_path())


def get_db_path() -> str:
    return _db_path()


# ---------------------------------------------------------------------------
# 自动备份(每 7 天一次,保留最近 5 个,不影响启动速度)
# ---------------------------------------------------------------------------

AUTO_BACKUP_KEEP = 5
AUTO_BACKUP_INTERVAL_DAYS = 7


def get_backup_dir() -> str:
    d = os.path.join(os.path.dirname(_db_path()), "backups")
    os.makedirs(d, exist_ok=True)
    return d


def list_backups() -> list[str]:
    """按新到旧列出自动备份文件。"""
    return sorted(glob.glob(os.path.join(get_backup_dir(), "autobackup_*.db")), reverse=True)


def auto_backup(force: bool = False) -> str | None:
    """每次启动时调用:距上次备份 >= 7 天才备份,保留最近 5 个。

    空库不备份(避免刚初始化就白备份),但会记录时间避免反复尝试。
    force=True 跳过节流(用于备份/恢复前后)。
    返回备份路径;未执行返回 None。
    """
    last = get_setting("last_auto_backup")
    now = datetime.now().date()
    # 节流只在非强制时生效(否则连点「立即备份」会被 7 天限制挡住)
    if not force and last:
        try:
            if (now - datetime.fromisoformat(last).date()).days < AUTO_BACKUP_INTERVAL_DAYS:
                return None
        except (ValueError, TypeError):
            pass
    # 空库不备份
    conn = get_connection()
    cnt = conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
    if cnt == 0 and not force:
        set_setting("last_auto_backup", now.isoformat())
        return None
    path = backup_via_sqlite(os.path.join(
        get_backup_dir(),
        f"autobackup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
    ))
    _prune_backups(AUTO_BACKUP_KEEP)
    set_setting("last_auto_backup", now.isoformat())
    return path


def _prune_backups(keep: int) -> None:
    for old in list_backups()[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass
