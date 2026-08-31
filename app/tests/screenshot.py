"""渲染各页面为 PNG 用于视觉检查。offscreen 平台,无需显示。
运行: uv run python -m app.tests.screenshot
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TMP = tempfile.mkdtemp(prefix="cfa_shot_")
from app.database import database as dbmod  # noqa: E402
dbmod.DB_DIR = _TMP
dbmod.DB_PATH = os.path.join(_TMP, "finance.db")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.database.database import init_db  # noqa: E402
from app.services import (  # noqa: E402
    budget_service, category_service, finance_service, savings_service,
)
from app.ui.main_window import MainWindow  # noqa: E402
from app.utils.helpers import today, iso  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shots")
os.makedirs(OUT, exist_ok=True)


def seed():
    init_db()
    ec = category_service.list_categories("expense")
    ic = category_service.list_categories("income")
    d = iso(today())
    # 本月若干支出
    from app.utils.helpers import get_cycle_range
    s, e = get_cycle_range("natural_month", 1, today())
    finance_service.add_transaction(2000, ic[0].id, "income", iso(s), "8月生活费")
    finance_service.add_transaction(38, ec[0].id, "expense", d, "午饭")
    finance_service.add_transaction(12, ec[2].id, "expense", d, "地铁")
    finance_service.add_transaction(89, ec[0].id, "expense", d, "晚饭")
    finance_service.add_transaction(158, ec[1].id, "expense", d, "网购")
    finance_service.add_transaction(45, ec[3].id, "expense", d, "电影")
    finance_service.add_transaction(32, ec[0].id, "expense", d, "早餐")
    finance_service.add_transaction(219, ec[1].id, "expense", d, "衣服")
    finance_service.add_transaction(26, ec[5].id, "expense", d, "日用品")
    budget_service.set_budget(2500, "natural_month", 1)
    savings_service.add_goal("换新电脑", 6000, 2350)
    savings_service.add_goal("毕业旅行", 3000, 800)


def grab(win, name, size=(1180, 780)):
    win.resize(*size)
    win.show()
    app.processEvents()
    pix = win.grab()
    path = os.path.join(OUT, name)
    pix.save(path, "PNG")
    print(f"saved {path}  {pix.width()}x{pix.height()}")


def main():
    global app
    seed()
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1180, 780)
    win.show()
    app.processEvents()
    names = ["dashboard", "transactions", "statistics",
             "budget", "savings", "settings"]
    for name in names:
        # 页面是惰性创建的，必须通过导航创建对应页；直接按索引切换会反复截图首页。
        win.go_to(name)
        w = win.pages.currentWidget()
        if hasattr(w, "refresh"):
            w.refresh()
        app.processEvents()
        grab(win, f"page_{name}.png")
    # 单独截一张账单编辑对话框
    print("done")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
