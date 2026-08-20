"""消费统计 —— 分类占比、每日趋势、月度对比。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.database.database import get_connection
from app.utils.helpers import (
    _month_days, get_cycle_range, iso, round2, safe_date, today, to_date,
)


@dataclass
class CategoryStat:
    category_id: Optional[int]
    name: str
    icon: str
    amount: float
    ratio: float          # 占总支出比例


def category_stats(start_date, end_date) -> list[CategoryStat]:
    """区间内支出按分类聚合,金额降序。"""
    rows = get_connection().execute(
        """
        SELECT t.category_id,
               COALESCE(c.name,'未分类') AS name,
               COALESCE(c.icon,'')      AS icon,
               SUM(t.amount)            AS amount
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.type='expense' AND t.date>=? AND t.date<=?
        GROUP BY t.category_id, c.name, c.icon
        ORDER BY amount DESC
        """,
        (iso(to_date(start_date)), iso(to_date(end_date))),
    ).fetchall()

    total = round2(sum(r["amount"] for r in rows))
    result: list[CategoryStat] = []
    for r in rows:
        amt = round2(r["amount"])
        result.append(CategoryStat(
            category_id=r["category_id"], name=r["name"], icon=r["icon"],
            amount=amt, ratio=round2(amt / total) if total > 0 else 0.0,
        ))
    return result


@dataclass
class DailyTrend:
    date: str
    amount: float


def daily_trend(start_date, end_date) -> list[DailyTrend]:
    """区间内每天的支出。补齐没有消费的日子为 0。"""
    start = to_date(start_date)
    end = to_date(end_date)
    rows = get_connection().execute(
        "SELECT date, SUM(amount) AS amount FROM transactions "
        "WHERE type='expense' AND date>=? AND date<=? GROUP BY date",
        (iso(start), iso(end)),
    ).fetchall()
    mapping = {r["date"]: round2(r["amount"]) for r in rows}

    out: list[DailyTrend] = []
    d = start
    from datetime import timedelta
    while d <= end:
        out.append(DailyTrend(date=d.isoformat(), amount=mapping.get(d.isoformat(), 0.0)))
        d += timedelta(days=1)
    return out


@dataclass
class CategoryCompare:
    category: str
    icon: str
    last: float
    this: float
    change_pct: float       # 本月相对上月的变化百分比


def monthly_comparison(ref=None) -> list[CategoryCompare]:
    """本月 vs 上月 各分类支出对比。"""
    ref = ref or today()
    # 本月:自然月
    this_start = safe_date(ref.year, ref.month, 1)
    this_end = safe_date(ref.year, ref.month, _month_days(ref.year, ref.month))
    py, pm = (ref.year - 1, 12) if ref.month == 1 else (ref.year, ref.month - 1)
    last_start = safe_date(py, pm, 1)
    last_end = safe_date(py, pm, _month_days(py, pm))

    def agg(s, e):
        rows = get_connection().execute(
            """
            SELECT COALESCE(c.name,'未分类') AS name, COALESCE(c.icon,'') AS icon,
                   SUM(t.amount) AS amount
            FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
            WHERE t.type='expense' AND t.date>=? AND t.date<=?
            GROUP BY c.name, c.icon
            """,
            (iso(s), iso(e)),
        ).fetchall()
        return {r["name"]: (r["icon"], round2(r["amount"])) for r in rows}

    this_map = agg(this_start, this_end)
    last_map = agg(last_start, last_end)
    names = sorted(set(this_map) | set(last_map))

    out = []
    for name in names:
        icon, this_amt = this_map.get(name, ("", 0.0))
        last_amt = last_map.get(name, ("", 0.0))[1]
        if last_amt > 0:
            change = round2((this_amt - last_amt) / last_amt)
        elif this_amt > 0:
            change = 1.0      # 上月 0 本月有支出 -> 视为 +100%
        else:
            change = 0.0
        out.append(CategoryCompare(category=name, icon=icon,
                                   last=last_amt, this=this_amt, change_pct=change))
    out.sort(key=lambda x: x.this + x.last, reverse=True)
    return out


def cycle_stats(period_type: str, start_day: int, ref=None) -> list[CategoryStat]:
    """按预算周期统计分类支出。"""
    start, end = get_cycle_range(period_type, start_day, ref)
    return category_stats(start, end)


def cycle_trend(period_type: str, start_day: int, ref=None) -> list[DailyTrend]:
    start, end = get_cycle_range(period_type, start_day, ref)
    return daily_trend(start, end)
