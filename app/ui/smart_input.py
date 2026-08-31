"""自然语言快速记账 —— 首页输入框 + 确认对话框。

流程: 输入文本 → 解析 → 展示结果(可编辑) → 确认 → 写入数据库 → 全页刷新。
"""
from __future__ import annotations

from PySide6.QtCore import QDate, QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDoubleSpinBox,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout,
)

from app.services import category_service, finance_service
from app.services.natural_language_parser import parse
from app.services.statistics_service import recent_categories
from app.utils import design_tokens as dtk
from app.utils.helpers import format_money, today


class _EnterConfirmFilter(QObject):
    """任意输入框按 Enter 即确认记账(连续记账无需动鼠标)。"""

    def __init__(self, dialog):
        super().__init__(dialog)
        self._dlg = dialog

    def eventFilter(self, watched, event):
        if (event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)):
            self._dlg._confirm()
            return True
        return super().eventFilter(watched, event)


def _install_enter_filter(widget, dialog):
    widget.installEventFilter(_EnterConfirmFilter(dialog))


class SmartInputDialog(QDialog):
    """自然语言解析确认对话框:展示解析结果,用户可编辑后确认记账。"""

    def __init__(self, text: str = "", parent_window=None, parent=None,
                 template: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("确认记账")
        self.setMinimumWidth(dtk.DIALOG_MIN_W)
        self._parent_window = parent_window
        self._text = text
        self._template = template or None
        # 模板模式:直接按模板预填,金额留空待用户输入
        if self._template:
            from app.services.natural_language_parser import ParseResult
            self._result = ParseResult(
                amount=None,
                transaction_type=self._template.get("type", "expense"),
                category_name=self._template.get("category", "其他"),
                date=None, note=self._template.get("note", ""),
                confidence="medium",
                category_uncertain=False,
                raw=f"{self._template.get('icon', '')} {self._template.get('label', '')}",
            )
        else:
            self._result = parse(text)
        self._build()
        self._populate()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 22)
        root.setSpacing(10)

        # 标题 + 结果摘要
        title = QLabel("快速记账")
        title.setStyleSheet("font-size:18px;font-weight:700;color:#1d1d1f;")
        root.addWidget(title)
        if self._result.raw:
            raw = QLabel(f"输入: {self._result.raw}")
            raw.setObjectName("SubMuted")
            root.addWidget(raw)

        # 卡片展示解析结果
        card = QFrame()
        card.setObjectName("Card")
        f = QFormLayout(card)
        f.setContentsMargins(18, 14, 18, 14)
        f.setSpacing(8)

        # 金额
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 100000000)
        self.amount.setDecimals(2)
        self.amount.setPrefix("¥ ")
        f.addRow("金额", self.amount)

        # 类型
        self.type_combo = QComboBox()
        self.type_combo.addItems(["支出", "收入"])
        self.type_combo.currentIndexChanged.connect(self._reload_cats)
        f.addRow("类型", self.type_combo)

        # 分类
        self.category = QComboBox()
        f.addRow("分类", self.category)

        # 日期
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        f.addRow("日期", self.date)

        # 备注
        self.note = QLineEdit()
        f.addRow("备注", self.note)

        # 任意输入框按 Enter 即确认记账
        for w in (self.amount, self.category, self.date, self.note):
            _install_enter_filter(w, self)

        # 置信度提示
        r0 = self._result
        if r0.confidence == "low":
            conf_text = "⚠️ 未识别到金额,请手动填写"
        elif r0.confidence == "medium" and r0.category_uncertain:
            conf_text = "分类按近期使用习惯推荐,请确认后记账"
        elif r0.confidence == "medium":
            conf_text = "部分信息不确定,请检查日期/分类"
        else:
            conf_text = "识别结果准确 ✓"
        conf_color = {"high": "#34c759", "medium": "#ff9500", "low": "#ff3b30"}
        self.conf_label = QLabel(conf_text)
        self.conf_label.setStyleSheet(f"color:{conf_color[r0.confidence]};"
                                       "font-weight:600;")
        f.addRow("", self.conf_label)

        # 操作提示:Enter 确认记账 / Esc 取消
        hint = QLabel("按 Enter 确认记账 · Esc 取消")
        hint.setObjectName("SubMuted")
        hint.setAlignment(Qt.AlignRight)
        f.addRow("", hint)

        root.addWidget(card)

        # 确认/取消
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton("确认记账")
        self.ok.setObjectName("Primary")
        self.ok.setCursor(Qt.PointingHandCursor)
        self.ok.clicked.connect(self._confirm)
        btns.addWidget(cancel)
        btns.addWidget(self.ok)
        root.addLayout(btns)

    def _populate(self):
        """用解析结果预填控件。"""
        r = self._result
        # 金额
        if r.amount is not None:
            self.amount.setValue(r.amount)
        # 类型
        self.type_combo.setCurrentIndex(0 if r.transaction_type == "expense" else 1)
        # 分类(_reload_cats 会按近期使用习惯排序)
        self._reload_cats()
        if r.category_name and not r.category_uncertain:
            idx = self.category.findText(r.category_name)
            if idx >= 0:
                self.category.setCurrentIndex(idx)
        elif self.category.count() > 0:
            # 分类不确定:默认选中最近使用的第一项(仍需用户确认才写入)
            self.category.setCurrentIndex(0)
        # 日期
        if r.date:
            y, m, d = r.date.split("-")
            self.date.setDate(QDate(int(y), int(m), int(d)))
        else:
            self.date.setDate(QDate(today()))
        # 备注
        self.note.setText(r.note or "")

    def showEvent(self, event):
        """默认焦点:优先聚焦最可能需要修改的字段。
        解析正确时聚焦金额,直接回 Enter 即可确认(连续记账不碰鼠标)。"""
        super().showEvent(event)
        r = self._result
        if r.amount is None:
            self.amount.setFocus()
        elif r.date is None:
            self.date.setFocus()
        elif r.category_uncertain:
            self.category.setFocus()
        else:
            self.amount.setFocus()
            self.amount.selectAll()

    def _reload_cats(self, *_):
        self.category.clear()
        type_ = "expense" if self.type_combo.currentIndex() == 0 else "income"
        cats = category_service.list_categories(type_)
        by_name = {c.name: c.id for c in cats}
        # 近期使用频率排序在前,其余按默认顺序在后 —— 让分类建议贴合个人习惯
        recent = recent_categories(type_)
        ordered_names = [n for n in recent if n in by_name]
        all_names = [c.name for c in cats]
        for name in ordered_names + [n for n in all_names if n not in ordered_names]:
            self.category.addItem(name, by_name[name])

    def _confirm(self):
        """确认记账:验证 → 写入 → 刷新 → 关闭。"""
        if self.amount.value() <= 0:
            QMessageBox.warning(self, "金额无效", "金额必须大于 0")
            return
        try:
            type_ = "expense" if self.type_combo.currentIndex() == 0 else "income"
            cid = self.category.currentData()
            d = self.date.date().toString("yyyy-MM-dd")
            note = self.note.text().strip()
            finance_service.add_transaction(self.amount.value(), cid, type_, d, note)
            self.accept()
            # 全页刷新 + 反馈
            if self._parent_window:
                self._parent_window.refresh_all()
                self._parent_window.feedback(
                    f"已记账 {format_money(self.amount.value())} · {note or self.category.currentText()}"
                )
        except ValueError as e:
            QMessageBox.warning(self, "输入有误", str(e))
        except Exception as e:  # noqa
            QMessageBox.critical(self, "出错了", str(e))