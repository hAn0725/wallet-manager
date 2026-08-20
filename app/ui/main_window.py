"""主窗口 —— 侧边栏导航 + 页面栈。"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app.ui.budget_page import BudgetPage
from app.ui.dashboard import Dashboard
from app.ui.savings_page import SavingsPage
from app.ui.settings_page import SettingsPage
from app.ui.statistics_page import StatisticsPage
from app.ui.transaction_page import TransactionPage
from app.utils.helpers import STYLE_SHEET


NAV_ITEMS = [
    ("dashboard", "🏠", "首页"),
    ("transactions", "📝", "记账"),
    ("statistics", "📊", "统计"),
    ("budget", "💰", "预算"),
    ("savings", "🎯", "储蓄"),
    ("settings", "⚙️", "设置"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("大学生个人财务管理助手")
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(STYLE_SHEET)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self._build_sidebar(h)
        self._build_pages(h)
        self.setCentralWidget(central)

        self.nav.setCurrentRow(0)
        self.pages.currentChanged.connect(self._on_page_changed)

    def _build_sidebar(self, parent_layout: QHBoxLayout):
        bar = QFrame()
        bar.setObjectName("SideBar")
        bar.setFixedWidth(190)
        col = QVBoxLayout(bar)
        col.setContentsMargins(0, 0, 0, 12)
        col.setSpacing(0)

        app_title = QLabel("💰 财务助手")
        app_title.setObjectName("AppTitle")
        col.addWidget(app_title)
        app_sub = QLabel("College Finance")
        app_sub.setObjectName("AppSub")
        col.addWidget(app_sub)

        self.nav = QListWidget()
        self.nav.setFrameShape(QListWidget.NoFrame)
        self.nav.setSpacing(2)
        self.nav.setCursor(Qt.PointingHandCursor)
        for key, icon, label in NAV_ITEMS:
            item = QListWidgetItem(f"  {icon}  {label}")
            item.setData(Qt.UserRole, key)
            item.setSizeHint(QSize(0, 48))
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        col.addWidget(self.nav)
        col.addStretch()
        parent_layout.addWidget(bar)

    def _build_pages(self, parent_layout: QHBoxLayout):
        self.pages = QStackedWidget()
        self.dashboard = Dashboard(self)
        self.transactions = TransactionPage(self)
        self.statistics = StatisticsPage(self)
        self.budget = BudgetPage(self)
        self.savings = SavingsPage(self)
        self.settings = SettingsPage(self)
        for w in (self.dashboard, self.transactions, self.statistics,
                  self.budget, self.savings, self.settings):
            w.setObjectName("PageRoot")
            self.pages.addWidget(w)
        parent_layout.addWidget(self.pages, stretch=1)

    # ----------------------------------------------------------------- 导航

    def _on_nav_changed(self, row):
        if 0 <= row < self.pages.count():
            self.pages.setCurrentIndex(row)

    def _on_page_changed(self, idx):
        w = self.pages.widget(idx)
        if w and hasattr(w, "refresh"):
            w.refresh()

    def go_to(self, key: str):
        for i, (k, *_rest) in enumerate(NAV_ITEMS):
            if k == key:
                self.nav.setCurrentRow(i)
                return

    def refresh_all(self):
        """数据变更后刷新所有页面。"""
        for w in (self.dashboard, self.transactions, self.statistics,
                  self.budget, self.savings, self.settings):
            if hasattr(w, "refresh"):
                w.refresh()
