"""主窗口 —— 侧边栏导航 + 页面栈。

启动优化:页面采用惰性创建/导入。程序启动只建「首页 Dashboard」,
统计/预算/储蓄/设置/账单页在用户首次导航到该页面时才创建并刷新,
从而把模块加载与页面构建成本推迟到需要时,首屏更快。
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app.utils.helpers import STYLE_SHEET, install_cjk_font


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
        install_cjk_font()
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

        # Ctrl+K 快捷键:任意页面跳回首页并聚焦快速记账输入框
        shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        shortcut.activated.connect(self._jump_to_smart_input)

        # 底部状态栏:用于非打扰式操作反馈 toast
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        sb.setStyleSheet(
            "QStatusBar{background:transparent; border-top:1px solid #e5e5ea;}"
            "QStatusBar::item{border:none;}"
            "QStatusBar QLabel{color:#1d1d1f; padding:4px 14px;}"
        )

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
        self._pages: dict[str, QWidget] = {}
        parent_layout.addWidget(self.pages, stretch=1)
        # 首屏只建首页(落地页),其余页面首次导航时惰性创建
        self.pages.setCurrentWidget(self._ensure_page("dashboard"))

    # --------------------------------------------------------------- 页面

    def _ensure_page(self, key: str) -> QWidget:
        """惰性创建页面(模块懒导入),缓存后复用。"""
        cached = self._pages.get(key)
        if cached is not None:
            return cached
        if key == "transactions":
            from app.ui.transaction_page import TransactionPage
            w = TransactionPage(self)
        elif key == "statistics":
            from app.ui.statistics_page import StatisticsPage
            w = StatisticsPage(self)
        elif key == "budget":
            from app.ui.budget_page import BudgetPage
            w = BudgetPage(self)
        elif key == "savings":
            from app.ui.savings_page import SavingsPage
            w = SavingsPage(self)
        elif key == "settings":
            from app.ui.settings_page import SettingsPage
            w = SettingsPage(self)
        else:
            from app.ui.dashboard import Dashboard
            w = Dashboard(self)
        w.setObjectName("PageRoot")
        self._pages[key] = w
        self.pages.addWidget(w)
        return w

    # 兼容旧接口:外部代码通过 win.dashboard / win.statistics 等访问页面,
    # 属性访问会自动惰性创建对应页。
    @property
    def dashboard(self) -> QWidget:
        return self._ensure_page("dashboard")

    @property
    def transactions(self) -> QWidget:
        return self._ensure_page("transactions")

    @property
    def statistics(self) -> QWidget:
        return self._ensure_page("statistics")

    @property
    def budget(self) -> QWidget:
        return self._ensure_page("budget")

    @property
    def savings(self) -> QWidget:
        return self._ensure_page("savings")

    @property
    def settings(self) -> QWidget:
        return self._ensure_page("settings")

    # --------------------------------------------------------------- 导航

    def _on_nav_changed(self, row):
        if 0 <= row < len(NAV_ITEMS):
            key = NAV_ITEMS[row][0]
            w = self._ensure_page(key)
            self.pages.setCurrentWidget(w)
            if hasattr(w, "refresh"):
                w.refresh()
            # 首页聚焦快速记账输入框(用户打开软件即可直接打字记账)
            if key == "dashboard" and hasattr(w, "focus_input"):
                w.focus_input()

    def go_to(self, key: str):
        for i, (k, *_rest) in enumerate(NAV_ITEMS):
            if k == key:
                self.nav.setCurrentRow(i)
                return

    def _jump_to_smart_input(self):
        """Ctrl+K:回首页并聚焦快速记账输入框。"""
        self.go_to("dashboard")
        self.dashboard.focus_input()

    def refresh_all(self):
        """数据变更后只刷新「当前可见页 + 首页」。

        其余页面通过导航时的 _on_nav_changed 自动刷新(每次切页都会重拉数据),
        因此数据始终一致;避免「记一笔账就全量重算统计页图表」的无差别刷新。
        """
        w = self.pages.currentWidget()
        if w is not None and hasattr(w, "refresh"):
            w.refresh()
        d = self._pages.get("dashboard")
        if d is not None and d is not w and hasattr(d, "refresh"):
            d.refresh()

    def feedback(self, msg: str, timeout: int = 2500):
        """底部短暂提示,非打扰式操作反馈(记账/删除/导出等成功时调用)。"""
        self.statusBar().showMessage(msg, timeout)
