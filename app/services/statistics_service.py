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


def category_expense_rows(start_date, end_date):
    """区间内支出按分类聚合(金额降序)。供分类占比/月度对比/异常提醒共用,避免重复 SQL。"""
    return get_connection().execute(
        """
        SELECT t.category_id,
               COALESCE(c.name,'未分类') AS name,
               COALESCE(c.icon,'')      AS icon,
               SUM(t.amount)            AS amount,
               COUNT(DISTINCT t.date)   AS days
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.type='expense' AND t.date>=? AND t.date<=?
        GROUP BY t.category_id, c.name, c.icon
        ORDER BY amount DESC
        """,
        (iso(to_date(start_date)), iso(to_date(end_date))),
    ).fetchall()


def category_stats(start_date, end_date) -> list[CategoryStat]:
    """区间内支出按分类聚合,金额降序。"""
    rows = category_expense_rows(start_date, end_date)
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
        rows = category_expense_rows(s, e)
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


def recent_categories(transaction_type: str, ref=None, days: int = 30) -> list[str]:
    """近 N 天最常使用的分类名(按使用次数降序,次数相同按金额降序)。

    用于自然语言无法明确分类时,按用户历史习惯推荐分类。
    """
    from datetime import timedelta
    ref = ref or today()
    start = (ref - timedelta(days=days)).isoformat()
    rows = get_connection().execute(
        """
        SELECT COALESCE(c.name,'未分类') AS name,
               COUNT(*) AS cnt, SUM(t.amount) AS amt
        FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
        WHERE t.type=? AND t.date>=?
        GROUP BY COALESCE(c.name,'未分类')
        ORDER BY cnt DESC, amt DESC
        """,
        (transaction_type, start),
    ).fetchall()
    return [r["name"] for r in rows]


# ---------------------------------------------------------------------------
# 月度财务报告
# ---------------------------------------------------------------------------

@dataclass
class MonthlyReport:
    year: int
    month: int
    income: float
    expense: float
    net: float                 # 收入 - 支出
    top_category: str          # 最大消费类别名(带图标)
    top_category_amount: float
    last_expense: float        # 上月支出
    expense_change_pct: float  # 本月 vs 上月 支出变化
    budget: float
    overspend: float           # max(0, 支出 - 预算)
    savings_total: float       # 储蓄目标累计已存
    savings_target: float      # 储蓄目标总额
    savings_count: int
    has_data: bool


def monthly_report(ref=None) -> MonthlyReport:
    """生成「我的本月财务报告」,默认以 ref 所在自然月为口径。"""
    from app.services import budget_service, finance_service, savings_service
    ref = ref or today()
    this_start = safe_date(ref.year, ref.month, 1)
    this_end = safe_date(ref.year, ref.month, _month_days(ref.year, ref.month))
    py, pm = (ref.year - 1, 12) if ref.month == 1 else (ref.year, ref.month - 1)
    last_start = safe_date(py, pm, 1)
    last_end = safe_date(py, pm, _month_days(py, pm))

    income = finance_service.sum_by_type(this_start, this_end, "income")
    expense = finance_service.sum_by_type(this_start, this_end, "expense")
    last_expense = finance_service.sum_by_type(last_start, last_end, "expense")
    if last_expense > 0:
        change = round2((expense - last_expense) / last_expense)
    elif expense > 0:
        change = 1.0
    else:
        change = 0.0

    stats = category_stats(this_start, this_end)
    if stats:
        top = stats[0]
        top_name = f"{top.icon} {top.name}".strip()
        top_amount = top.amount
    else:
        top_name = "—"
        top_amount = 0.0

    cfg = budget_service.get_budget()
    budget = cfg.amount if cfg else 0.0
    overspend = round2(max(0.0, expense - budget)) if budget > 0 else 0.0

    goals = savings_service.list_goals()
    savings_total = round2(sum(g.current_amount for g in goals))
    savings_target = round2(sum(g.target_amount for g in goals))

    return MonthlyReport(
        year=ref.year, month=ref.month, income=income, expense=expense,
        net=round2(income - expense), top_category=top_name,
        top_category_amount=top_amount, last_expense=last_expense,
        expense_change_pct=change, budget=budget, overspend=overspend,
        savings_total=savings_total, savings_target=savings_target,
        savings_count=len(goals),
        has_data=(income > 0 or expense > 0),
    )


# ---------------------------------------------------------------------------
# 个人使用习惯统计(轻量)
# ---------------------------------------------------------------------------

@dataclass
class UsageInsights:
    peak_hour_range: str   # 最易消费的时间段
    avg_daily_bills: float # 日均消费笔数
    max_amount: float      # 最大单笔消费
    max_category: str      # 最大单笔所在分类
    top_category_ratio: float  # 最大分类占总支出比例


def usage_insights(ref=None) -> UsageInsights:
    """本月个人使用习惯(供统计页/月度报告展示,不侵占 Dashboard)。

    消费时间段用 created_at 的小时段近似(本应用常实时记账)。
    """
    ref = ref or today()
    s = safe_date(ref.year, ref.month, 1)
    e = safe_date(ref.year, ref.month, _month_days(ref.year, ref.month))

    # 最频繁的记账小时
    row = get_connection().execute(
        """SELECT CAST(strftime('%H', created_at) AS INTEGER) AS h, COUNT(*) AS c
           FROM transactions WHERE type='expense' AND date>=? AND date<=?
           GROUP BY h ORDER BY c DESC, h LIMIT 1""",
        (iso(s), iso(e)),
    ).fetchone()
    if row and row["h"] is not None:
        h = int(row["h"])
        h2 = (h + 3) % 24
        peak = f"{h:02d}:00 ~ {h2:02d}:00"
        if peak.startswith(("06", "07", "08", "09", "10", "11")):
            peak_label = f"上午 {peak}"
        elif peak.startswith(("00", "01", "02", "03", "04", "05")):
            peak_label = f"凌晨 {peak}"
        elif peak.startswith(("18", "19", "20", "21", "22", "23")):
            peak_label = f"晚上 {peak}"
        else:
            peak_label = f"下午 {peak}"
    else:
        peak_label = "—"

    # 日均笔数
    cnt_row = get_connection().execute(
        "SELECT COUNT(*) AS c FROM transactions WHERE type='expense' AND date>=? AND date<=?",
        (iso(s), iso(e)),
    ).fetchone()
    count = cnt_row["c"]
    days_elapsed = (ref - s).days + 1
    avg = round2(count / days_elapsed) if count > 0 else 0.0

    # 最大单笔 + 分类
    max_row = get_connection().execute(
        """SELECT t.amount AS amt, COALESCE(c.name,'未分类') AS name
           FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
           WHERE t.type='expense' AND t.date>=? AND t.date<=?
           ORDER BY t.amount DESC LIMIT 1""",
        (iso(s), iso(e)),
    ).fetchone()
    if max_row:
        max_amount = round2(max_row["amt"])
        max_cat = max_row["name"]
    else:
        max_amount, max_cat = 0.0, "—"

    # 最大分类占比
    stats = category_stats(s, e)
    ratio = stats[0].ratio if stats else 0.0

    return UsageInsights(
        peak_hour_range=peak_label, avg_daily_bills=avg,
        max_amount=max_amount, max_category=max_cat,
        top_category_ratio=ratio,
    )
