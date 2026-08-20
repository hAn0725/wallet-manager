"""记账页 —— 顶部快速记账,下方账单列表(筛选/搜索/编辑/删除)。"""
from __future__ import annotations

from datetime import date as _date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QDialog, QFormLayout, QDialogButtonBox,
    QDoubleSpinBox, QTextEdit, QStackedWidget,
)

from app.services import category_service, finance_service
from app.services.finance_service import Transaction
from app.utils.helpers import format_money, parse_money, today


class QuickAddBar(QWidget):
    """快速记账条:金额 + 分类 + 日期 + 备注 + 类型,一键添加。"""

    submitted = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self._build()

    def _build(self):
        h = QHBoxLayout(self)
        h.setContentsMargins(18, 14, 18, 14)
        h.setSpacing(10)

        # 类型切换
        self.type_combo = QComboBox()
        self.type_combo.addItems(["支出", "收入"])
        self.type_combo.currentIndexChanged.connect(self._reload_categories)
        h.addWidget(QLabel("类型"))
        h.addWidget(self.type_combo)

        h.addSpacing(6)
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("金额")
        self.amount.setFixedWidth(120)
        self.amount.returnPressed.connect(self._submit)
        h.addWidget(QLabel("金额"))
        h.addWidget(self.amount)

        h.addSpacing(6)
        self.category = QComboBox()
        self.category.setMinimumWidth(140)
        h.addWidget(QLabel("分类"))
        h.addWidget(self.category)

        h.addSpacing(6)
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDate(QDate(self._d()))
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setFixedWidth(130)
        h.addWidget(QLabel("日期"))
        h.addWidget(self.date)

        h.addSpacing(6)
        self.note = QLineEdit()
        self.note.setPlaceholderText("备注(可选)")
        self.note.setMinimumWidth(140)
        self.note.returnPressed.connect(self._submit)
        h.addWidget(self.note)

        h.addStretch()
        self.btn = QPushButton("记一笔")
        self.btn.setObjectName("Primary")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self._submit)
        h.addWidget(self.btn)

        self._reload_categories()

    def _d(self):
        return today()

    def _reload_categories(self, *_):
        self.category.clear()
        type_ = "expense" if self.type_combo.currentIndex() == 0 else "income"
        self._cats = category_service.list_categories(type_)
        for c in self._cats:
            self.category.addItem(f"{c.icon} {c.name}", c.id)

    def _submit(self):
        try:
            type_ = "expense" if self.type_combo.currentIndex() == 0 else "income"
            amt_text = self.amount.text()
            if not amt_text.strip():
                QMessageBox.information(self, "提示", "请输入金额")
                return
            amt = parse_money(amt_text)
            if amt <= 0:
                QMessageBox.warning(self, "金额无效", "金额必须大于 0")
                return
            cid = self.category.currentData()
            d = self.date.date().toString("yyyy-MM-dd")
            note = self.note.text()
            finance_service.add_transaction(amt, cid, type_, d, note)
            # 重置
            self.amount.clear()
            self.note.clear()
            self.amount.setFocus()
            self.submitted.emit()
        except ValueError as e:
            QMessageBox.warning(self, "输入有误", str(e))
        except Exception as e:  # noqa
            QMessageBox.critical(self, "出错了", str(e))


class TransactionDialog(QDialog):
    """编辑账单对话框。"""

    def __init__(self, txn: Transaction = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑账单" if txn else "新增账单")
        self.setMinimumWidth(380)
        self._txn = txn
        self._build()

    def _build(self):
        f = QFormLayout(self)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["支出", "收入"])
        self.type_combo.currentIndexChanged.connect(self._reload)
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 100000000)
        self.amount.setDecimals(2)
        self.amount.setSingleStep(1)
        self.category = QComboBox()
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.note = QTextEdit()
        self.note.setFixedHeight(60)

        f.addRow("类型", self.type_combo)
        f.addRow("金额", self.amount)
        f.addRow("分类", self.category)
        f.addRow("日期", self.date)
        f.addRow("备注", self.note)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("保存")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        f.addRow(btns)

        # 预填
        if self._txn:
            self.type_combo.setCurrentIndex(0 if self._txn.type == "expense" else 1)
            self._reload()
            self.amount.setValue(self._txn.amount)
            self.date.setDate(QDate(*map(int, self._txn.date.split("-"))))
            self.note.setPlainText(self._txn.note)
            idx = self.category.findData(self._txn.category_id)
            if idx >= 0:
                self.category.setCurrentIndex(idx)
        else:
            self._reload()
            self.date.setDate(QDate(self._d()))

    def _d(self):
        return today()

    def _reload(self, *_):
        self.category.clear()
        type_ = "expense" if self.type_combo.currentIndex() == 0 else "income"
        cats = category_service.list_categories(type_)
        for c in cats:
            self.category.addItem(f"{c.icon} {c.name}", c.id)

    def get_data(self):
        type_ = "expense" if self.type_combo.currentIndex() == 0 else "income"
        return {
            "amount": round(self.amount.value(), 2),
            "category_id": self.category.currentData(),
            "type": type_,
            "date": self.date.date().toString("yyyy-MM-dd"),
            "note": self.note.toPlainText().strip(),
        }


