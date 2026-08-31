"""消费统计页 —— 分类饼图、每日趋势柱状图、月度对比表。

优先使用 PySide6.QtCharts;若不可用则退化为纯表格。
"""
from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from app.services import budget_service, statistics_service
from app.utils import design_tokens as dtk
from app.utils.helpers import (
    _month_days, format_money, get_cycle_range, safe_date, today,
)

try:
    from PySide6.QtCharts import (QBarCategoryAxis, QBarSeries, QBarSet,
                                  QChart, QChartView, QPieSeries, QValueAxis)
    from PySide6.QtGui import QPainter
    HAS_CHARTS = True
except Exception:  # noqa
    HAS_CHARTS = False


class StatisticsPage(QWidget):
    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(*dtk.PAGE_MARGINS)
        root.setSpacing(dtk.PAGE_SPACING)

        title = QLabel("消费统计")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        head = QHBoxLayout()
        head.addWidget(QLabel("统计周期:"))
        self.cycle_combo = QComboBox()
        self.cycle_combo.addItem("本月(预算周期)", "cycle")
        self.cycle_combo.addItem("本月(自然月)", "month")
        self.cycle_combo.addItem("最近 30 天", "last30")
        self.cycle_combo.addItem("全部", "all")
        self.cycle_combo.currentIndexChanged.connect(self.refresh)
        head.addWidget(self.cycle_combo)
        head.addStretch()
        self.btn_report = QPushButton("📄 本月财务报告")
        self.btn_report.setObjectName("Primary")
        self.btn_report.setCursor(Qt.PointingHandCursor)
        self.btn_report.clicked.connect(self._show_report)
        head.addWidget(self.btn_report)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        head.addWidget(self.btn_refresh)
        root.addLayout(head)

        # 总额
        self.total_label = QLabel("")
        self.total_label.setStyleSheet("font-size:15px;font-weight:600;color:#0d2b3e;")
        root.addWidget(self.total_label)

        # 图表区
        charts = QHBoxLayout()
        charts.setSpacing(14)
        self.pie_holder = QWidget()
        pv = QVBoxLayout(self.pie_holder)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(QLabel("分类占比"))
        self.pie_view = None
        self.pie_table = QTableWidget(0, 4)
        self.pie_table.setHorizontalHeaderLabels(["分类", "金额", "占比", ""])
        self.pie_table.verticalHeader().setVisible(False)
        self.pie_table.setEditTriggers(QTableWidget.NoEditTriggers)
        ph = self.pie_table.horizontalHeader()
        ph.setSectionResizeMode(0, QHeaderView.Stretch)
        ph.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        ph.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        ph.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        pv.addWidget(self.pie_table)
        charts.addWidget(self.pie_holder, stretch=1)

        self.trend_holder = QWidget()
        tv = QVBoxLayout(self.trend_holder)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addWidget(QLabel("每日消费趋势"))
        self.trend_view = None
        charts.addWidget(self.trend_holder, stretch=1)
        root.addLayout(charts, stretch=2)

        # 月度对比表
        root.addWidget(QLabel("月度对比(本月 vs 上月)"))
        self.cmp_table = QTableWidget(0, 4)
        self.cmp_table.setHorizontalHeaderLabels(["分类", "上月", "本月", "变化"])
        self.cmp_table.verticalHeader().setVisible(False)
        self.cmp_table.setEditTriggers(QTableWidget.NoEditTriggers)
        ch = self.cmp_table.horizontalHeader()
        ch.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3):
            ch.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        root.addWidget(self.cmp_table)
        root.addStretch()

    # ----------------------------------------------------------------- 数据

    def _range(self):
        cfg = budget_service.get_budget()
        period_type = cfg.period_type if cfg else "natural_month"
        start_day = cfg.start_day if cfg else 1
        key = self.cycle_combo.currentData()
        ref = today()
        if key == "cycle":
            return get_cycle_range(period_type, start_day, ref)
        if key == "month":
            return (safe_date(ref.year, ref.month, 1),
                    safe_date(ref.year, ref.month, _month_days(ref.year, ref.month)))
        if key == "last30":
            return (ref - timedelta(days=29), ref)
        # all
        return (ref - timedelta(days=365 * 5), ref)

    def refresh(self):
        start, end = self._range()

        # 分类统计
        stats = statistics_service.category_stats(start, end)
        total = sum(s.amount for s in stats)
        self.total_label.setText(
            f"{start} ~ {end}　总支出 {format_money(total)}"
        )

        # 饼图(先用 deleteLater 回收旧视图,避免 setParent(None) 残留)
        if self.pie_view is not None:
            self.pie_view.deleteLater()
            self.pie_view = None
        self.pie_table.setRowCount(len(stats))
        colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
                  "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16"]
        if HAS_CHARTS:
            series = QPieSeries()
            for i, s in enumerate(stats):
                sl = series.append(f"{s.icon} {s.name}", s.amount)
                sl.setColor(colors[i % len(colors)])
                sl.setLabelVisible(True)
                # 标签位置枚举在不同 PySide6 版本命名空间不同,用 try 兼容
                try:
                    from PySide6.QtCharts import QPieSlice as _PS
                    pos = _PS.LabelPosition.InsideHorizontal  # 6.x scoped enum
                    sl.setLabelPosition(pos)
                except Exception:
                    pass
            chart = QChart()
            chart.addSeries(series)
            chart.setTitle("分类占比")
            chart.legend().setAlignment(Qt.AlignRight)
            chart.legend().setFont(self.font())
            self.pie_view = QChartView(chart)
            self.pie_view.setRenderHint(QPainter.Antialiasing)
            # 插到 table 之前
            pv = self.pie_holder.layout()
            pv.insertWidget(1, self.pie_view)

        for i, s in enumerate(stats):
            self.pie_table.setItem(i, 0, QTableWidgetItem(f"{s.icon} {s.name}"))
            mi = QTableWidgetItem(format_money(s.amount))
            mi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.pie_table.setItem(i, 1, mi)
            pc = QTableWidgetItem(f"{int(round(s.ratio*100))}%")
            pc.setTextAlignment(Qt.AlignCenter)
            self.pie_table.setItem(i, 2, pc)
            # 进度色块
            bar = QTableWidgetItem("")
            bar.setData(Qt.DisplayRole, "")
            self.pie_table.setItem(i, 3, bar)

        # 每日趋势
        if self.trend_view is not None:
            self.trend_view.deleteLater()
            self.trend_view = None
        trend = statistics_service.daily_trend(start, end)
        if HAS_CHARTS and any(d.amount > 0 for d in trend):
            bar_set = QBarSet("每日消费")
            bar_set.setColor("#3b82f6")
            categories = []
            for d in trend:
                bar_set.append(d.amount)
                categories.append(d.date[5:])  # MM-DD
            series = QBarSeries()
            series.append(bar_set)
            chart = QChart()
            chart.addSeries(series)
            axis_x = QBarCategoryAxis()
            axis_x.append(categories)
            chart.addAxis(axis_x, Qt.AlignBottom)
            series.attachAxis(axis_x)
            axis_y = QValueAxis()
            axis_y.setLabelFormat("%.0f")
            axis_y.setTitleText("金额(元)")
            chart.addAxis(axis_y, Qt.AlignLeft)
            series.attachAxis(axis_y)
            chart.legend().setVisible(False)
            chart.setTitle("每日消费")
            self.trend_view = QChartView(chart)
            self.trend_view.setRenderHint(QPainter.Antialiasing)
            tv = self.trend_holder.layout()
            tv.insertWidget(1, self.trend_view)
        elif not HAS_CHARTS:
            self.trend_view = QLabel("（QtCharts 不可用，每日趋势图表无法显示）")
            self.trend_view.setObjectName("SubMuted")
            tv = self.trend_holder.layout()
            tv.insertWidget(1, self.trend_view)

        # 月度对比
        cmp = statistics_service.monthly_comparison()
        self.cmp_table.setRowCount(len(cmp))
        for i, c in enumerate(cmp):
            self.cmp_table.setItem(i, 0, QTableWidgetItem(f"{c.icon} {c.category}"))
            for col, val in ((1, c.last), (2, c.this)):
                it = QTableWidgetItem(format_money(val))
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.cmp_table.setItem(i, col, it)
            if c.last == 0 and c.this == 0:
                txt = "—"
                color = "#7f8ea0"
            elif c.change_pct > 0:
                txt = f"↑ {int(round(c.change_pct*100))}%"
                color = "#b91c1c"
            elif c.change_pct < 0:
                txt = f"↓ {int(round(abs(c.change_pct)*100))}%"
                color = "#15803d"
            else:
                txt = "持平"
                color = "#7f8ea0"
            chg = QTableWidgetItem(txt)
            chg.setForeground(Qt.red if c.change_pct > 0 else
                               (Qt.darkGreen if c.change_pct < 0 else Qt.gray))
            chg.setTextAlignment(Qt.AlignCenter)
            chg.setData(Qt.UserRole, color)
            self.cmp_table.setItem(i, 3, chg)

    def _show_report(self):
        rep = statistics_service.monthly_report()
        dlg = MonthlyReportDialog(rep, self)
        dlg.exec()


