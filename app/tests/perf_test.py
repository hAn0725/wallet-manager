"""性能测试:衡量 100/500/1000/5000 条账单下的关键操作耗时。

运行: uv run python -m app.tests.perf_test
覆盖:启动(init_db)、Dashboard 汇总、账单查询、统计、月度报告、自然语言解析。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="cfa_perf_")
from app.database import database as dbmod  # noqa: E402
dbmod.DB_DIR = _TMP
dbmod.DB_PATH = os.path.join(_TMP, "finance.db")

from app.database.database import init_db, get_connection  # noqa: E402
from app.services import (  # noqa: E402
    budget_service, finance_service, statistics_service,
)
from app.services.natural_language_parser import parse  # noqa: E402

CATEGORY_IDS = None


def _seed(n: int):
    global CATEGORY_IDS
    init_db()  # 保证表已建好(含默认分类)
    conn = get_connection()
    rows = conn.execute("SELECT id FROM categories WHERE type='expense' ORDER BY id").fetchall()
    CATEGORY_IDS = [r["id"] for r in rows] or [None]
    conn.execute("DELETE FROM transactions")
    import datetime
    import app.services.settings_service as ss
    ss.set_setting("last_auto_backup", datetime.date.today().isoformat())
    data = []
    base = datetime.date(2025, 1, 1)
    for i in range(n):
        d = base + datetime.timedelta(days=i % 800)
        data.append((round((i % 97) + 0.5, 2), CATEGORY_IDS[i % len(CATEGORY_IDS)],
                     "expense", d.isoformat(), f"账单{i % 500}"))
    conn.executemany(
        "INSERT INTO transactions(amount,category_id,type,date,note) "
        "VALUES(?,?,?,?,?)", data)
    conn.commit()


def _t(label, fn):
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1000


def _measure(n: int) -> dict:
    _seed(n)
    out = {}
    out["init_db"] = _t("init", init_db)
    out["get_cycle_summary"] = _t("summary", budget_service.get_cycle_summary)
    out["get_transactions(500)"] = _t("txns", lambda: finance_service.get_transactions(limit=500))
    out["category_stats"] = _t("cats", lambda: statistics_service.category_stats("2025-01-01", "2026-12-31"))
    out["daily_trend"] = _t("trend", lambda: statistics_service.daily_trend("2025-01-01", "2026-12-31"))
    out["monthly_report"] = _t("report", statistics_service.monthly_report)
    out["parse('午饭18')"] = _t("parse", lambda: parse("午饭18.5"))
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sizes = [100, 500, 1000, 5000]
    headers = ["操作"]
    for s in sizes:
        headers.append(f"{s} 条")
    print("  操作耗时(ms)    " + "  ".join(h.center(12) for h in headers))
    print("-" * 70)
    results = {}
    for s in sizes:
        results[s] = _measure(s)
    labels = list(next(iter(results.values())).keys())
    for lbl in labels:
        row = f"  {lbl:<16} "
        for s in sizes:
            row += f"{results[s][lbl]:>10.1f}ms  "
        print(row)
    # 5 千条时行数阈值告警(仅供参考,不视为失败)
    r5 = results[5000]
    if r5["get_transactions(500)"] > 200:
        print("\n⚠️ 提示: 5000 条账单查询偏慢(考虑加索引/分页)")
    print(f"\n临时库: {_TMP}")


if __name__ == "__main__":
    main()