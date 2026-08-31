"""固定周期收支 —— 生活费/话费/订阅等周期性收支的到期提醒与一键记账。

设计:不自动创建账单(避免数据意外),而是在首页温和提醒到期项,
由用户一键「记入」生成账单。每项每月最多提醒一次(记入后本月不再提醒)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.database.database import get_connection
from app.services import finance_service
from app.utils.helpers import round2, safe_date, today


@dataclass
class Recurring:
    id: Optional[int]
    name: str
    amount: float
    type: str               # 'income' / 'expense'
    category_id: Optional[int]
    day_of_month: int
    note: str
    enabled: bool
    last_applied: Optional[str]   # 'YYYY-MM'


def _row(r) -> Recurring:
    return Recurring(
        id=r["id"], name=r["name"], amount=round2(r["amount"]),
        type=r["type"], category_id=r["category_id"],
        day_of_month=r["day_of_month"], note=r["note"] or "",
        enabled=bool(r["enabled"]), last_applied=r["last_applied"],
    )


def list_recurring(enabled_only: bool = False) -> list[Recurring]:
    sql = "SELECT * FROM recurring"
    if enabled_only:
        sql += " WHERE enabled=1"
    sql += " ORDER BY type, day_of_month, id"
    return [_row(r) for r in get_connection().execute(sql).fetchall()]


def get_recurring(rid: int) -> Optional[Recurring]:
    row = get_connection().execute("SELECT * FROM recurring WHERE id=?", (rid,)).fetchone()
    return _row(row) if row else None


def add_recurring(name, amount, type_, category_id, day_of_month, note="") -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("名称不能为空")
    amount = round2(amount)
    if amount <= 0:
        raise ValueError("金额必须大于 0")
    if type_ not in ("income", "expense"):
        raise ValueError("类型必须是 income 或 expense")
    if not (1 <= int(day_of_month) <= 28):
        raise ValueError("日期必须在 1~28 号之间(避免月末天数不一)")
    finance_service._validate_category_for_type(category_id, type_)
    conn = get_connection()
    rid = conn.execute(
        "INSERT INTO recurring(name,amount,type,category_id,day_of_month,note) "
        "VALUES(?,?,?,?,?,?)",
        (name, amount, type_, category_id, int(day_of_month), note or ""),
    ).lastrowid
    conn.commit()
    return rid


def update_recurring(rid, name, amount, type_, category_id, day_of_month, note=""):
    r = get_recurring(rid)
    if r is None:
        raise ValueError("项目不存在")
    name = (name or "").strip()
    if not name:
        raise ValueError("名称不能为空")
    amount = round2(amount)
    if amount <= 0:
        raise ValueError("金额必须大于 0")
    if type_ not in ("income", "expense"):
        raise ValueError("类型必须是 income 或 expense")
    if not (1 <= int(day_of_month) <= 28):
        raise ValueError("日期必须在 1~28 号之间")
    finance_service._validate_category_for_type(category_id, type_)
    conn = get_connection()
    conn.execute(
        "UPDATE recurring SET name=?,amount=?,type=?,category_id=?,day_of_month=?,note=?, "
        "updated_at=datetime('now','localtime') WHERE id=?",
        (name, amount, type_, category_id, int(day_of_month), note or "", rid),
    )
    conn.commit()


def delete_recurring(rid):
    conn = get_connection()
    conn.execute("DELETE FROM recurring WHERE id=?", (rid,))
    conn.commit()


def toggle_enabled(rid):
    conn = get_connection()
    conn.execute(
        "UPDATE recurring SET enabled = 1 - enabled, "
        "updated_at=datetime('now','localtime') WHERE id=?", (rid,))
    conn.commit()


# ---------------------------------------------------------------------------
# 到期判断与一键记账
# ---------------------------------------------------------------------------

def _month_key(ref) -> str:
    return f"{ref.year}-{ref.month:02d}"


def is_due(r: Recurring, ref=None) -> bool:
    """是否到期:本月已过到账日(day_of_month <= 今天)且本月尚未记入。"""
    ref = ref or today()
    if not r.enabled:
        return False
    if r.day_of_month > ref.day:
        return False
    if r.last_applied == _month_key(ref):
        return False
    return True


def due_recurring(ref=None) -> list[Recurring]:
    """所有已到期、待记入的固定收支。"""
    ref = ref or today()
    return [r for r in list_recurring(enabled_only=True) if is_due(r, ref)]


def apply_recurring(rid, ref=None) -> int:
    """一键记入:为该固定收支生成本月账单,返回新账单 id。
    记账日期取本月到账日(已到)或今天(提前记入)。"""
    ref = ref or today()
    r = get_recurring(rid)
    if r is None:
        raise ValueError("项目不存在")
    # 日期:到账日 <= 今天用到账日,否则今天
    sched = safe_date(ref.year, ref.month, r.day_of_month)
    d = sched if sched <= ref else ref
    tid = finance_service.add_transaction(r.amount, r.category_id, r.type, d, r.note or r.name)
    conn = get_connection()
    conn.execute(
        "UPDATE recurring SET last_applied=?, updated_at=datetime('now','localtime') WHERE id=?",
        (_month_key(ref), rid),
    )
    conn.commit()
    return tid


def apply_all_due(ref=None) -> int:
    """记入所有到期项,返回记入条数。"""
    ref = ref or today()
    n = 0
    for r in due_recurring(ref):
        try:
            apply_recurring(r.id, ref)
            n += 1
        except Exception:
            pass
    return n
