"""储蓄目标页 —— 新增/编辑/删除目标,调整资金,展示进度。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from app.services import savings_service
from app.services.savings_service import SavingsGoal
from app.utils import design_tokens as dtk
from app.utils.helpers import format_money
from app.ui.widgets import _apply_shadow


class GoalDialog(QDialog):
    def __init__(self, goal: SavingsGoal = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑目标" if goal else "新增储蓄目标")
        self.setMinimumWidth(dtk.DIALOG_MIN_W)
        self._goal = goal
        self._build()

    def _build(self):
        f = QFormLayout(self)
        self.name = QLineEdit()
        self.target = QDoubleSpinBox()
        self.target.setRange(1, 100000000)
        self.target.setDecimals(2)
        self.target.setPrefix("¥ ")
        self.current = QDoubleSpinBox()
        self.current.setRange(0, 100000000)
        self.current.setDecimals(2)
        self.current.setPrefix("¥ ")
        self.note = QTextEdit()
        self.note.setFixedHeight(60)

        f.addRow("目标名称", self.name)
        f.addRow("目标金额", self.target)
        f.addRow("当前金额", self.current)
        f.addRow("备注", self.note)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("保存")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        f.addRow(btns)

        if self._goal:
            self.name.setText(self._goal.name)
            self.target.setValue(self._goal.target_amount)
            self.current.setValue(self._goal.current_amount)
            self.note.setPlainText(self._goal.note)
            self.current.setMaximum(self._goal.target_amount)

    def get_data(self):
        return {
            "name": self.name.text().strip(),
            "target_amount": round(self.target.value(), 2),
            "current_amount": round(self.current.value(), 2),
            "note": self.note.toPlainText().strip(),
        }


class SavingsPage(QWidget):
    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(*dtk.PAGE_MARGINS)
        root.setSpacing(dtk.PAGE_SPACING)

        title = QLabel("储蓄目标")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        head = QHBoxLayout()
        self.btn_add = QPushButton("＋ 新增目标")
        self.btn_add.setObjectName("Primary")
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self._add)
        head.addWidget(self.btn_add)
        head.addStretch()
        root.addLayout(head)

        self.list_holder = QVBoxLayout()
        self.list_holder.setSpacing(12)
        root.addLayout(self.list_holder)
        root.addStretch()

    def refresh(self):
        # 清空
        while self.list_holder.count():
            it = self.list_holder.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        goals = savings_service.list_goals()
        if not goals:
            empty = QLabel("还没有储蓄目标,点击「新增目标」开始攒钱吧 💰")
            empty.setObjectName("SubMuted")
            self.list_holder.addWidget(empty)
            return
        for g in goals:
            self.list_holder.addWidget(self._goal_card(g))

    def _goal_card(self, g: SavingsGoal) -> QWidget:
        card = QWidget()
        card.setObjectName("Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(8)

        row = QHBoxLayout()
        name = QLabel(f"{g.name}")
        name.setStyleSheet("font-size:16px;font-weight:700;color:#1d1d1f;")
        row.addWidget(name)
        row.addStretch()
        amt = QLabel(f"{format_money(g.current_amount)} / {format_money(g.target_amount)}")
        amt.setStyleSheet("font-size:15px;font-weight:600;")
        row.addWidget(amt)
        v.addLayout(row)

        bar = QProgressBar()
        bar.setRange(0, 100)
        pct = int(round(g.progress_pct * 100))
        bar.setValue(pct)
        bar.setFixedHeight(16)
        bar.setTextVisible(True)
        bar.setFormat(f"{pct}%")
        v.addWidget(bar)

        info = QLabel(
            f"已完成 {pct}%　·　距离目标还差 {format_money(g.remaining)}"
            + (f"　·　{g.note}" if g.note else "")
        )
        info.setObjectName("SubMuted")
        info.setWordWrap(True)
        v.addWidget(info)

        ops = QHBoxLayout()
        ops.setSpacing(8)
        add_box = QDoubleSpinBox()
        add_box.setRange(0.01, 100000000)
        add_box.setDecimals(2)
        add_box.setPrefix("＋¥ ")
        sub_box = QDoubleSpinBox()
        sub_box.setRange(0.01, 100000000)
        sub_box.setDecimals(2)
        sub_box.setPrefix("−¥ ")
        btn_add = QPushButton("存入")
        btn_add.setObjectName("Primary")
        btn_add.clicked.connect(lambda _, gid=g.id, b=add_box: self._adjust(gid, b.value()))
        btn_sub = QPushButton("取出")
        btn_sub.clicked.connect(lambda _, gid=g.id, b=sub_box: self._adjust(gid, -b.value()))
        btn_edit = QPushButton("编辑")
        btn_edit.clicked.connect(lambda _, gl=g: self._edit(gl))
        btn_del = QPushButton("删除")
        btn_del.setStyleSheet("color:#b91c1c;")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.clicked.connect(lambda _, gl=g: self._delete(gl))
        ops.addWidget(QLabel("存入"))
        ops.addWidget(add_box)
        ops.addWidget(QLabel("取出"))
        ops.addWidget(sub_box)
        ops.addWidget(btn_add)
        ops.addWidget(btn_sub)
        ops.addStretch()
        ops.addWidget(btn_edit)
        ops.addWidget(btn_del)
        v.addLayout(ops)
        _apply_shadow(card)
        return card

    # ---------------------------------------------------------------- 操作

    def _add(self):
        dlg = GoalDialog(parent=self)
        if dlg.exec() == GoalDialog.Accepted:
            d = dlg.get_data()
            try:
                savings_service.add_goal(d["name"], d["target_amount"],
                                         d["current_amount"], d["note"])
                self.refresh()
                if self.parent_window:
                    self.parent_window.refresh_all()
                    self.parent_window.feedback(f"已创建目标「{d['name']}」")
            except ValueError as e:
                QMessageBox.warning(self, "输入有误", str(e))

    def _edit(self, g: SavingsGoal):
        dlg = GoalDialog(g, self)
        if dlg.exec() == GoalDialog.Accepted:
            d = dlg.get_data()
            try:
                savings_service.update_goal(g.id, d["name"],
                                            d["target_amount"], d["note"])
                self.refresh()
                if self.parent_window:
                    self.parent_window.refresh_all()
                    self.parent_window.feedback("已更新目标")
            except ValueError as e:
                QMessageBox.warning(self, "输入有误", str(e))

    def _delete(self, g: SavingsGoal):
        if QMessageBox.question(
            self, "确认删除",
            f"确定删除储蓄目标「{g.name}」吗?\n该目标的资金记录将被移除。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        savings_service.delete_goal(g.id)
        self.refresh()
        if self.parent_window:
            self.parent_window.refresh_all()
            self.parent_window.feedback(f"已删除目标「{g.name}」")

    def _adjust(self, gid: int, delta: float):
        if abs(delta) < 0.01:
            return
        try:
            savings_service.adjust_amount(gid, delta)
            self.refresh()
            if self.parent_window:
                self.parent_window.refresh_all()
                if delta > 0:
                    self.parent_window.feedback(f"已存入 {format_money(delta)}")
                else:
                    self.parent_window.feedback(f"已取出 {format_money(-delta)}")
        except ValueError as e:
            QMessageBox.warning(self, "操作失败", str(e))
