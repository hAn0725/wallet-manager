"""预算管理 —— 预算配置、预算周期、剩余预算、今日建议、超支提醒。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.database.database import get_connection
from app.services import finance_service
from app.utils.helpers import (
    cycle_days, get_cycle_range, round2, today,
)


@dataclass
class BudgetConfig:
    id: int
    amount: float
    period_type: str       # 'natural_month' / 'custom'
    start_day: int


def get_budget() -> Optional[BudgetConfig]:
    row = get_connection().execute(
        "SELECT * FROM budgets WHERE is_active=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return BudgetConfig(id=row["id"], amount=round2(row["amount"]),
                        period_type=row["period_type"], start_day=row["start_day"])


def set_budget(amount: float, period_type: str, start_day: int) -> None:
    """更新当前生效预算。period_type ∈ {'natural_month','custom'}。
    custom 时 start_day ∈ [1,28];natural_month 时 start_day 固定 1。"""
    amount = round2(amount)
    if amount < 0:
        raise ValueError("预算不能为负数")
    if period_type not in ("natural_month", "custom"):
        raise ValueError("周期类型无效")
    if period_type == "natural_month":
        start_day = 1
    elif not (1 <= start_day <= 28):
        raise ValueError("自定义周期的开始日必须在 1~28 之间")

    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM budgets WHERE is_active=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE budgets SET amount=?,period_type=?,start_day=?, "
            "updated_at=datetime('now','localtime') WHERE id=?",
            (amount, period_type, start_day, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO budgets(amount,period_type,start_day,is_active) "
            "VALUES(?,?,?,1)",
            (amount, period_type, start_day),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# 周期汇总
# ---------------------------------------------------------------------------

@dataclass
class CycleSummary:
    budget: float
    spent: float
    income: float
    remaining: float          # 预算 - 支出
    balance_total: float     # 累计余额(全部收入-支出)
    start_date: str
    end_date: str
    days_total: int
    days_elapsed: int
    days_remaining: int
    daily_suggestion: float  # 剩余预算 ÷ 剩余天数
    alert_level: str         # none / warning / danger / over
    used_ratio: float        # spent / budget

    @property
    def is_overspent(self) -> bool:
        return self.remaining < 0


def get_cycle_summary(ref=None) -> CycleSummary:
    ref = ref or today()
    cfg = get_budget()
    budget = cfg.amount if cfg else 0.0
    period_type = cfg.period_type if cfg else "natural_month"
    start_day = cfg.start_day if cfg else 1

    start, end = get_cycle_range(period_type, start_day, ref)
    total, elapsed, remaining_days = cycle_days(period_type, start_day, ref)

    spent = finance_service.get_cycle_spent(start, end)
    income = finance_service.get_cycle_income(start, end)
    remaining = round2(budget - spent)
    balance_total = finance_service.get_total_balance()

    if remaining_days > 0 and remaining > 0:
        suggestion = round2(remaining / remaining_days)
    elif remaining_days > 0 and remaining <= 0:
        suggestion = 0.0            # 已超支,建议停止消费
    else:
        suggestion = round2(remaining) if remaining > 0 else 0.0  # 周期最后一天

    used_ratio = round2(spent / budget) if budget > 0 else 0.0
    alert = alert_level(spent, budget)

    return CycleSummary(
        budget=budget, spent=spent, income=income, remaining=remaining,
        balance_total=balance_total, start_date=start.isoformat(),
        end_date=end.isoformat(), days_total=total, days_elapsed=elapsed,
        days_remaining=remaining_days, daily_suggestion=suggestion,
        alert_level=alert, used_ratio=used_ratio,
    )


def alert_level(spent: float, budget: float) -> str:
    """提醒级别。预算为 0 视为未设置。"""
    if budget <= 0:
        return "none"
    if spent > budget:
        return "over"          # 超支
    if spent >= budget:        # 刚好 100%
        return "danger"
    if spent >= budget * 0.8:
        return "warning"       # 80%
    return "none"
