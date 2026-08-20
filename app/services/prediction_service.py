"""月底消费预测 —— 基于当前消费速度与近期趋势,设计为可替换。

第一版使用加权统计法:
  日均 = 周期内累计支出 / 已过天数
  近7日日均 = 最近 7 天支出 / 7(数据不足时退化为日均)
  融合速率 = 0.4 * 日均 + 0.6 * 近7日日均   (更看重近期趋势)
  预计月底总消费 = 累计支出 + 融合速率 * 剩余天数
  预计月底余额 = 预算 - 预计月底总消费
  预计超支   = max(0, 预计月底总消费 - 预算)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.services import budget_service, finance_service, statistics_service
from app.utils.helpers import cycle_days, get_cycle_range, round2, today


@dataclass
class PredictionResult:
    spent: float                 # 周期内已支出
    predicted_total: float       # 预计月底总消费
    predicted_balance: float     # 预计月底余额(预算 - 预计总消费)
    overspend: float             # 预计超支金额(>=0)
    avg_daily: float             # 周期日均
    recent_daily: float          # 近 7 日日均
    blended_daily: float         # 融合后每日速率
    days_elapsed: int
    days_remaining: int
    method: str = "weighted_recent7"

    @property
    def will_overspend(self) -> bool:
        return self.overspend > 0


class Predictor:
    """预测器基类/默认实现。子类可重写 predict() 实现更高级算法。"""

    name = "weighted_recent7"

    def predict(self, ref=None) -> PredictionResult:
        ref = ref or today()
        cfg = budget_service.get_budget()
        budget = cfg.amount if cfg else 0.0
        period_type = cfg.period_type if cfg else "natural_month"
        start_day = cfg.start_day if cfg else 1

        start, end = get_cycle_range(period_type, start_day, ref)
        # 复用 CycleSummary,避免重复查询预算/支出/天数
        summary = budget_service.get_cycle_summary(ref)
        spent = summary.spent
        days_elapsed = summary.days_elapsed
        days_remaining = summary.days_remaining

        avg_daily = round2(spent / days_elapsed) if days_elapsed > 0 else 0.0

        # 近 7 日支出(含今天往前的 7 天,不超出周期起点)
        recent_start = max(start, ref - timedelta(days=6))
        trend = statistics_service.daily_trend(recent_start, ref)
        recent_total = round2(sum(d.amount for d in trend))
        recent_days = len(trend) or 1
        recent_daily = round2(recent_total / recent_days) if recent_total > 0 else avg_daily

        # 数据稀疏时退化为日均
        if recent_total == 0 and spent == 0:
            blended = 0.0
        elif recent_total == 0:
            blended = avg_daily
        else:
            blended = round2(0.4 * avg_daily + 0.6 * recent_daily)

        predicted_total = round2(spent + blended * days_remaining)
        predicted_balance = round2(budget - predicted_total)
        overspend = round2(max(0.0, predicted_total - budget)) if budget > 0 else 0.0

        return PredictionResult(
            spent=spent, predicted_total=predicted_total,
            predicted_balance=predicted_balance, overspend=overspend,
            avg_daily=avg_daily, recent_daily=recent_daily, blended_daily=blended,
            days_elapsed=days_elapsed, days_remaining=days_remaining,
            method=self.name,
        )

    def predict_with_budget(self, budget: float, period_type: str, start_day: int,
                            ref=None) -> PredictionResult:
        """直接给定预算参数做预测,跳过读库(便于批量/离线场景)。"""
        ref = ref or today()
        start, end = get_cycle_range(period_type, start_day, ref)
        total, elapsed, remaining_days = cycle_days(period_type, start_day, ref)

        spent = finance_service.get_cycle_spent(start, end)
        avg_daily = round2(spent / elapsed) if elapsed > 0 else 0.0

        recent_start = max(start, ref - timedelta(days=6))
        trend = statistics_service.daily_trend(recent_start, ref)
        recent_total = round2(sum(d.amount for d in trend))
        recent_daily = round2(recent_total / len(trend)) if recent_total > 0 else avg_daily

        if recent_total == 0 and spent == 0:
            blended = 0.0
        elif recent_total == 0:
            blended = avg_daily
        else:
            blended = round2(0.4 * avg_daily + 0.6 * recent_daily)

        predicted_total = round2(spent + blended * remaining_days)
        predicted_balance = round2(budget - predicted_total)
        overspend = round2(max(0.0, predicted_total - budget)) if budget > 0 else 0.0

        return PredictionResult(
            spent=spent, predicted_total=predicted_total,
            predicted_balance=predicted_balance, overspend=overspend,
            avg_daily=avg_daily, recent_daily=recent_daily, blended_daily=blended,
            days_elapsed=elapsed, days_remaining=remaining_days,
            method=self.name,
        )


# 默认实例,UI 与测试可直接使用;如需替换算法只需修改此变量
predictor: Predictor = Predictor()


def predict(ref=None) -> PredictionResult:
    return predictor.predict(ref)
