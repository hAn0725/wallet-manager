"""端到端生命周期测试:模拟真实用户完整使用流程,重点验证
「关闭程序后重新打开数据不丢失」与各功能联动。

运行: uv run python -m pytest app/tests/test_lifecycle.py -v
"""
from __future__ import annotations

import datetime
import os
import shutil
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_TMP = tempfile.mkdtemp(prefix="cfa_life_")
from app.database import database as dbmod  # noqa: E402
dbmod.DB_DIR = _TMP
dbmod.DB_PATH = os.path.join(_TMP, "finance.db")

from app.services import (  # noqa: E402
    budget_service, category_service, finance_service,
    prediction_service, recurring_service, savings_service,
    settings_service, statistics_service, anomaly_service,
)
from app.utils.helpers import iso  # noqa: E402


def _restart():
    """模拟关闭程序后重新打开:关闭连接,重新初始化。"""
    conn = getattr(dbmod._local, "conn", None)
    if conn is not None:
        conn.close()
        dbmod._local.conn = None
    # 确保仍指向本模块的临时库(避免被其他测试模块覆盖)
    dbmod.DB_DIR = _TMP
    dbmod.DB_PATH = os.path.join(_TMP, "finance.db")
    dbmod.init_db()   # 幂等,不会清数据


def test_full_lifecycle():
    conn = getattr(dbmod._local, "conn", None)
    if conn is not None:
        conn.close()
        dbmod._local.conn = None
    dbmod.DB_DIR = _TMP
    dbmod.DB_PATH = os.path.join(_TMP, "finance.db")
    for ext in ("", "-wal", "-shm"):
        p = dbmod.DB_PATH + ext
        if os.path.exists(p):
            os.remove(p)
    dbmod.init_db()

    ref = datetime.date(2026, 8, 15)

    # 1) 新用户:无账单,默认预算 2500
    assert len(finance_service.get_transactions()) == 0
    assert budget_service.get_budget().amount == 2500
    s = budget_service.get_cycle_summary(ref)
    assert s.spent == 0 and s.remaining == 2500

    # 2) 设置固定生活费(每月5号)并一键记入
    icats = category_service.list_categories("income")
    rid = recurring_service.add_recurring("生活费", 2000, "income",
                                           icats[0].id, 5)
    due = recurring_service.due_recurring(ref)
    assert any(d.id == rid for d in due)
    recurring_service.apply_recurring(rid, ref)
    assert finance_service.get_total_balance() == 2000

    # 3) 连续记录多笔消费
    ecats = category_service.list_categories("expense")
    finance_service.add_transaction(38, ecats[0].id, "expense", iso(ref), "午饭")
    finance_service.add_transaction(12, ecats[2].id, "expense", iso(ref), "地铁")
    finance_service.add_transaction(158, ecats[1].id, "expense", iso(ref), "网购")
    finance_service.add_transaction(45, ecats[3].id, "expense", iso(ref), "电影")

    # 4) Dashboard 数字联动
    s = budget_service.get_cycle_summary(ref)
    assert s.spent == 253      # 38+12+158+45
    assert s.remaining == 2247
    assert s.balance_total == 1747  # 2000 - 253
    pred = prediction_service.predict(ref)
    assert pred.spent == 253

    # 5) 修改历史账单
    txns = finance_service.get_transactions()
    lunch = next(t for t in txns if t.note == "午饭")
    finance_service.update_transaction(lunch.id, 50, lunch.category_id,
                                       "expense", "2026-08-14", "午饭改")
    t = finance_service.get_transaction(lunch.id)
    assert t.amount == 50 and t.date == "2026-08-14"
    s = budget_service.get_cycle_summary(ref)
    assert s.spent == 265      # 50+12+158+45

    # 6) 删除账单
    movie = next(t for t in finance_service.get_transactions() if t.note == "电影")
    finance_service.delete_transaction(movie.id)
    assert finance_service.get_transaction(movie.id) is None
    assert budget_service.get_cycle_summary(ref).spent == 220  # 50+12+158

    # 7) 跨月记录 + 月度对比
    finance_service.add_transaction(300, ecats[0].id, "expense", "2026-07-10", "上月餐饮")
    cmp = statistics_service.monthly_comparison(ref)
    row = next(c for c in cmp if c.category == ecats[0].name)
    assert row.last == 300 and row.this == 50  # 本月餐饮:午饭改50

    # 8) 储蓄目标
    gid = savings_service.add_goal("电脑", 6000, 1000)
    savings_service.adjust_amount(gid, 500)
    assert savings_service.get_goal(gid).current_amount == 1500

    # 9) 修改预算
    budget_service.set_budget(2000, "natural_month", 1)
    assert budget_service.get_budget().amount == 2000
    s = budget_service.get_cycle_summary(ref)
    assert s.remaining == 1780  # 2000 - 220

    # 10) 导出 JSON
    path = os.path.join(_TMP, "backup.json")
    n = settings_service.export_json(path)
    assert n == len(finance_service.get_transactions())

    # 11) 关闭程序后重新打开 -> 数据持久
    before_txns = len(finance_service.get_transactions())
    before_goals = len(savings_service.list_goals())
    before_budget = budget_service.get_budget().amount
    _restart()
    assert len(finance_service.get_transactions()) == before_txns
    assert len(savings_service.list_goals()) == before_goals
    assert budget_service.get_budget().amount == before_budget
    # 生活费收入还在;累计余额含上月餐饮300:2000 - 220 - 300 = 1480
    assert finance_service.get_total_balance() == 1480

    # 12) 月度报告
    rep = statistics_service.monthly_report(ref)
    assert rep.income == 2000
    assert rep.expense == 220
    assert rep.net == 1780
    assert rep.budget == 2000
    assert rep.has_data

    # 13) 异常提醒:构造今日大额(近7日基线低)
    # 近7日已花(本月14号只有午饭改50),今天再加大额触发
    finance_service.add_transaction(600, ecats[1].id, "expense", iso(ref), "大额网购")
    anomalies = anomaly_service.detect_anomalies(ref)
    # 今日(15号)消费 12+158+600=770,近7日日均较低,应触发今日异常
    assert any("今日" in a.message for a in anomalies)

    # 清理
    conn = getattr(dbmod._local, "conn", None)
    if conn is not None:
        conn.close()
        dbmod._local.conn = None
    shutil.rmtree(_TMP, ignore_errors=True)
