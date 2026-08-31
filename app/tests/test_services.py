"""服务层与数据库的单元测试,覆盖需求列出的边界情况。

运行: uv run python -m pytest app/tests/ -v
或:   uv run python app/tests/test_services.py
"""
from __future__ import annotations

import datetime
import os
import shutil
import sys
import tempfile

import pytest

# Windows 控制台默认 GBK,强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 使用临时数据库,避免污染真实数据
_TMP = tempfile.mkdtemp(prefix="cfa_test_")
os.environ["CFA_TEST_DB_DIR"] = _TMP

from app.database import database as dbmod
dbmod.DB_DIR = _TMP
dbmod.DB_PATH = os.path.join(_TMP, "finance.db")

from app.services import (  # noqa: E402
    anomaly_service, budget_service, category_service, finance_service,
    prediction_service, recurring_service, savings_service,
    settings_service, statistics_service,
)
from app.utils.helpers import (  # noqa: E402
    cycle_days, format_money, get_cycle_range, parse_money, round2,
    safe_date,
)


def _close_conn():
    conn = getattr(dbmod._local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        dbmod._local.conn = None


def _setup():
    _close_conn()
    # 显式重指向本模块的临时库(多测试模块同会话运行时避免相互覆盖 DB_PATH)
    dbmod.DB_DIR = _TMP
    dbmod.DB_PATH = os.path.join(_TMP, "finance.db")
    # 删除主库与 WAL 侧文件(已关闭连接,可安全删除)
    for ext in ("", "-wal", "-shm"):
        p = dbmod.DB_PATH + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    dbmod.init_db()


def _teardown():
    _close_conn()
    # 留着文件等下一轮 _setup 覆盖;仅在全部结束时清目录
    shutil.rmtree(_TMP, ignore_errors=True)
    os.makedirs(_TMP, exist_ok=True)


def pytest_runtest_makereport(item, call):
    """测试结束后无论成功/失败都清理临时库,避免状态泄漏污染后续测试。"""


@pytest.fixture(autouse=True)
def _auto_cleanup():
    yield
    _teardown()


# ===========================================================================
# 格式化 / 日期工具
# ===========================================================================

def test_money_format():
    assert format_money(1174) == "¥1,174"
    assert format_money(1174.5) == "¥1,174.50"
    assert format_money(0) == "¥0"
    assert format_money(-180, False) == "-180"
    assert parse_money("¥1,200.5") == 1200.5
    assert parse_money("28元") == 28.0
    assert parse_money("") == 0.0
    assert round2(1.005) == 1.01  # 四舍五入(ROUND_HALF_UP)


def test_cycle_natural_month():
    ref = datetime.date(2026, 8, 20)
    s, e = get_cycle_range("natural_month", 1, ref)
    assert s == datetime.date(2026, 8, 1)
    assert e == datetime.date(2026, 8, 31)
    total, elapsed, remaining = cycle_days("natural_month", 1, ref)
    assert total == 31 and elapsed == 20 and remaining == 11


def test_cycle_custom_start():
    # 自定义周期起始日 15 号,今天是 20 号 -> 本月15 ~ 下月14
    ref = datetime.date(2026, 8, 20)
    s, e = get_cycle_range("custom", 15, ref)
    assert s == datetime.date(2026, 8, 15)
    assert e == datetime.date(2026, 9, 14)
    # 今天 10 号,早于 15 -> 上月15 ~ 本月14
    ref2 = datetime.date(2026, 8, 10)
    s2, e2 = get_cycle_range("custom", 15, ref2)
    assert s2 == datetime.date(2026, 7, 15)
    assert e2 == datetime.date(2026, 8, 14)


def test_cycle_feb_leap_safe():
    # 2 月没有 30/31 号,safe_date 不应报错
    ref = datetime.date(2026, 2, 28)
    s, e = get_cycle_range("natural_month", 1, ref)
    assert e.day == 28


# ===========================================================================
# 记账 / 账单
# ===========================================================================

def test_add_and_query():
    _setup()
    cats = category_service.list_categories("expense")
    cid = cats[0].id
    finance_service.add_transaction(28, cid, "expense", "2026-08-20", "午饭")
    txns = finance_service.get_transactions()
    assert len(txns) == 1
    assert txns[0].amount == 28
    assert txns[0].note == "午饭"
    _teardown()


def test_update_delete():
    _setup()
    cats = category_service.list_categories("expense")
    cid = cats[0].id
    tid = finance_service.add_transaction(50, cid, "expense", "2026-08-20", "test")
    finance_service.update_transaction(tid, 80, cid, "expense", "2026-08-19", "改了")
    t = finance_service.get_transaction(tid)
    assert t.amount == 80 and t.note == "改了" and t.date == "2026-08-19"
    finance_service.delete_transaction(tid)
    assert finance_service.get_transaction(tid) is None
    _teardown()


def test_invalid_amount_zero_and_negative():
    _setup()
    cats = category_service.list_categories("expense")
    cid = cats[0].id
    for bad in (-10, 0):
        try:
            finance_service.add_transaction(bad, cid, "expense", "2026-08-20", "")
            assert False, f"应拒绝金额 {bad}"
        except ValueError:
            pass
    _teardown()


def test_category_type_must_match_transaction_type():
    """服务层也要拒绝收入使用支出分类，不能只依赖 UI 下拉框。"""
    _setup()
    expense_category = category_service.list_categories("expense")[0]
    with pytest.raises(ValueError, match="分类类型"):
        finance_service.add_transaction(100, expense_category.id, "income", "2026-08-20")
    _teardown()


def test_huge_amount():
    _setup()
    cats = category_service.list_categories("income")
    cid = cats[0].id
    finance_service.add_transaction(1_000_000_000, cid, "income", "2026-08-20", "巨款")
    assert finance_service.get_total_balance() == 1_000_000_000
    _teardown()


def test_cross_month_transaction():
    _setup()
    cats = category_service.list_categories("expense")
    cid = cats[0].id
    finance_service.add_transaction(100, cid, "expense", "2026-07-31", "上月")
    finance_service.add_transaction(200, cid, "expense", "2026-08-01", "本月")
    # 自然月统计
    s, e = get_cycle_range("natural_month", 1, datetime.date(2026, 8, 15))
    spent = finance_service.get_cycle_spent(s, e)
    assert spent == 200
    _teardown()


def test_income_only_and_expense_only():
    _setup()
    ecats = category_service.list_categories("expense")
    icats = category_service.list_categories("income")
    # 只有收入
    finance_service.add_transaction(2000, icats[0].id, "income", "2026-08-01", "生活费")
    assert finance_service.get_total_balance() == 2000
    pred = prediction_service.predict(datetime.date(2026, 8, 15))
    assert pred.spent == 0 and pred.predicted_total == 0 and pred.overspend == 0
    _teardown()


def test_expense_only_no_income():
    _setup()
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(300, ecats[0].id, "expense", "2026-08-10", "花")
    bal = finance_service.get_total_balance()
    assert bal == -300
    _teardown()


def test_no_transactions():
    _setup()
    summary = budget_service.get_cycle_summary(datetime.date(2026, 8, 15))
    assert summary.spent == 0
    assert summary.remaining == 2500  # 默认预算
    pred = prediction_service.predict(datetime.date(2026, 8, 15))
    assert pred.spent == 0
    _teardown()


# ===========================================================================
# 预算系统
# ===========================================================================

def test_budget_default_and_update():
    _setup()
    cfg = budget_service.get_budget()
    assert cfg.amount == 2500 and cfg.period_type == "natural_month"
    budget_service.set_budget(3000, "custom", 15)
    cfg = budget_service.get_budget()
    assert cfg.amount == 3000 and cfg.period_type == "custom" and cfg.start_day == 15
    _teardown()


def test_budget_alerts():
    _setup()
    ecats = category_service.list_categories("expense")
    cid = ecats[0].id
    budget_service.set_budget(1000, "natural_month", 1)
    # 80% -> warning
    finance_service.add_transaction(800, cid, "expense", "2026-08-10", "")
    s = budget_service.get_cycle_summary(datetime.date(2026, 8, 11))
    assert s.alert_level == "warning"
    # 100% -> danger
    finance_service.add_transaction(200, cid, "expense", "2026-08-11", "")
    s = budget_service.get_cycle_summary(datetime.date(2026, 8, 11))
    assert s.alert_level == "danger"
    # 超支 -> over
    finance_service.add_transaction(1, cid, "expense", "2026-08-11", "")
    s = budget_service.get_cycle_summary(datetime.date(2026, 8, 11))
    assert s.alert_level == "over"
    assert s.remaining == -1
    _teardown()


def test_budget_zero():
    _setup()
    budget_service.set_budget(0, "natural_month", 1)
    s = budget_service.get_cycle_summary(datetime.date(2026, 8, 15))
    assert s.budget == 0 and s.alert_level == "none"
    pred = prediction_service.predict(datetime.date(2026, 8, 15))
    assert pred.overspend == 0  # 预算为 0 不报超支
    _teardown()


def test_cycle_auto_switch_natural_month():
    """自然月周期自动切换:新周期从 0 开始,旧周期历史保留。"""
    _setup()
    ecats = category_service.list_categories("expense")
    # 8 月消费 100,9 月消费 20
    finance_service.add_transaction(100, ecats[0].id, "expense", "2026-08-20", "八月")
    finance_service.add_transaction(20, ecats[0].id, "expense", "2026-09-02", "九月")
    # 9 月周期汇总只统计 9 月
    s = budget_service.get_cycle_summary(datetime.date(2026, 9, 2))
    assert s.spent == 20
    assert s.start_date == "2026-09-01" and s.end_date == "2026-09-30"
    # 历史账单保留
    assert len(finance_service.get_transactions()) == 2
    # 月度对比能看到两个月的隔离
    cmp = statistics_service.monthly_comparison(datetime.date(2026, 9, 2))
    row = next(c for c in cmp if c.category == ecats[0].name)
    assert row.last == 100 and row.this == 20
    _teardown()


def test_cycle_auto_switch_custom_start():
    """自定义周期(每月10号):9/10 开启 9/10~10/9 的新周期。"""
    _setup()
    budget_service.set_budget(2500, "custom", 10)
    ecats = category_service.list_categories("expense")
    # 9/9 属于上个周期(8/10~9/9),9/11 属于新周期(9/10~10/9)
    finance_service.add_transaction(30, ecats[0].id, "expense", "2026-09-09", "旧周期")
    finance_service.add_transaction(50, ecats[0].id, "expense", "2026-09-11", "新周期")
    s = budget_service.get_cycle_summary(datetime.date(2026, 9, 11))
    assert s.start_date == "2026-09-10"
    assert s.end_date == "2026-10-09"
    assert s.spent == 50  # 旧周期账单不计入
    _teardown()


def test_cycle_auto_switch_year():
    """跨年切换:2027-01 周期正常开始,2026-12 消费不计入。"""
    _setup()
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(90, ecats[0].id, "expense", "2026-12-28", "去年")
    finance_service.add_transaction(10, ecats[0].id, "expense", "2027-01-03", "今年")
    s = budget_service.get_cycle_summary(datetime.date(2027, 1, 3))
    assert s.start_date == "2027-01-01"
    assert s.spent == 10
    _teardown()


def test_daily_suggestion():
    _setup()
    budget_service.set_budget(1000, "natural_month", 1)
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(400, ecats[0].id, "expense", "2026-08-10", "")
    s = budget_service.get_cycle_summary(datetime.date(2026, 8, 11))
    # 剩余 600, 剩余 20 天(11..31),近期偏快 -> 被持平线截断为 flat=30
    assert s.remaining == 600
    assert s.daily_suggestion == round2(600 / 20)
    _teardown()


def test_smart_daily_suggestion():
    """智能建议:融合持平线与近期节奏,不超持平线。"""
    fn = budget_service.smart_daily_suggestion
    # 已超支 -> 0
    assert fn(-100, 10, 50) == 0.0
    # 周期结束 -> 0
    assert fn(100, 0, 50) == 0.0
    # 无近期数据 -> 持平线
    assert fn(600, 20, 0) == round2(600 / 20)
    # 近期偏慢(recent<flat) -> 融合值低于持平线
    assert fn(600, 20, 10) == round2(0.5 * 30 + 0.5 * 10)   # 20
    # 近期偏快(recent>flat) -> 被持平线截断为 flat
    assert fn(100, 10, 50) == round2(100 / 10)              # 10
    _teardown()


def test_cycle_summary_has_recent_daily():
    _setup()
    budget_service.set_budget(1000, "natural_month", 1)
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(70, ecats[0].id, "expense", "2026-08-09", "")
    s = budget_service.get_cycle_summary(datetime.date(2026, 8, 11))
    assert s.recent_daily > 0   # 近7日有支出
    _teardown()


# ===========================================================================
# 月底预测
# ===========================================================================

def test_prediction_overspend():
    _setup()
    budget_service.set_budget(1000, "natural_month", 1)
    ecats = category_service.list_categories("expense")
    # 每天消费 50,到 15 号已花 750,剩余 16 天 -> 预计 750+50*16=1550 -> 超支 550
    for day in range(1, 16):
        finance_service.add_transaction(50, ecats[0].id, "expense",
                                        f"2026-08-{day:02d}", "")
    pred = prediction_service.predict(datetime.date(2026, 8, 15))
    assert pred.avg_daily == round2(750 / 15)
    assert pred.recent_daily == 50  # 近7天都是50
    assert pred.predicted_total == 750 + 50 * 16
    assert pred.will_overspend
    assert pred.overspend == 550
    _teardown()


def test_prediction_decreasing_trend():
    _setup()
    budget_service.set_budget(1000, "natural_month", 1)
    ecats = category_service.list_categories("expense")
    # 前期花得多,最近少 -> 融合后应低于平均
    for day in range(1, 11):
        finance_service.add_transaction(100, ecats[0].id, "expense",
                                        f"2026-08-{day:02d}", "")
    for day in range(11, 16):
        finance_service.add_transaction(10, ecats[0].id, "expense",
                                        f"2026-08-{day:02d}", "")
    pred = prediction_service.predict(datetime.date(2026, 8, 15))
    # 近7日日均(9,10=100;11-15=10) = (200+50)/7 = 35.71
    assert pred.recent_daily < pred.avg_daily
    _teardown()


# ===========================================================================
# 统计
# ===========================================================================

def test_statistics():
    _setup()
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(850, ecats[0].id, "expense", "2026-08-10", "")
    finance_service.add_transaction(320, ecats[1].id, "expense", "2026-08-11", "")
    stats = statistics_service.category_stats(datetime.date(2026, 8, 1),
                                             datetime.date(2026, 8, 31))
    assert len(stats) == 2
    assert stats[0].amount == 850
    assert stats[0].ratio == round2(850 / 1170)
    trend = statistics_service.daily_trend(datetime.date(2026, 8, 10),
                                          datetime.date(2026, 8, 11))
    assert len(trend) == 2
    _teardown()


def test_monthly_comparison():
    _setup()
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(720, ecats[0].id, "expense", "2026-07-10", "")
    finance_service.add_transaction(850, ecats[0].id, "expense", "2026-08-10", "")
    cmp = statistics_service.monthly_comparison(datetime.date(2026, 8, 15))
    row = next(c for c in cmp if c.category == ecats[0].name)
    assert row.last == 720 and row.this == 850
    assert row.change_pct == round2((850 - 720) / 720)
    _teardown()


def test_recent_categories_by_usage():
    """近 30 天分类使用频率排序(供自然语言无法明确分类时推荐)。"""
    _setup()
    ecats = category_service.list_categories("expense")
    # 餐饮 3 次,购物 1 次,交通 1 次
    finance_service.add_transaction(18, ecats[0].id, "expense", "2026-08-18", "午饭")
    finance_service.add_transaction(16, ecats[0].id, "expense", "2026-08-19", "奶茶")
    finance_service.add_transaction(25, ecats[0].id, "expense", "2026-08-20", "晚饭")
    finance_service.add_transaction(100, ecats[1].id, "expense", "2026-08-10", "淘宝")
    finance_service.add_transaction(6, ecats[2].id, "expense", "2026-08-12", "地铁")
    recent = statistics_service.recent_categories("expense")
    # 按使用次数:餐饮(3) 应排在最前
    assert recent[0] == ecats[0].name
    # 超过 30 天的记录不应影响
    finance_service.add_transaction(999, ecats[3].id, "expense", "2026-06-01", "很旧")
    recent2 = statistics_service.recent_categories("expense")
    assert ecats[3].name not in recent2
    _teardown()


def test_monthly_report():
    _setup()
    ecats = category_service.list_categories("expense")
    icats = category_service.list_categories("income")
    budget_service.set_budget(1000, "natural_month", 1)
    finance_service.add_transaction(2000, icats[0].id, "income", "2026-08-05", "生活费")
    finance_service.add_transaction(850, ecats[0].id, "expense", "2026-08-10", "餐饮")
    finance_service.add_transaction(200, ecats[1].id, "expense", "2026-08-12", "购物")
    finance_service.add_transaction(100, ecats[0].id, "expense", "2026-07-10", "上月餐饮")
    savings_service.add_goal("电脑", 6000, 2350)
    rep = statistics_service.monthly_report(datetime.date(2026, 8, 15))
    assert rep.year == 2026 and rep.month == 8
    assert rep.income == 2000
    assert rep.expense == 1050            # 本月支出 850+200
    assert rep.net == 950
    assert rep.top_category_amount == 850  # 本月餐饮(上月的不算)
    assert rep.budget == 1000
    assert rep.overspend == 50            # 1050 - 1000
    assert rep.savings_total == 2350
    assert rep.has_data
    _teardown()


def test_usage_insights():
    _setup()
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(18, ecats[0].id, "expense", "2026-08-05", "午饭")
    finance_service.add_transaction(300, ecats[1].id, "expense", "2026-08-06", "大额")
    finance_service.add_transaction(16, ecats[0].id, "expense", "2026-08-07", "奶茶")
    ins = statistics_service.usage_insights(datetime.date(2026, 8, 15))
    assert ins.max_amount == 300
    assert ins.max_category == ecats[1].name
    assert ins.avg_daily_bills > 0
    assert ins.top_category_ratio > 0
    _teardown()


def test_monthly_report_empty():
    _setup()
    rep = statistics_service.monthly_report(datetime.date(2026, 8, 15))
    assert not rep.has_data
    assert rep.income == 0 and rep.expense == 0
    _teardown()


# ===========================================================================
# 储蓄目标
# ===========================================================================

def test_savings_goal():
    _setup()
    gid = savings_service.add_goal("买电脑", 6000, 2350)
    g = savings_service.get_goal(gid)
    assert g.target_amount == 6000 and g.current_amount == 2350
    assert g.remaining == 3650
    assert g.progress_pct == round2(2350 / 6000)
    # 存入
    savings_service.adjust_amount(gid, 150)
    assert savings_service.get_goal(gid).current_amount == 2500
    # 取出超过余额
    savings_service.adjust_amount(gid, -99999)
    assert savings_service.get_goal(gid).current_amount == 0
    # 目标金额变更
    savings_service.update_goal(gid, "新电脑", 8000)
    g = savings_service.get_goal(gid)
    assert g.name == "新电脑" and g.target_amount == 8000
    savings_service.delete_goal(gid)
    assert savings_service.get_goal(gid) is None
    _teardown()


def test_savings_invalid():
    _setup()
    try:
        savings_service.add_goal("", 1000)
        assert False
    except ValueError:
        pass
    try:
        savings_service.add_goal("x", 0)
        assert False
    except ValueError:
        pass
    _teardown()


# ===========================================================================
# 固定周期收支
# ===========================================================================

def test_recurring_crud():
    _setup()
    icats = category_service.list_categories("income")
    ecats = category_service.list_categories("expense")
    rid = recurring_service.add_recurring("生活费", 2000, "income",
                                           icats[0].id, 5, "月生活费")
    r = recurring_service.get_recurring(rid)
    assert r.name == "生活费" and r.amount == 2000 and r.day_of_month == 5
    assert r.enabled and r.last_applied is None
    recurring_service.update_recurring(rid, "生活费", 2200, "income",
                                       icats[0].id, 6, "改")
    assert recurring_service.get_recurring(rid).amount == 2200
    assert recurring_service.get_recurring(rid).day_of_month == 6
    recurring_service.toggle_enabled(rid)
    assert not recurring_service.get_recurring(rid).enabled
    recurring_service.delete_recurring(rid)
    assert recurring_service.get_recurring(rid) is None
    _teardown()


def test_recurring_due_and_apply():
    _setup()
    icats = category_service.list_categories("income")
    # 每月5号生活费,今天是15号 -> 到期
    rid = recurring_service.add_recurring("生活费", 2000, "income",
                                           icats[0].id, 5)
    due = recurring_service.due_recurring(datetime.date(2026, 8, 15))
    assert any(d.id == rid for d in due)
    # 一键记入
    tid = recurring_service.apply_recurring(rid, datetime.date(2026, 8, 15))
    t = finance_service.get_transaction(tid)
    assert t.amount == 2000 and t.type == "income"
    assert t.date == "2026-08-05"   # 记到账日
    # 记入后本月不再到期
    due2 = recurring_service.due_recurring(datetime.date(2026, 8, 15))
    assert not any(d.id == rid for d in due2)
    # 下月应再次到期
    due3 = recurring_service.due_recurring(datetime.date(2026, 9, 6))
    assert any(d.id == rid for d in due3)
    _teardown()


def test_recurring_not_due_future():
    _setup()
    ecats = category_service.list_categories("expense")
    # 每月20号话费,今天是15号 -> 未到
    rid = recurring_service.add_recurring("话费", 50, "expense",
                                           ecats[2].id, 20)
    due = recurring_service.due_recurring(datetime.date(2026, 8, 15))
    assert not any(d.id == rid for d in due)
    _teardown()


def test_recurring_invalid():
    _setup()
    try:
        recurring_service.add_recurring("", 100, "income", None, 5)
        assert False
    except ValueError:
        pass
    try:
        recurring_service.add_recurring("x", 0, "income", None, 5)
        assert False
    except ValueError:
        pass
    try:
        recurring_service.add_recurring("x", 100, "income", None, 31)
        assert False
    except ValueError:
        pass
    expense_category = category_service.list_categories("expense")[0]
    with pytest.raises(ValueError, match="分类类型"):
        recurring_service.add_recurring("x", 100, "income", expense_category.id, 5)
    _teardown()


def test_recurring_apply_all_due():
    _setup()
    icats = category_service.list_categories("income")
    ecats = category_service.list_categories("expense")
    recurring_service.add_recurring("生活费", 2000, "income", icats[0].id, 5)
    recurring_service.add_recurring("话费", 50, "expense", ecats[2].id, 1)
    # 未到期的也加一个
    recurring_service.add_recurring("会员", 15, "expense", ecats[3].id, 25)
    n = recurring_service.apply_all_due(datetime.date(2026, 8, 15))
    assert n == 2   # 只记入到期的两笔
    _teardown()


# ===========================================================================
# 消费异常提醒
# ===========================================================================

def test_anomaly_today_high():
    _setup()
    ecats = category_service.list_categories("expense")
    cid = ecats[0].id
    ref = datetime.date(2026, 8, 15)
    for d in range(8, 15):   # 近7日(8-8..8-14)每天20
        finance_service.add_transaction(20, cid, "expense", f"2026-08-{d:02d}", "")
    finance_service.add_transaction(200, cid, "expense", "2026-08-15", "")  # 今天大额
    anomalies = anomaly_service.detect_anomalies(ref)
    assert any("今日" in a.message for a in anomalies)
    _teardown()


def test_anomaly_none_normal():
    _setup()
    ecats = category_service.list_categories("expense")
    ref = datetime.date(2026, 8, 15)
    for d in range(8, 15):
        finance_service.add_transaction(30, ecats[0].id, "expense", f"2026-08-{d:02d}", "")
    finance_service.add_transaction(30, ecats[0].id, "expense", "2026-08-15", "")
    anomalies = anomaly_service.detect_anomalies(ref)
    assert anomalies == []
    _teardown()


def test_anomaly_weekly_category():
    _setup()
    ecats = category_service.list_categories("expense")
    cid = ecats[1].id  # 购物
    ref = datetime.date(2026, 8, 15)
    # 过去四周每周购物50(均在 7-12..8-8 区间内)
    finance_service.add_transaction(50, cid, "expense", "2026-07-15", "")
    finance_service.add_transaction(50, cid, "expense", "2026-07-22", "")
    finance_service.add_transaction(50, cid, "expense", "2026-07-29", "")
    finance_service.add_transaction(50, cid, "expense", "2026-08-05", "")
    # 本周(8-9..8-15)购物大额300
    finance_service.add_transaction(300, cid, "expense", "2026-08-12", "")
    anomalies = anomaly_service.detect_anomalies(ref)
    assert any("本周" in a.message and "购物" in a.message for a in anomalies)
    _teardown()


def test_anomaly_no_data():
    _setup()
    ref = datetime.date(2026, 8, 15)
    assert anomaly_service.detect_anomalies(ref) == []
    _teardown()


# ===========================================================================

# 分类管理
# ===========================================================================

def test_category_delete_with_transactions():
    _setup()
    ecats = category_service.list_categories("expense")
    cid = ecats[0].id
    finance_service.add_transaction(50, cid, "expense", "2026-08-10", "")
    assert category_service.category_transaction_count(cid) == 1
    # 删除分类 -> 账单保留但 category_id 为 NULL(ON DELETE SET NULL)
    category_service.delete_category(cid)
    assert category_service.get_category(cid) is None
    t = finance_service.get_transactions()[0]
    assert t.category_id is None
    _teardown()


def test_category_crud():
    _setup()
    cid = category_service.add_category("宠物", "🐶", "expense")
    c = category_service.get_category(cid)
    assert c.name == "宠物" and c.icon == "🐶"
    category_service.update_category(cid, "宠物用品", "🐾")
    c = category_service.get_category(cid)
    assert c.name == "宠物用品" and c.icon == "🐾"
    _teardown()


def test_category_invalid_type():
    _setup()
    try:
        category_service.add_category("x", "x", "other")
        assert False
    except ValueError:
        pass
    _teardown()


def test_transaction_category_id_validation():
    """category_id 必须指向真实存在的分类,否则拒绝。"""
    _setup()
    try:
        finance_service.add_transaction(10, 99999, "expense", "2026-08-20", "")
        assert False, "应拒绝不存在的分类"
    except ValueError:
        pass
    _teardown()


def test_transaction_update_nonexistent():
    _setup()
    try:
        finance_service.update_transaction(99999, 10, None, "expense", "2026-08-20", "")
        assert False, "应拒绝更新不存在的账单"
    except ValueError:
        pass
    _teardown()


def test_prediction_with_budget_params():
    """直接给定预算参数的预测路径(不走 get_budget 读库)。"""
    _setup()
    ecats = category_service.list_categories("expense")
    for d in range(1, 11):
        finance_service.add_transaction(50, ecats[0].id, "expense",
                                        f"2026-08-{d:02d}", "")
    pred = prediction_service.predictor.predict_with_budget(
        1000, "natural_month", 1, datetime.date(2026, 8, 10))
    assert pred.spent == 500  # 1~10 日每天 50
    assert pred.days_elapsed == 10
    assert pred.avg_daily == 50
    _teardown()


def test_cycle_summary_no_budget():
    """未设置预算时 CycleSummary 的默认行为。"""
    _setup()
    # 清掉默认预算
    dbmod.get_connection().execute("DELETE FROM budgets")
    dbmod.get_connection().commit()
    s = budget_service.get_cycle_summary(datetime.date(2026, 8, 15))
    assert s.budget == 0
    assert s.alert_level == "none"
    _teardown()


def test_format_money_negative():
    _setup()
    assert format_money(-180) == "-¥180"
    assert format_money(-180.5) == "-¥180.50"
    _teardown()


def test_parse_money_various():
    _setup()
    assert parse_money("  ¥ 1,234.5  ") == 1234.5
    assert parse_money("￥50") == 50.0
    assert parse_money("$99.9") == 99.9
    # 纯字母无法解析,应抛 ValueError
    try:
        parse_money("abc")
        assert False, "应拒绝纯字母输入"
    except ValueError:
        pass
    _teardown()


def test_safe_date_clamp():
    _setup()
    # 2 月没有 30 号,应自动夹到 28
    d = safe_date(2026, 2, 30)
    assert d.day == 28
    # 4 月没有 31 号
    d2 = safe_date(2026, 4, 31)
    assert d2.day == 30
    _teardown()


def test_category_lookup_includes_all():
    _setup()
    lookup = finance_service.get_category_lookup()
    assert len(lookup) >= 14  # 默认 9 支出 + 5 收入
    _teardown()


def test_cycle_days_elapsed_clamped():
    _setup()
    # ref 在周期开始之前,elapsed 应至少为 1
    total, elapsed, remaining = cycle_days("natural_month", 1,
                                            datetime.date(2026, 8, 1))
    assert elapsed >= 1
    _teardown()


# ===========================================================================
# 导入导出
# ===========================================================================

def test_export_import_json():
    _setup()
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(28, ecats[0].id, "expense", "2026-08-20", "午饭")
    path = os.path.join(_TMP, "exp.json")
    n = settings_service.export_json(path)
    assert n == 1
    # 清空后导入
    dbmod.get_connection().execute("DELETE FROM transactions")
    dbmod.get_connection().commit()
    assert len(finance_service.get_transactions()) == 0
    m = settings_service.import_json(path, "merge")
    assert m == 1
    assert len(finance_service.get_transactions()) == 1
    _teardown()


def test_export_import_json_preserves_recurring_and_settings():
    """JSON 全量迁移必须包含固定收支与用户配置，而不仅是账单。"""
    _setup()
    income_category = category_service.list_categories("income")[0]
    recurring_service.add_recurring("生活费", 2000, "income", income_category.id, 5, "月初到账")
    settings_service.set_setting("quick_templates", '[{"label":"测试模板"}]')
    path = os.path.join(_TMP, "full_export.json")
    settings_service.export_json(path)
    with open(path, encoding="utf-8") as f:
        exported = __import__("json").load(f)
    assert exported["version"] == 2
    assert len(exported["recurring"]) == 1
    assert any(row["key"] == "quick_templates" for row in exported["settings"])

    settings_service.import_json(path, "replace")
    rows = recurring_service.list_recurring()
    assert len(rows) == 1 and rows[0].name == "生活费"
    assert settings_service.get_setting("quick_templates") == '[{"label":"测试模板"}]'
    _teardown()


def test_export_csv():
    _setup()
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(28, ecats[0].id, "expense", "2026-08-20", "午饭")
    path = os.path.join(_TMP, "exp.csv")
    n = settings_service.export_csv(path)
    assert n == 1
    assert os.path.exists(path)
    _teardown()


def test_templates_default_and_crud():
    _setup()
    tpls = settings_service.get_templates()
    assert len(tpls) == 4  # 默认 4 个
    labels = [t["label"] for t in tpls]
    assert "午饭" in labels and "奶茶" in labels
    # 增删改
    tpls = list(tpls)
    tpls.append({"icon": "☕", "label": "咖啡", "type": "expense",
                 "category": "餐饮", "note": "咖啡"})
    settings_service.save_templates(tpls)
    assert any(t["label"] == "咖啡" for t in settings_service.get_templates())
    # 排序
    tpls2 = settings_service.get_templates()
    tpls2.reverse()
    settings_service.save_templates(tpls2)
    assert settings_service.get_templates()[0]["label"] == "咖啡"
    _teardown()


def test_auto_backup_rotates_and_throttles():
    _setup()
    ecats = category_service.list_categories("expense")
    for i in range(3):
        finance_service.add_transaction(10, ecats[0].id, "expense", f"2026-08-{i+1:02d}", "")
    # 连续强制备份 8 次,应裁剪到 5 个
    for _ in range(8):
        p = settings_service.auto_backup(force=True)
        assert p and os.path.exists(p)
    assert len(settings_service.list_backups()) <= settings_service.AUTO_BACKUP_KEEP
    # 刚备份过,普通调用(未强制)应跳过(7 天内)
    assert settings_service.auto_backup() is None
    _teardown()


def test_corrupt_db_recovery():
    """数据库损坏:使用最近的有效自动备份恢复,历史数据不丢。"""
    _setup()
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(25, ecats[0].id, "expense", "2026-08-15", "重要")
    # 先做一个有效备份
    settings_service.auto_backup(force=True)
    # 关闭连接后损坏主库
    from app.database import database as _db
    _db._close()
    for ext in ("", "-wal", "-shm"):
        p = dbmod.DB_PATH + ext
        try:
            os.remove(p)
        except OSError:
            pass
    with open(dbmod.DB_PATH, "wb") as f:
        f.write(b"garbage not a sqlite db" * 5)
    # 重新初始化 → 从备份恢复
    dbmod.init_db()
    txns = finance_service.get_transactions()
    assert len(txns) == 1
    assert txns[0].amount == 25
    _teardown()


def test_backup_restore():
    _setup()
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(28, ecats[0].id, "expense", "2026-08-20", "x")
    bak = os.path.join(_TMP, "bak.db")
    settings_service.backup_via_sqlite(bak)
    assert os.path.exists(bak)
    # 删数据后恢复
    dbmod.get_connection().execute("DELETE FROM transactions")
    dbmod.get_connection().commit()
    assert len(finance_service.get_transactions()) == 0
    settings_service.restore_database(bak)
    assert len(finance_service.get_transactions()) == 1
    _teardown()


# ===========================================================================
# 运行
# ===========================================================================

def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    failures = []
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa
            failed += 1
            failures.append((t.__name__, repr(e)))
            print(f"  FAIL  {t.__name__}: {e!r}")
        finally:
            _teardown()
    print(f"\nResult: {passed} passed, {failed} failed, {len(tests)} total")
    for name, err in failures:
        print(f"  - {name}: {err}")
    return failed == 0


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
