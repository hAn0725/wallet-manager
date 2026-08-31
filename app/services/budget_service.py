"""预算管理 —— 预算配置、预算周期、剩余预算、今日建议、超支提醒。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
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
    daily_suggestion: float  # 智能建议:融合持平线与近期节奏,不超持平线
    recent_daily: float      # 近 7 日日均支出(用于判断消费节奏)
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

    # 近 7 日(含今天,不早于周期起点)日均支出,用于判断消费节奏
    recent_start = max(start, ref - timedelta(days=6))
    recent_days = max(1, (ref - recent_start).days + 1)
    recent_spent = finance_service.sum_by_type(recent_start, ref, "expense")
    recent_daily = round2(recent_spent / recent_days) if recent_spent > 0 else 0.0

    suggestion = smart_daily_suggestion(remaining, remaining_days, recent_daily)

    used_ratio = round2(spent / budget) if budget > 0 else 0.0
    alert = alert_level(spent, budget)

    return CycleSummary(
        budget=budget, spent=spent, income=income, remaining=remaining,
        balance_total=balance_total, start_date=start.isoformat(),
        end_date=end.isoformat(), days_total=total, days_elapsed=elapsed,
        days_remaining=remaining_days, daily_suggestion=suggestion,
        recent_daily=recent_daily, alert_level=alert, used_ratio=used_ratio,
    )


def smart_daily_suggestion(remaining: float, days_remaining: int,
                           recent_daily: float) -> float:
    """根据剩余预算、剩余天数、近期日均动态计算今日建议消费。

    持平线 flat = 剩余预算 ÷ 剩余天数(到月底不超支的日均上限)。
    - 已超支或周期已结束:0
    - 无近期消费数据:flat(用持平线)
    - 否则:融合持平线(0.5)与近期日均(0.5),但永不超过持平线
      (近期偏快会被持平线截断 → flat;近期偏慢则略低于持平线,贴合实际节奏)
    设计上保证不会鼓励超支。
    """
    if remaining <= 0 or days_remaining <= 0:
        return 0.0
    flat = round2(remaining / days_remaining)
    if recent_daily <= 0:
        return flat
    blend = round2(0.5 * flat + 0.5 * recent_daily)
    return round2(min(blend, flat))


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
