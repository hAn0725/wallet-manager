"""首页 Dashboard —— 打开软件几秒内看清本月财务状况。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.services import budget_service, prediction_service, recurring_service, savings_service
from app.services import anomaly_service, finance_service, settings_service
from app.services.finance_service import get_today_spent, get_transactions
from app.utils import design_tokens as dtk
from app.utils.helpers import format_money, round2
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
        root.setContentsMargins(*dtk.PAGE_MARGINS)
        root.setSpacing(dtk.PAGE_SPACING)

        # ---- 头部标题 ----
        head = QHBoxLayout()
        title = QLabel("财务概览")
        title.setObjectName("PageTitle")
        head.addWidget(title)
        self.today_badge = QLabel("")
        self.today_badge.setObjectName("TodayBadge")
        head.addWidget(self.today_badge)
        head.addStretch()
        root.addLayout(head)

        # ---- 快速记账(自然语言输入 + 常用模板) ----
        self.smart_card = QFrame()
        self.smart_card.setObjectName("Card")
        scv = QVBoxLayout(self.smart_card)
        scv.setContentsMargins(20, 14, 20, 14)
        scv.setSpacing(10)
        sc = QHBoxLayout()
        sc.setSpacing(10)
        icon = QLabel("✏️")
        icon.setStyleSheet("font-size:20px;")
        sc.addWidget(icon)
        self.smart_input = QLineEdit()
        self.smart_input.setPlaceholderText("输入一句话快速记账,如: 午饭18 或 昨天吃饭35,Ctrl+K 呼出")
        self.smart_input.setMinimumHeight(36)
        self.smart_input.setStyleSheet("font-size:14px; border-radius:12px; padding:6px 12px;")
        self.smart_input.returnPressed.connect(self._smart_submit)
        sc.addWidget(self.smart_input, stretch=1)
        self.smart_btn = QPushButton("记账")
        self.smart_btn.setObjectName("Primary")
        self.smart_btn.setCursor(Qt.PointingHandCursor)
        self.smart_btn.setMinimumHeight(36)
        self.smart_btn.clicked.connect(self._smart_submit)
        sc.addWidget(self.smart_btn)
        scv.addLayout(sc)
        # 常用模板 chips:点击直接进确认框,只需输金额
        self.tpl_row = QHBoxLayout()
        self.tpl_row.setSpacing(8)
        scv.addLayout(self.tpl_row)
        _apply_shadow(self.smart_card)
        root.addWidget(self.smart_card)

        # ---- 新手引导卡(无账单时显示) ----
        self.onboarding = QFrame()
        self.onboarding.setObjectName("Card")
        ob = QVBoxLayout(self.onboarding)
        ob.setContentsMargins(28, 22, 28, 24)
        ob.setSpacing(10)
        ob_greet = QLabel("欢迎使用财务助手 👋")
        ob_greet.setStyleSheet("font-size:20px;font-weight:700;color:#1d1d1f;")
        ob.addWidget(ob_greet)
        ob_sub = QLabel("三步开始管理你的生活费:设置预算 → 记第一笔账 → 看月底预测是否超支。")
        ob_sub.setObjectName("SubMuted")
        ob_sub.setWordWrap(True)
        ob.addWidget(ob_sub)
        ob_row = QHBoxLayout()
        ob_row.setSpacing(10)
        for label, key, primary in (
            ("① 设置月度预算", "budget", True),
            ("② 记第一笔账", "transactions", True),
            ("③ 添加储蓄目标", "savings", False),
        ):
            b = QPushButton(label)
            b.setObjectName("Primary" if primary else "")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(
                lambda _, k=key: self.parent_window and self.parent_window.go_to(k)
            )
            ob_row.addWidget(b)
        ob_row.addStretch()
        ob.addLayout(ob_row)
        _apply_shadow(self.onboarding)
        self.onboarding.setVisible(False)
        root.addWidget(self.onboarding)

        # ---- 固定收支到期提醒(有到期项时显示) ----
        self.recurring_box = QFrame()
        self.recurring_box.setObjectName("Card")
        rv = QVBoxLayout(self.recurring_box)
        rv.setContentsMargins(20, 16, 20, 18)
        rv.setSpacing(8)
        rtitle = QLabel("📌 固定收支到期提醒")
        rtitle.setObjectName("CardTitle")
        rv.addWidget(rtitle)
        self.recurring_holder = QVBoxLayout()
        self.recurring_holder.setContentsMargins(0, 0, 0, 0)
        rv.addLayout(self.recurring_holder)
        rall = QHBoxLayout()
        self.btn_apply_all = QPushButton("全部记入")
        self.btn_apply_all.setObjectName("Primary")
        self.btn_apply_all.setCursor(Qt.PointingHandCursor)
        self.btn_apply_all.clicked.connect(self._apply_all_recurring)
        rall.addStretch()
        rall.addWidget(self.btn_apply_all)
        rv.addLayout(rall)
        _apply_shadow(self.recurring_box)
        self.recurring_box.setVisible(False)
        root.addWidget(self.recurring_box)

        # ---- 消费异常提醒(有异常时静默展示) ----
        self.anomaly_box = QFrame()
        self.anomaly_box.setObjectName("Card")
        av = QVBoxLayout(self.anomaly_box)
        av.setContentsMargins(20, 16, 20, 18)
        av.setSpacing(6)
        atitle = QLabel("⚡ 消费异常提醒")
        atitle.setObjectName("CardTitle")
        av.addWidget(atitle)
        self.anomaly_holder = QVBoxLayout()
        self.anomaly_holder.setContentsMargins(0, 0, 0, 0)
        av.addLayout(self.anomaly_holder)
        _apply_shadow(self.anomaly_box)
        self.anomaly_box.setVisible(False)
        root.addWidget(self.anomaly_box)

        # ---- 月初/月末周期提示(仅周期开始或临近结束时显示) ----
        self.period_hint = QLabel("")
        self.period_hint.setWordWrap(True)
        self.period_hint.setObjectName("Card")
        self.period_hint.setContentsMargins(14, 12, 14, 12)
        self.period_hint.setStyleSheet(
            "QFrame#Card{background:#fff;border-radius:12px;padding:8px 14px;}")
        self.period_hint.setVisible(False)
        self.period_hint.setTextFormat(Qt.RichText)
        root.addWidget(self.period_hint)

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

        # ---- 最近记账记录(可点击编辑/删除) ----
        self.recent_box = QFrame()
        self.recent_box.setObjectName("Card")
        rev = QVBoxLayout(self.recent_box)
        rev.setContentsMargins(18, 16, 18, 18)
        rev.setSpacing(8)
        rtitle = QLabel("最近记录")
        rtitle.setObjectName("CardTitle")
        rev.addWidget(rtitle)
        self.recent_table = QTableWidget(0, 3)
        self.recent_table.setHorizontalHeaderLabels(["分类", "金额", "日期"])
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.recent_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.recent_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.recent_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.recent_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.recent_table.cellDoubleClicked.connect(self._open_recent)
        self.recent_table.setMaximumHeight(196)
        rev.addWidget(self.recent_table)
        _apply_shadow(self.recent_box)
        root.addWidget(self.recent_box)
        root.addStretch()

    # --------------------------------------------------------------- 刷新

    def refresh(self):
        from app.utils.helpers import today_display
        summary = budget_service.get_cycle_summary()
        pred = prediction_service.predict()

        # 新手引导:无任何账单时显示
        has_txns = bool(get_transactions(limit=1))
        self.onboarding.setVisible(not has_txns)

        # 今天日期徽章
        self.today_badge.setText(today_display())

        # 主金额:剩余预算
        self.huge.setText(format_money(summary.remaining))
        extra = (f"本月预算 {format_money(summary.budget)}　·　"
                 f"已消费 {format_money(summary.spent)}　·　"
                 f"累计余额 {format_money(summary.balance_total)}")
        if summary.alert_level == "over":
            extra += f"　·　❌ 已超支 {format_money(summary.spent - summary.budget, False)}"
        elif summary.alert_level == "danger":
            extra += "　·　⚠️ 预算已用完"
        elif summary.alert_level == "warning":
            extra += "　·　⏰ 已达 80%,注意控制"
        self.sub.setText(extra)

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

        # 月初 / 月末周期提示
        if summary.days_remaining <= 3 and summary.days_remaining >= 0 and summary.budget > 0:
            if summary.days_remaining == 0:
                self.period_hint.setText(
                    f"⏳ <b>本周期今天结束</b> · 当前剩余 {format_money(summary.remaining)}"
                    f" · 预计结余 {format_money(pred.predicted_balance)}")
            else:
                self.period_hint.setText(
                    f"⏳ <b>本周期即将结束(剩 {summary.days_remaining} 天)</b>"
                    f" · 当前剩余 {format_money(summary.remaining)}"
                    f" · 预计结余 {format_money(pred.predicted_balance)}")
            self.period_hint.setVisible(True)
        elif summary.days_elapsed <= 2 and summary.income > 0:
            self.period_hint.setText(
                f"✨ <b>新周期已开始</b> · 本月预算 {format_money(summary.budget)}"
                f" · 已消费 {format_money(summary.spent)}"
                f" · 收入 {format_money(summary.income)} 已到账 ✓"
                f"<br><span style='color:#86868b'>固定收支到账可点击上方提醒卡一键记入</span>")
            self.period_hint.setVisible(True)
        else:
            self.period_hint.setVisible(False)

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
            # 展示消费节奏:近期日均 vs 持平线
            flat = round2(summary.remaining / summary.days_remaining) \
                if summary.days_remaining > 0 else 0.0
            if summary.recent_daily <= 0:
                pace = "暂无近期消费数据"
            elif summary.recent_daily > flat and flat > 0:
                pace = f"近期偏快(近7日日均 {format_money(summary.recent_daily, False)})"
            elif summary.recent_daily < flat and flat > 0:
                pace = f"近期偏省(近7日日均 {format_money(summary.recent_daily, False)})"
            else:
                pace = f"近7日日均 {format_money(summary.recent_daily, False)}"
            self.card_suggest.set_subtitle(
                f"{pace}　·　今日已花 {format_money(get_today_spent())}"
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

        # 储蓄目标
        self._refresh_goals()
        self._refresh_recent()
        # 固定收支到期提醒
        self._refresh_recurring()
        # 消费异常提醒
        self._refresh_anomaly()
        self._refresh_templates()

    def _refresh_recurring(self):
        # 清空
        while self.recurring_holder.count():
            it = self.recurring_holder.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        due = recurring_service.due_recurring()
        if not due:
            self.recurring_box.setVisible(False)
            return
        self.recurring_box.setVisible(True)
        for r in due:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 4, 0, 4)
            h.setSpacing(10)
            tag = "收入" if r.type == "income" else "支出"
            name = QLabel(
                f"{r.name}　·　{tag}　·　每月{r.day_of_month}号"
                f"　·　{format_money(r.amount)}"
            )
            h.addWidget(name, stretch=1)
            btn = QPushButton("记入")
            btn.setObjectName("Primary")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, rid=r.id: self._apply_recurring(rid))
            h.addWidget(btn)
            self.recurring_holder.addWidget(row)

    def _apply_recurring(self, rid):
        try:
            recurring_service.apply_recurring(rid)
            if self.parent_window:
                self.parent_window.refresh_all()
                self.parent_window.feedback("已记入固定收支")
        except Exception as e:  # noqa
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "操作失败", str(e))

    def _apply_all_recurring(self):
        n = recurring_service.apply_all_due()
        if self.parent_window:
            self.parent_window.refresh_all()
            self.parent_window.feedback(f"已记入 {n} 笔固定收支")

    def _refresh_templates(self):
        """常用记账模板 chips:点击直接进确认框,只需输金额。"""
        while self.tpl_row.count():
            it = self.tpl_row.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        tpls = settings_service.get_templates()[:6]
        if not tpls:
            return
        lbl = QLabel("常用")
        lbl.setObjectName("SubMuted")
        self.tpl_row.addWidget(lbl)
        for t in tpls:
            chip = QPushButton(f"{t.get('icon', '')} {t.get('label', '')}")
            chip.setCursor(Qt.PointingHandCursor)
            chip.setFixedHeight(30)
            chip.clicked.connect(lambda _checked=False, tpl=t: self._smart_template_click(tpl))
            self.tpl_row.addWidget(chip)
        self.tpl_row.addStretch()
        manage = QPushButton("管理")
        manage.setFixedHeight(30)
        manage.clicked.connect(self._manage_templates)
        self.tpl_row.addWidget(manage)

    def _manage_templates(self):
        from app.ui.settings_page import TemplateManagerDialog
        dlg = TemplateManagerDialog(self)
        dlg.exec()
        self._refresh_templates()
        if self.parent_window:
            self.parent_window.refresh_all()

    def _smart_template_click(self, tpl):
        """点击模板 → 打开确认框(分类/备注已填),只需输入金额后回车。"""
        from app.ui.smart_input import SmartInputDialog
        dlg = SmartInputDialog(parent_window=self.parent_window, parent=self,
                               template=tpl)
        if dlg.exec() == SmartInputDialog.Accepted:
            self.smart_input.clear()
            self.smart_input.setFocus()

    def _refresh_recent(self):
        """首页最近记账记录,最近 5 条;双击可编辑/删除。"""
        txns = get_transactions(limit=5)
        cat_map = finance_service.get_category_lookup()
        self.recent_table.setRowCount(len(txns))
        for i, txn in enumerate(txns):
            name, icon, _t = cat_map.get(txn.category_id, ("未分类", "", ""))
            cat_item = QTableWidgetItem(f"{icon} {name}")
            amt_item = QTableWidgetItem(format_money(txn.amount))
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amt_item.setForeground(Qt.red if txn.is_expense else Qt.darkGreen)
            date_item = QTableWidgetItem(txn.date)
            self.recent_table.setItem(i, 0, cat_item)
            self.recent_table.setItem(i, 1, amt_item)
            self.recent_table.setItem(i, 2, date_item)
            self.recent_table.item(i, 0).setData(Qt.UserRole, txn.id)
        self.recent_box.setVisible(True)

    def _open_recent(self, row, _col):
        item = self.recent_table.item(row, 0)
        if not item:
            return
        tid = item.data(Qt.UserRole)
        txn = finance_service.get_transaction(tid)
        if not txn:
            self.refresh()
            return
        from app.ui.transaction_page import TransactionDialog
        dlg = TransactionDialog(txn, self, parent_window=self.parent_window)
        dlg.exec()
        # 编辑/删除后刷新
        self.refresh()
        if self.parent_window:
            self.parent_window.refresh_all()

    def focus_input(self):
        """切换到首页时让快速记账输入框获得焦点。"""
        self.smart_input.setFocus()

    def _smart_submit(self):
        """自然语言记账:解析 → 确认对话框 → 记账。"""
        from app.ui.smart_input import SmartInputDialog
        text = self.smart_input.text().strip()
        if not text:
            if self.parent_window:
                self.parent_window.feedback("请输入记账内容", 1500)
            return
        dlg = SmartInputDialog(text, self.parent_window, self)
        if dlg.exec() == SmartInputDialog.Accepted:
            self.smart_input.clear()
            self.smart_input.setFocus()

    def _refresh_anomaly(self):
        while self.anomaly_holder.count():
            it = self.anomaly_holder.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        anomalies = anomaly_service.detect_anomalies()
        if not anomalies:
            self.anomaly_box.setVisible(False)
            return
        self.anomaly_box.setVisible(True)
        for a in anomalies:
            lb = QLabel(a.message)
            lb.setWordWrap(True)
            lb.setStyleSheet("color:#ff9500;")
            self.anomaly_holder.addWidget(lb)

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