class MonthlyReportDialog(QDialog):
    """「我的本月财务报告」对话框 —— 简洁易读的月度总结。"""

    def __init__(self, rep, parent=None):
        super().__init__(parent)
        self.setWindowTitle("本月财务报告")
        self.setMinimumWidth(dtk.DIALOG_REPORT_W)
        self._build(rep)

    def _build(self, rep):
        from app.ui.widgets import _apply_shadow

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 26)
        root.setSpacing(14)

        title = QLabel("我的本月财务报告")
        title.setStyleSheet("font-size:22px;font-weight:800;color:#1d1d1f;")
        root.addWidget(title)
        sub = QLabel(f"{rep.year} 年 {rep.month} 月")
        sub.setObjectName("SubMuted")
        root.addWidget(sub)

        if not rep.has_data:
            empty = QLabel("本月还没有任何收支记录。\n记几笔账后,这里会生成你的月度总结。")
            empty.setObjectName("SubMuted")
            empty.setWordWrap(True)
            root.addWidget(empty)
            root.addStretch()
            return

        # 结余卡
        net_card = QFrame()
        net_card.setObjectName("Card")
        nc = QVBoxLayout(net_card)
        nc.setContentsMargins(20, 16, 20, 18)
        nc.setSpacing(4)
        nlbl = QLabel("本月结余(收入 − 支出)")
        nlbl.setObjectName("CardTitle")
        nc.addWidget(nlbl)
        net_color = "#34c759" if rep.net >= 0 else "#ff3b30"
        nval = QLabel(format_money(rep.net))
        nval.setStyleSheet(f"font-size:32px;font-weight:800;color:{net_color};")
        nc.addWidget(nval)
        _apply_shadow(net_card)
        root.addWidget(net_card)

        # 收支明细网格
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        rows = [
            ("本月收入", format_money(rep.income), "#1d1d1f"),
            ("本月支出", format_money(rep.expense), "#ff3b30" if rep.expense else "#1d1d1f"),
            ("最大消费", f"{rep.top_category}　{format_money(rep.top_category_amount, False)}", "#1d1d1f"),
        ]
        if rep.budget > 0:
            overspend_txt = (f"超支 {format_money(rep.overspend)}" if rep.overspend > 0
                             else "未超支 ✓")
            rows.append(("预算情况", f"预算 {format_money(rep.budget, False)}　{overspend_txt}",
                         "#ff9500" if rep.overspend > 0 else "#34c759"))
        if rep.last_expense > 0 or rep.expense > 0:
            sign = "↑" if rep.expense_change_pct > 0 else ("↓" if rep.expense_change_pct < 0 else "—")
            pct = int(round(abs(rep.expense_change_pct) * 100))
            chg_color = "#ff3b30" if rep.expense_change_pct > 0 else "#34c759"
            rows.append(("环比上月",
                         f"{format_money(rep.last_expense, False)} → {format_money(rep.expense, False)}　{sign}{pct}%",
                         chg_color))
        if rep.savings_count > 0:
            rows.append(("储蓄进度",
                         f"{format_money(rep.savings_total, False)} / {format_money(rep.savings_target, False)}"
                         f"　({rep.savings_count} 个目标)",
                         "#0071e3"))
        for i, (k, v, color) in enumerate(rows):
            kl = QLabel(k)
            kl.setObjectName("CardTitle")
            vl = QLabel(v)
            vl.setStyleSheet(f"font-size:14px;font-weight:600;color:{color};")
            vl.setWordWrap(True)
            grid.addWidget(kl, i, 0)
            grid.addWidget(vl, i, 1)
        root.addLayout(grid)

        # 使用习惯
        ins = statistics_service.usage_insights()
        ins_title = QLabel("💡 本月使用习惯")
        ins_title.setStyleSheet("font-size:13px;font-weight:700;color:#1d1d1f;"
                                 "margin-top:6px;")
        root.addWidget(ins_title)
        ins_grid = QGridLayout()
        ins_grid.setHorizontalSpacing(12)
        ins_grid.setVerticalSpacing(4)
        ins_rows = [
            ("最易记账时间段", ins.peak_hour_range),
            ("日均支出笔数", f"约 {ins.avg_daily_bills} 笔"),
            ("最大单笔", f"{format_money(ins.max_amount)} · {ins.max_category}"),
            ("消费集中度", f"{int(round(ins.top_category_ratio*100))}% 集中在最大分类"),
        ]
        for i, (k, v) in enumerate(ins_rows):
            kl = QLabel(k)
            kl.setObjectName("CardTitle")
            vl = QLabel(v)
            vl.setStyleSheet("font-size:13px;font-weight:600;")
            ins_grid.addWidget(kl, i, 0)
            ins_grid.addWidget(vl, i, 1)
        root.addLayout(ins_grid)
        root.addStretch()
