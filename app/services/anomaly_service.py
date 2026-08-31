"""消费异常提醒 —— 检测今日/本周消费明显偏离常态,克制提示。

提醒克制:只在首页以静默卡片展示,不弹窗、不重复打扰。
检测两类异常:
  1) 今日消费明显高于近 7 日(不含今天)日均 —— 需同时满足相对(1.5×)与绝对(+50)阈值。
  2) 本周某类消费明显高于过去四周该类周均 —— 只报最显著的一项。
阈值的存在是为了避免小额波动被误报(如 10 元 vs 20 元)。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.services import finance_service
from app.services.statistics_service import category_expense_rows
from app.utils.helpers import format_money, round2, today


@dataclass
class Anomaly:
    message: str


def _category_expense_map(start, end) -> dict:
    """区间内各支出分类汇总:{name: (icon, amount, days)}。复用 statistics_service 公共聚合,避免重复 SQL。"""
    rows = category_expense_rows(start, end)
    return {r["name"]: (r["icon"], round2(r["amount"]), r["days"]) for r in rows}


def _today_anomaly(ref) -> Anomaly | None:
    baseline_start = ref - timedelta(days=7)
    baseline_end = ref - timedelta(days=1)
    baseline = finance_service.sum_by_type(baseline_start, baseline_end, "expense")
    baseline_avg = round2(baseline / 7) if baseline > 0 else 0.0
    today_spent = finance_service.get_today_spent(ref)
    if (baseline_avg > 0
            and today_spent > baseline_avg * 1.5
            and today_spent > baseline_avg + 50):
        return Anomaly(
            f"今日已消费 {format_money(today_spent)},明显高于近 7 日日均 "
            f"{format_money(baseline_avg)}。可留意是否有大额支出。"
        )
    return None


def _weekly_category_anomaly(ref) -> Anomaly | None:
    this_start, this_end = ref - timedelta(days=6), ref
    prior_start, prior_end = ref - timedelta(days=34), ref - timedelta(days=7)
    this_map = _category_expense_map(this_start, this_end)
    prior_map = _category_expense_map(prior_start, prior_end)
    best = None  # (name, icon, this_amt, prior_weekly_avg)
    for name, (icon, this_amt, _this_days) in this_map.items():
        _pi, prior_total, prior_days = prior_map.get(name, ("", 0.0, 0))
        prior_weekly_avg = round2(prior_total / 4) if prior_total > 0 else 0.0
        # 需要真实基线:过去四周该类至少有 3 天有消费,否则不算异常
        if (prior_weekly_avg > 0 and prior_days >= 3
                and this_amt > prior_weekly_avg * 1.5
                and this_amt > prior_weekly_avg + 100):
            if best is None or this_amt > best[2]:
                best = (name, icon, this_amt, prior_weekly_avg)
    if best:
        name, icon, this_amt, prior_avg = best
        return Anomaly(
            f"本周{icon} {name}消费 {format_money(this_amt)},"
            f"高于过去四周周均 {format_money(prior_avg)}。"
        )
    return None


def detect_anomalies(ref=None) -> list[Anomaly]:
    """检测异常,返回(最多 2 条)提醒。无异常返回空列表。"""
    ref = ref or today()
    out: list[Anomaly] = []
    a1 = _today_anomaly(ref)
    if a1:
        out.append(a1)
    a2 = _weekly_category_anomaly(ref)
    if a2:
        out.append(a2)
    return out