class TransactionPage(QWidget):
    """记账页 = 快速记账条 + 筛选 + 账单表格。"""

    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel("记账与账单")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.quick = QuickAddBar()
        self.quick.submitted.connect(self.refresh)
        root.addWidget(self.quick)

        # 筛选行
        filt = QHBoxLayout()
        filt.setSpacing(8)
        self.f_type = QComboBox()
        self.f_type.addItems(["全部类型", "支出", "收入"])
        self.f_cat = QComboBox()
        self.f_cat.addItem("全部分类", None)
        self._load_filter_categories()
        self.f_keyword = QLineEdit()
        self.f_keyword.setPlaceholderText("搜索备注…")
        self.f_keyword.returnPressed.connect(self.refresh)
        self.btn_search = QPushButton("筛选")
        self.btn_search.clicked.connect(self.refresh)
        self.btn_reset = QPushButton("重置")
        self.btn_reset.clicked.connect(self._reset_filters)
        for w in (QLabel("筛选:"), self.f_type, self.f_cat,
                  self.f_keyword, self.btn_search, self.btn_reset):
            filt.addWidget(w)
        filt.addStretch()
        root.addLayout(filt)

        # 账单表格
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["日期", "类型", "分类", "金额", "备注", "操作"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        root.addWidget(self.table)

    def _load_filter_categories(self):
        self.f_cat.clear()
        self.f_cat.addItem("全部分类", None)
        for c in category_service.list_categories():
            self.f_cat.addItem(f"{c.icon} {c.name} ({c.type})", c.id)

    def _reset_filters(self):
        self.f_type.setCurrentIndex(0)
        self.f_cat.setCurrentIndex(0)
        self.f_keyword.clear()
        self.refresh()

    def refresh(self):
        # 筛选条件
        t = self.f_type.currentIndex()
        type_ = None if t == 0 else ("expense" if t == 1 else "income")
        cid = self.f_cat.currentData()
        kw = self.f_keyword.text().strip()
        txns = finance_service.get_transactions(
            type_filter=type_, category_id=cid, keyword=kw,
        )

        # 刷新分类下拉(可能被新增)
        prev = self.f_cat.currentData()
        self._load_filter_categories()
        if prev is not None:
            idx = self.f_cat.findData(prev)
            if idx >= 0:
                self.f_cat.setCurrentIndex(idx)

        cat_map = finance_service.get_category_lookup()
        self.table.setRowCount(len(txns))
        for i, txn in enumerate(txns):
            name, icon, ctype = cat_map.get(txn.category_id, ("未分类", "", ""))
            date_item = QTableWidgetItem(txn.date)
            date_item.setData(Qt.UserRole, txn.id)
            type_item = QTableWidgetItem("支出" if txn.is_expense else "收入")
            type_item.setForeground(Qt.red if txn.is_expense else Qt.darkGreen)
            cat_item = QTableWidgetItem(f"{icon} {name}")
            amt_item = QTableWidgetItem(format_money(txn.amount))
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if txn.is_expense:
                amt_item.setForeground(Qt.red)
            note_item = QTableWidgetItem(txn.note)
            op_item = QTableWidgetItem("编辑/删除(双击编辑)")
            self.table.setItem(i, 0, date_item)
            self.table.setItem(i, 1, type_item)
            self.table.setItem(i, 2, cat_item)
            self.table.setItem(i, 3, amt_item)
            self.table.setItem(i, 4, note_item)
            self.table.setItem(i, 5, op_item)

        self.table.setRowCount(len(txns))

    def _on_double_click(self, row, col):
        item = self.table.item(row, 0)
        tid = item.data(Qt.UserRole)
        txn = finance_service.get_transaction(tid)
        if not txn:
            return
        dlg = TransactionDialog(txn, self)
        if dlg.exec() == TransactionDialog.Accepted:
            d = dlg.get_data()
            try:
                finance_service.update_transaction(tid, d["amount"], d["category_id"],
                                                   d["type"], d["date"], d["note"])
                self.refresh()
                if self.parent_window:
                    self.parent_window.refresh_all()
            except ValueError as e:
                QMessageBox.warning(self, "输入有误", str(e))
