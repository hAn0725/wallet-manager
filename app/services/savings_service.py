"""储蓄目标管理。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.database.database import get_connection
from app.utils.helpers import round2


@dataclass
class SavingsGoal:
    id: Optional[int]
    name: str
    target_amount: float
    current_amount: float
    note: str = ""

    @property
    def progress_pct(self) -> float:
        if self.target_amount <= 0:
            return 0.0
        return round2(min(1.0, self.current_amount / self.target_amount))

    @property
    def remaining(self) -> float:
        return round2(max(0.0, self.target_amount - self.current_amount))


def list_goals() -> list[SavingsGoal]:
    rows = get_connection().execute(
        "SELECT * FROM savings_goals ORDER BY id"
    ).fetchall()
    return [_row(r) for r in rows]


def get_goal(gid: int) -> Optional[SavingsGoal]:
    row = get_connection().execute(
        "SELECT * FROM savings_goals WHERE id=?", (gid,)
    ).fetchone()
    return _row(row) if row else None


def _row(r) -> SavingsGoal:
    return SavingsGoal(
        id=r["id"], name=r["name"], target_amount=round2(r["target_amount"]),
        current_amount=round2(r["current_amount"]), note=r["note"] or "",
    )


def add_goal(name: str, target_amount, current_amount=0, note="") -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("目标名称不能为空")
    target = round2(target_amount)
    cur = round2(current_amount)
    if target <= 0:
        raise ValueError("目标金额必须大于 0")
    if cur < 0:
        raise ValueError("当前金额不能为负数")
    conn = get_connection()
    cur_id = conn.execute(
        "INSERT INTO savings_goals(name,target_amount,current_amount,note) "
        "VALUES(?,?,?,?)",
        (name, target, cur, note or ""),
    ).lastrowid
    conn.commit()
    return cur_id


def update_goal(gid: int, name: str, target_amount, note="") -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("目标名称不能为空")
    target = round2(target_amount)
    if target <= 0:
        raise ValueError("目标金额必须大于 0")
    conn = get_connection()
    # 当前金额不得超过新目标
    goal = get_goal(gid)
    cur = goal.current_amount if goal else 0
    if cur > target:
        cur = target
    conn.execute(
        "UPDATE savings_goals SET name=?,target_amount=?,current_amount=?,note=?, "
        "updated_at=datetime('now','localtime') WHERE id=?",
        (name, target, cur, note or "", gid),
    )
    conn.commit()


def delete_goal(gid: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM savings_goals WHERE id=?", (gid,))
    conn.commit()


def adjust_amount(gid: int, delta) -> SavingsGoal:
    """向目标增加(正)或减少(负)金额。"""
    delta = round2(delta)
    goal = get_goal(gid)
    if goal is None:
        raise ValueError("目标不存在")
    new_amount = round2(goal.current_amount + delta)
    if new_amount < 0:
        new_amount = 0.0
    conn = get_connection()
    conn.execute(
        "UPDATE savings_goals SET current_amount=?, "
        "updated_at=datetime('now','localtime') WHERE id=?",
        (new_amount, gid),
    )
    conn.commit()
    return get_goal(gid)
