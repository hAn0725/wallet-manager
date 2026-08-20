"""首页 Dashboard —— 打开软件几秒内看清本月财务状况。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from app.services import budget_service, prediction_service, savings_service
from app.services.finance_service import get_total_balance, get_today_spent
from app.utils.helpers import format_money, today
from app.ui.widgets import _apply_shadow


class Dashboard(QWidget):
    """首页。"""

    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # ---- 头部标题 ----
        head = QHBoxLayout()
        title = QLabel("财务概览")
        title.setObjectName("PageTitle")
        head.addWidget(title)
        self.today_badge = QLabel("")
        self.today_badge.setObjectName("TodayBadge")
        head.addWidget(self.today_badge)
        head.addStretch()
        self.btn_add = QPushButton("＋ 快速记账")
        self.btn_add.setObjectName("Primary")
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(
            lambda: self.parent_window and self.parent_window.go_to("transactions")
        )
        head.addWidget(self.btn_add)
        root.addLayout(head)

        # ---- 主金额卡片 ----
        hero = QFrame()
        hero.setObjectName("Card")
        hv = QVBoxLayout(hero)
        hv.setContentsMargins(28, 24, 28, 26)
        hv.setSpacing(8)
        lbl = QLabel("本月剩余预算")
        lbl.setObjectName("CardTitle")
        hv.addWidget(lbl)
        self.huge = QLabel("¥ 0")
        self.huge.setObjectName("HugeNumber")
        hv.addWidget(self.huge)
        self.sub = QLabel("")
        self.sub.setObjectName("SubMuted")
        self.sub.setWordWrap(True)
        hv.addWidget(self.sub)

        # 预算进度条
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setFixedHeight(14)
        self.progress.setTextVisible(False)
        hv.addWidget(self.progress)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("SubMuted")
        hv.addWidget(self.progress_label)
        _apply_shadow(hero)
        root.addWidget(hero)

        # ---- 三张统计卡 ----
        row = QHBoxLayout()
        row.setSpacing(14)
        self.card_days = _stat("距离预算结束", "—", "")
        self.card_suggest = _stat("今日建议消费", "¥ 0", "")
        self.card_predict = _stat("月底预测", "—", "")
        for c in (self.card_days, self.card_suggest, self.card_predict):
            row.addWidget(c, stretch=1)
        root.addLayout(row)

        # ---- 累计余额 + 超支提醒 ----
        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        self.card_balance = _stat("累计余额", "¥ 0", "全部收入 - 全部支出")
        self.card_warn = _stat("超支提醒", "正常", "预算充足")
        bottom.addWidget(self.card_balance, stretch=1)
        bottom.addWidget(self.card_warn, stretch=1)
        root.addLayout(bottom)

        # ---- 储蓄目标概览 ----
        self.goals_box = QFrame()
        self.goals_box.setObjectName("Card")
        gv = QVBoxLayout(self.goals_box)
        gv.setContentsMargins(18, 16, 18, 18)
        gv.setSpacing(10)
        gtitle = QLabel("储蓄目标")
        gtitle.setObjectName("CardTitle")
        gv.addWidget(gtitle)
        self.goals_holder = QVBoxLayout()
        self.goals_holder.setContentsMargins(0, 0, 0, 0)
        gv.addLayout(self.goals_holder)
        _apply_shadow(self.goals_box)
        root.addWidget(self.goals_box)
        root.addStretch()

    # --------------------------------------------------------------- 刷新

    def refresh(self):
        from app.services.statistics_service import cycle_stats
        from app.utils.helpers import today_display
        summary = budget_service.get_cycle_summary()
        pred = prediction_service.predict()

        # 今天日期徽章
        self.today_badge.setText(today_display())

        # 主金额:剩余预算
        self.huge.setText(format_money(summary.remaining))
        self.sub.setText(
            f"本月预算 {format_money(summary.budget)}　·　"
            f"已消费 {format_money(summary.spent)}　·　"
            f"周期 {summary.start_date} ~ {summary.end_date}"
        )

        # 进度条
        ratio = max(0.0, min(1.0, summary.used_ratio))
        self.progress.setValue(int(ratio * 1000))
        pct = int(round(ratio * 100))
        self.progress_label.setText(
            f"已用 {pct}%　·　剩余 {format_money(summary.remaining)}　·　"
            f"今日已消费 {format_money(get_today_spent())}"
        )
        # 进度条颜色随阈值变化
        color = "#3b82f6"
        if summary.alert_level == "warning":
            color = "#d97706"
        elif summary.alert_level in ("danger", "over"):
            color = "#ef4444"
        self.progress.setStyleSheet(
            f"QProgressBar::chunk{{background:{color};border-radius:7px;}}"
        )

        # 三张统计卡
        if summary.days_remaining > 0:
            self.card_days.set_value(f"{summary.days_remaining} 天")
            self.card_days.set_subtitle(f"周期结束日 {summary.end_date}")
        else:
            self.card_days.set_value("今天到期")
            self.card_days.set_subtitle(f"周期结束日 {summary.end_date}")

        self.card_suggest.set_value(format_money(summary.daily_suggestion))
        if summary.remaining <= 0 and summary.budget > 0:
            self.card_suggest.set_value_object("DangerLabel")
            self.card_suggest.set_subtitle("本月已超支,建议减少消费")
        else:
            self.card_suggest.set_value_object("BigNumber")
            self.card_suggest.set_subtitle(
                f"剩余预算 ÷ 剩余天数　今日已花 {format_money(get_today_spent())}"
            )

        # 月底预测卡
        self.card_predict.set_value(format_money(pred.predicted_total))
        if pred.will_overspend and summary.budget > 0:
            self.card_predict.set_value_object("DangerLabel")
            self.card_predict.set_subtitle(
                f"⚠️ 预计月底超支 {format_money(pred.overspend)}　"
                f"预计余额 {format_money(pred.predicted_balance)}"
            )
        elif summary.budget > 0:
            self.card_predict.set_value_object("OkLabel")
            self.card_predict.set_subtitle(
                f"预计月底余额 {format_money(pred.predicted_balance)}　"
                f"日均 {format_money(pred.blended_daily, False)}"
            )
        else:
            self.card_predict.set_value_object("BigNumber")
            self.card_predict.set_subtitle(
                f"按当前速度预计消费 {format_money(pred.predicted_total)}"
            )

        # 累计余额
        self.card_balance.set_value(format_money(summary.balance_total))

        # 超支提醒
        if summary.budget <= 0:
            self.card_warn.set_value("未设置预算")
            self.card_warn.set_value_object("WarnLabel")
            self.card_warn.set_subtitle("前往「预算」设置月度预算")
        elif summary.alert_level == "over":
            self.card_warn.set_value(f"超支 {format_money(-summary.remaining, False)}")
            self.card_warn.set_value_object("DangerLabel")
            self.card_warn.set_subtitle(f"已超出预算 {format_money(summary.spent - summary.budget, False)}")
        elif summary.alert_level == "danger":
            self.card_warn.set_value("预算已用完")
            self.card_warn.set_value_object("DangerLabel")
            self.card_warn.set_subtitle(f"已用 {int(round(summary.used_ratio*100))}%")
        elif summary.alert_level == "warning":
            self.card_warn.set_value("注意预算")
            self.card_warn.set_value_object("WarnLabel")
            self.card_warn.set_subtitle(f"已用 {int(round(summary.used_ratio*100))}%,接近上限")
        else:
            self.card_warn.set_value("正常")
            self.card_warn.set_value_object("OkLabel")
            self.card_warn.set_subtitle(f"已用 {int(round(summary.used_ratio*100))}%,预算充足")

        # 储蓄目标
        self._refresh_goals()

    def _refresh_goals(self):
        # 清空
        while self.goals_holder.count():
            it = self.goals_holder.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        goals = savings_service.list_goals()
        if not goals:
            empty = QLabel("还没有储蓄目标,去「储蓄」添加一个吧 →")
            empty.setObjectName("SubMuted")
            self.goals_holder.addWidget(empty)
            return
        for g in goals[:3]:   # 只显示前 3 个主目标
            row = _goal_row(g)
            self.goals_holder.addWidget(row)
        if len(goals) > 3:
            more = QLabel(f"还有 {len(goals)-3} 个目标,去「储蓄」查看全部")
            more.setObjectName("SubMuted")
            self.goals_holder.addWidget(more)


def _stat(title, value, subtitle) -> "StatCard":
    from app.ui.widgets import StatCard
    return StatCard(title, value, subtitle)


def _goal_row(g) -> QWidget:
    from app.services.savings_service import SavingsGoal
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 4, 0, 4)
    h.setSpacing(12)
    v = QVBoxLayout()
    v.setSpacing(4)
    name = QLabel(g.name)
    name.setStyleSheet("font-weight:600;")
    line2 = QLabel(
        f"{format_money(g.current_amount, False)} / {format_money(g.target_amount, False)}"
        f"  ·  剩余 {format_money(g.remaining, False)}"
    )
    line2.setObjectName("SubMuted")
    v.addWidget(name)
    v.addWidget(line2)
    h.addLayout(v, stretch=1)
    pct = int(round(g.progress_pct * 100))
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(pct)
    bar.setFixedWidth(160)
    bar.setFixedHeight(14)
    bar.setTextVisible(True)
    bar.setFormat(f"{pct}%")
    h.addWidget(bar)
    return w
