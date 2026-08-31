"""预算管理页 —— 设置月度预算与周期,展示预算使用情况与提醒。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from app.services import budget_service
from app.utils import design_tokens as dtk
from app.utils.helpers import format_money
from app.ui.widgets import _apply_shadow


class BudgetPage(QWidget):
    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(*dtk.PAGE_MARGINS)
        root.setSpacing(dtk.PAGE_SPACING)

        title = QLabel("预算管理")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        # ---- 当前预算使用卡片 ----
        use_card = QFrame()
        use_card.setObjectName("Card")
        uv = QVBoxLayout(use_card)
        uv.setContentsMargins(20, 18, 20, 18)
        uv.setSpacing(10)
        uv.addWidget(QLabel("本月预算使用情况"))
        self.lbl_remaining = QLabel("")
        self.lbl_remaining.setObjectName("HugeNumber")
        uv.addWidget(self.lbl_remaining)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setFixedHeight(18)
        self.progress.setTextVisible(False)
        uv.addWidget(self.progress)
        self.lbl_detail = QLabel("")
        self.lbl_detail.setObjectName("SubMuted")
        self.lbl_detail.setWordWrap(True)
        uv.addWidget(self.lbl_detail)
        self.lbl_alert = QLabel("")
        uv.addWidget(self.lbl_alert)
        _apply_shadow(use_card)
        root.addWidget(use_card)

        # ---- 预算设置卡片 ----
        set_card = QFrame()
        set_card.setObjectName("Card")
        sv = QVBoxLayout(set_card)
        sv.setContentsMargins(20, 18, 20, 18)
        sv.setSpacing(10)
        sv.addWidget(QLabel("设置预算"))

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("月度预算"))
        self.spin_amount = QDoubleSpinBox()
        self.spin_amount.setRange(0, 100000000)
        self.spin_amount.setDecimals(2)
        self.spin_amount.setSingleStep(100)
        self.spin_amount.setPrefix("¥ ")
        r1.addWidget(self.spin_amount)
        r1.addStretch()
        sv.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("预算周期"))
        self.combo_period = QComboBox()
        self.combo_period.addItem("自然月(1 日 ~ 月底)", "natural_month")
        self.combo_period.addItem("自定义起始日", "custom")
        self.combo_period.currentIndexChanged.connect(self._on_period_change)
        r2.addWidget(self.combo_period)
        r2.addWidget(QLabel("起始日"))
        self.spin_start = QSpinBox()
        self.spin_start.setRange(1, 28)
        self.spin_start.setSuffix(" 日")
        self.spin_start.setEnabled(False)
        r2.addWidget(self.spin_start)
        r2.addStretch()
        sv.addLayout(r2)

        r3 = QHBoxLayout()
        self.btn_save = QPushButton("保存预算")
        self.btn_save.setObjectName("Primary")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self._save)
        r3.addWidget(self.btn_save)
        r3.addStretch()
        sv.addLayout(r3)
        _apply_shadow(set_card)
        root.addWidget(set_card)

        # 说明
        tip = QLabel(
            "提醒规则:消费达到 80% 提示注意预算,达到 100% 提示预算用完,"
            "超出预算时在首页与统计页明显标注超支金额。\n"
            "本月剩余预算 = 月度预算 − 本周期总支出。"
        )
        tip.setObjectName("SubMuted")
        tip.setWordWrap(True)
        root.addWidget(tip)
        root.addStretch()

    def _on_period_change(self, idx):
        is_custom = self.combo_period.currentData() == "custom"
        self.spin_start.setEnabled(is_custom)

    def refresh(self):
        cfg = budget_service.get_budget()
        if cfg:
            idx = self.combo_period.findData(cfg.period_type)
            self.combo_period.setCurrentIndex(idx if idx >= 0 else 0)
            self.spin_start.setValue(cfg.start_day)
            self.spin_amount.setValue(cfg.amount)
        self._on_period_change(self.combo_period.currentIndex())

        summary = budget_service.get_cycle_summary()
        self.lbl_remaining.setText(format_money(summary.remaining))
        ratio = max(0.0, min(1.0, summary.used_ratio))
        self.progress.setValue(int(ratio * 1000))
        color = "#3b82f6"
        if summary.alert_level == "warning":
            color = "#d97706"
        elif summary.alert_level in ("danger", "over"):
            color = "#ef4444"
        self.progress.setStyleSheet(
            f"QProgressBar::chunk{{background:{color};border-radius:8px;}}"
        )
        self.lbl_detail.setText(
            f"预算 {format_money(summary.budget)}　·　已消费 {format_money(summary.spent)}"
            f"　·　已用 {int(round(ratio*100))}%　·　"
            f"周期 {summary.start_date} ~ {summary.end_date}　·　"
            f"剩余 {summary.days_remaining} 天"
        )

        if summary.budget <= 0:
            self.lbl_alert.setText("⚠️ 尚未设置预算,请先设置月度预算。")
            self.lbl_alert.setStyleSheet("color:#d97706;font-weight:600;")
        elif summary.alert_level == "over":
            over = summary.spent - summary.budget
            self.lbl_alert.setText(f"❌ 已超支 {format_money(over)} ! 请控制消费。")
            self.lbl_alert.setStyleSheet("color:#b91c1c;font-weight:700;font-size:15px;")
        elif summary.alert_level == "danger":
            self.lbl_alert.setText("⚠️ 预算已用完,后续消费将超支。")
            self.lbl_alert.setStyleSheet("color:#b91c1c;font-weight:600;")
        elif summary.alert_level == "warning":
            self.lbl_alert.setText("⏰ 消费已达 80%,请注意控制预算。")
            self.lbl_alert.setStyleSheet("color:#d97706;font-weight:600;")
        else:
            self.lbl_alert.setText("✅ 预算使用正常,继续保持。")
            self.lbl_alert.setStyleSheet("color:#15803d;font-weight:600;")

    def _save(self):
        try:
            amount = self.spin_amount.value()
            period = self.combo_period.currentData()
            start_day = self.spin_start.value() if period == "custom" else 1
            budget_service.set_budget(amount, period, start_day)
            self.refresh()
            if self.parent_window:
                self.parent_window.refresh_all()
            QMessageBox.information(self, "已保存", "预算已更新。")
        except ValueError as e:
            QMessageBox.warning(self, "输入有误", str(e))
