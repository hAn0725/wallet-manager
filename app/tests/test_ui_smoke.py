"""UI 烟雾测试:用 offscreen 平台无头构造主窗口与所有页面,
验证导入、构造、刷新、记账流程不报错。

运行: uv run python -m app.tests.test_ui_smoke
"""
from __future__ import annotations

import os
import sys
import tempfile

# 必须在导入 PySide6 之前设置 offscreen 平台
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TMP = tempfile.mkdtemp(prefix="cfa_ui_")
from app.database import database as dbmod  # noqa: E402
dbmod.DB_DIR = _TMP
dbmod.DB_PATH = os.path.join(_TMP, "finance.db")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.database.database import init_db  # noqa: E402
from app.services import (  # noqa: E402
    budget_service, category_service, finance_service, prediction_service,
    savings_service,
)
from app.ui.main_window import MainWindow  # noqa: E402


def main():
    init_db()
    app = QApplication(sys.argv)

    errors = []

    # 1. 构造主窗口
    try:
        win = MainWindow()
        print("PASS  构造 MainWindow")
    except Exception as e:  # noqa
        print(f"FAIL  构造 MainWindow: {e!r}")
        return 1

    # 2. 切换到每个页面(惰性加载:首次导航创建页面并 refresh)
    NAV_KEYS = ["dashboard", "transactions", "statistics", "budget",
                "savings", "settings"]
    for i, key in enumerate(NAV_KEYS):
        try:
            win.go_to(key)
            w = win.pages.currentWidget()
            if hasattr(w, "refresh"):
                w.refresh()
            print(f"PASS  切换页面 {i} ({key}): {w.__class__.__name__}")
        except Exception as e:  # noqa
            print(f"FAIL  页面 {i} ({key}): {e!r}")
            errors.append((key, repr(e)))

    # 3. 写入一条支出 + 一条收入,验证刷新链路
    try:
        ecats = category_service.list_categories("expense")
        icats = category_service.list_categories("income")
        finance_service.add_transaction(28, ecats[0].id, "expense", None, "午饭")
        finance_service.add_transaction(2000, icats[0].id, "income", None, "生活费")
        # 用今天日期补一条让统计有数据
        from app.utils.helpers import today, iso
        d = iso(today())
        finance_service.add_transaction(50, ecats[1].id, "expense", d, "打车")
        win.refresh_all()
        print("PASS  记账后 refresh_all 全流程")
    except Exception as e:  # noqa
        print(f"FAIL  记账流程: {e!r}")
        errors.append(("txn", repr(e)))

    # 4. 创建储蓄目标,验证储蓄页 + 首页目标区
    try:
        savings_service.add_goal("买电脑", 6000, 2350)
        win.go_to("savings")
        win.savings.refresh()
        win.go_to("dashboard")
        win.dashboard.refresh()
        print("PASS  储蓄目标 + 首页目标区")
    except Exception as e:  # noqa
        print(f"FAIL  储蓄流程: {e!r}")
        errors.append(("savings", repr(e)))

    # 5. 改预算,验证预算页 + 预测
    try:
        budget_service.set_budget(2500, "custom", 15)
        win.go_to("budget")
        win.budget.refresh()
        pred = prediction_service.predict()
        assert pred.method == "weighted_recent7"
        print(f"PASS  预算自定义周期 + 预测(method={pred.method})")
    except Exception as e:  # noqa
        print(f"FAIL  预算/预测: {e!r}")
        errors.append(("budget", repr(e)))

    # 5.5 自然语言记账:解析 → 确认对话框 → 写入
    try:
        import datetime as dt
        from app.ui.smart_input import SmartInputDialog
        # 支出案例
        dlg = SmartInputDialog("午饭18", win, win.dashboard)
        assert dlg.amount.value() == 18.0
        assert dlg.type_combo.currentIndex() == 0          # 支出
        assert dlg.category.currentText() == "餐饮"
        d = dlg.date.date()
        assert dt.date(d.year(), d.month(), d.day()) == dt.date.today()
        # 收入案例
        dlg2 = SmartInputDialog("生活费到账2500", win, win.dashboard)
        assert dlg2.amount.value() == 2500.0
        assert dlg2.type_combo.currentIndex() == 1         # 收入
        assert "生活费" in dlg2.category.currentText()
        # 直接触发确认写入(不弹窗),验证数据链路
        n_before = len(finance_service.get_transactions())
        dlg._confirm()
        n_after = len(finance_service.get_transactions())
        assert n_after == n_before + 1
        assert dlg.result() == 1  # Accepted
        win.refresh_all()
        print("PASS  自然语言记账 解析+确认+写入+刷新全链路")
    except Exception as e:  # noqa
        print(f"FAIL  自然语言记账: {e!r}")
        errors.append(("smart_input", repr(e)))

    # 6. 切回各页面再刷新一次(确认无残留状态错误)
    try:
        for key in NAV_KEYS:
            win.go_to(key)
            w = win.pages.currentWidget()
            if hasattr(w, "refresh"):
                w.refresh()
        print("PASS  二次切换刷新")
    except Exception as e:  # noqa
        print(f"FAIL  二次刷新: {e!r}")
        errors.append(("reflow", repr(e)))

    print(f"\nResult: {'ALL OK' if not errors else f'{len(errors)} errors'}")
    return 0 if not errors else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
