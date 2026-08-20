"""记账 / 账单 / 余额 —— 面向交易记录的核心数据操作。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.database.database import get_connection
from app.utils.helpers import iso, parse_money, round2, today, to_date


@dataclass
class Transaction:
    id: Optional[int]
    amount: float
    category_id: Optional[int]
    type: str            # 'income' / 'expense'
    date: str            # YYYY-MM-DD
    note: str
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_expense(self) -> bool:
        return self.type == "expense"


# ---------------------------------------------------------------------------
# 新增 / 修改 / 删除
# ---------------------------------------------------------------------------

def add_transaction(amount, category_id, type_: str, date, note: str = "") -> int:
    """新增账单,返回新 id。amount 接受数字或字符串。

    category_id 允许为 None(未分类),但若提供则必须指向真实存在的分类。
    """
    amt = parse_money(amount) if not isinstance(amount, (int, float)) else round2(amount)
    if amt <= 0:
        raise ValueError("金额必须大于 0")
    if type_ not in ("income", "expense"):
        raise ValueError("类型必须是 income 或 expense")
    if category_id is not None and not _category_exists(category_id):
        raise ValueError("分类不存在")
    d = iso(to_date(date))
    note = (note or "").strip()
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO transactions(amount,category_id,type,date,note) VALUES(?,?,?,?,?)",
        (amt, category_id, type_, d, note),
    )
    conn.commit()
    return cur.lastrowid


def update_transaction(tid: int, amount, category_id, type_: str, date, note: str = "") -> None:
    amt = parse_money(amount) if not isinstance(amount, (int, float)) else round2(amount)
    if amt <= 0:
        raise ValueError("金额必须大于 0")
    if type_ not in ("income", "expense"):
        raise ValueError("类型必须是 income 或 expense")
    if category_id is not None and not _category_exists(category_id):
        raise ValueError("分类不存在")
    if get_transaction(tid) is None:
        raise ValueError("账单不存在")
    d = iso(to_date(date))
    note = (note or "").strip()
    conn = get_connection()
    conn.execute(
        "UPDATE transactions SET amount=?,category_id=?,type=?,date=?,note=?, "
        "updated_at=datetime('now','localtime') WHERE id=?",
        (amt, category_id, type_, d, note, tid),
    )
    conn.commit()


def _category_exists(category_id: int) -> bool:
    """轻量级外键前置校验,避免写入孤立 category_id。"""
    row = get_connection().execute(
        "SELECT 1 FROM categories WHERE id=?", (category_id,)
    ).fetchone()
    return row is not None


def delete_transaction(tid: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM transactions WHERE id=?", (tid,))
    conn.commit()


def get_transaction(tid: int) -> Optional[Transaction]:
    row = get_connection().execute(
        "SELECT * FROM transactions WHERE id=?", (tid,)
    ).fetchone()
    return _row_to_txn(row) if row else None


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def _row_to_txn(row) -> Transaction:
    return Transaction(
        id=row["id"], amount=row["amount"], category_id=row["category_id"],
        type=row["type"], date=row["date"], note=row["note"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def get_transactions(type_filter: Optional[str] = None,
                     category_id: Optional[int] = None,
                     start_date=None,
                     end_date=None,
                     keyword: str = "",
                     limit: int = 0) -> list[Transaction]:
    """按条件查询账单,按日期降序、id 降序排列。"""
    sql = "SELECT * FROM transactions WHERE 1=1"
    params: list = []
    if type_filter:
        sql += " AND type=?"
        params.append(type_filter)
    if category_id is not None:
        sql += " AND category_id=?"
        params.append(category_id)
    if start_date is not None:
        sql += " AND date>=?"
        params.append(iso(to_date(start_date)))
    if end_date is not None:
        sql += " AND date<=?"
        params.append(iso(to_date(end_date)))
    if keyword:
        sql += " AND note LIKE ?"
        params.append(f"%{keyword.strip()}%")
    sql += " ORDER BY date DESC, id DESC"
    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    rows = get_connection().execute(sql, params).fetchall()
    return [_row_to_txn(r) for r in rows]


def sum_by_type(start_date, end_date, type_: str) -> float:
    """区间内某类型(收入/支出)的金额合计。"""
    rows = get_connection().execute(
        "SELECT COALESCE(SUM(amount),0) AS s FROM transactions "
        "WHERE type=? AND date>=? AND date<=?",
        (type_, iso(to_date(start_date)), iso(to_date(end_date))),
    ).fetchone()
    return round2(rows["s"])


def get_cycle_spent(start_date, end_date) -> float:
    return sum_by_type(start_date, end_date, "expense")


def get_cycle_income(start_date, end_date) -> float:
    return sum_by_type(start_date, end_date, "income")


def get_today_spent(ref=None) -> float:
    d = iso(ref or today())
    rows = get_connection().execute(
        "SELECT COALESCE(SUM(amount),0) AS s FROM transactions "
        "WHERE type='expense' AND date=?", (d,)
    ).fetchone()
    return round2(rows["s"])


def get_total_balance() -> float:
    """累计余额 = 全部收入 - 全部支出。"""
    rows = get_connection().execute(
        "SELECT "
        "COALESCE((SELECT SUM(amount) FROM transactions WHERE type='income'),0) "
        "- COALESCE((SELECT SUM(amount) FROM transactions WHERE type='expense'),0) AS b"
    ).fetchone()
    return round2(rows["b"])


def get_category_lookup() -> dict:
    """{id: (name, icon, type)} 用于列表展示。"""
    rows = get_connection().execute(
        "SELECT id,name,icon,type FROM categories ORDER BY sort_order, id"
    ).fetchall()
    return {r["id"]: (r["name"], r["icon"], r["type"]) for r in rows}
