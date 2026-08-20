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
    budget_service, category_service, finance_service,
    prediction_service, savings_service, settings_service,
    statistics_service,
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


def test_daily_suggestion():
    _setup()
    budget_service.set_budget(1000, "natural_month", 1)
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(400, ecats[0].id, "expense", "2026-08-10", "")
    s = budget_service.get_cycle_summary(datetime.date(2026, 8, 11))
    # 剩余 600, 剩余 20 天(11..31)
    assert s.remaining == 600
    assert s.daily_suggestion == round2(600 / 20)
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


def test_export_csv():
    _setup()
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(28, ecats[0].id, "expense", "2026-08-20", "午饭")
    path = os.path.join(_TMP, "exp.csv")
    n = settings_service.export_csv(path)
    assert n == 1
    assert os.path.exists(path)
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
