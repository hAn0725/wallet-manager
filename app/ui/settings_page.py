"""设置页 —— 分类管理、数据导入导出、备份恢复、关于。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from app.services import category_service, recurring_service, settings_service
from app.ui.widgets import _apply_shadow
from app.utils import design_tokens as dtk
from app.utils.helpers import format_money


class CategoryDialog(QDialog):
    def __init__(self, cat=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑分类" if cat else "新增分类")
        self._cat = cat
        self._build()

    def _build(self):
        f = QFormLayout(self)
        self.name = QLineEdit()
        self.icon = QLineEdit()
        self.icon.setPlaceholderText("一个 emoji,如 🍜")
        self.type = QComboBox()
        self.type.addItem("支出", "expense")
        self.type.addItem("收入", "income")
        self.type.setEnabled(self._cat is None)   # 编辑时不改类型
        f.addRow("名称", self.name)
        f.addRow("图标", self.icon)
        f.addRow("类型", self.type)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("保存")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        f.addRow(btns)
        if self._cat:
            self.name.setText(self._cat.name)
            self.icon.setText(self._cat.icon)
            self.type.setCurrentIndex(0 if self._cat.type == "expense" else 1)

    def get_data(self):
        return {
            "name": self.name.text().strip(),
            "icon": self.icon.text().strip(),
            "type": self.type.currentData(),
        }


class RecurringDialog(QDialog):
    """新增/编辑固定收支。"""

    def __init__(self, recurring=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑固定收支" if recurring else "新增固定收支")
        self._r = recurring
        self.setMinimumWidth(dtk.DIALOG_MIN_W)
        self._build()

    def _build(self):
        f = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("如:生活费 / 话费 / 视频会员")
        self.type = QComboBox()
        self.type.addItem("收入", "income")
        self.type.addItem("支出", "expense")
        self.type.currentIndexChanged.connect(self._reload_cat)
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0.01, 100000000)
        self.amount.setDecimals(2)
        self.amount.setPrefix("¥ ")
        self.category = QComboBox()
        self.day = QSpinBox()
        self.day.setRange(1, 28)
        self.day.setSuffix(" 号")
        self.note = QLineEdit()
        self.note.setPlaceholderText("备注(可选)")
        f.addRow("名称", self.name)
        f.addRow("类型", self.type)
        f.addRow("金额", self.amount)
        f.addRow("分类", self.category)
        f.addRow("每月到账日", self.day)
        f.addRow("备注", self.note)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("保存")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        f.addRow(btns)
        self._reload_cat()
        if self._r:
            self.name.setText(self._r.name)
            self.type.setCurrentIndex(0 if self._r.type == "income" else 1)
            self._reload_cat()
            self.amount.setValue(self._r.amount)
            self.day.setValue(self._r.day_of_month)
            self.note.setText(self._r.note)
            idx = self.category.findData(self._r.category_id)
            if idx >= 0:
                self.category.setCurrentIndex(idx)

    def _reload_cat(self, *_):
        from app.services import category_service
        self.category.clear()
        type_ = self.type.currentData()
        for c in category_service.list_categories(type_):
            self.category.addItem(f"{c.icon} {c.name}", c.id)

    def get_data(self):
        return {
            "name": self.name.text().strip(),
            "amount": round(self.amount.value(), 2),
            "type": self.type.currentData(),
            "category_id": self.category.currentData(),
            "day_of_month": self.day.value(),
            "note": self.note.text().strip(),
        }


class TemplateEditDialog(QDialog):
    """编辑单个常用记账模板。"""

    def __init__(self, tpl: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑模板" if tpl else "新增模板")
        self._tpl = tpl or {}
        self.setMinimumWidth(dtk.DIALOG_MIN_W)
        self._build()

    def _build(self):
        f = QFormLayout(self)
        self.icon = QLineEdit()
        self.icon.setPlaceholderText("emoji,如 🍜")
        self.label = QLineEdit()
        self.label.setPlaceholderText("如:午饭")
        self.type_combo = QComboBox()
        self.type_combo.addItem("支出", "expense")
        self.type_combo.addItem("收入", "income")
        self.type_combo.currentIndexChanged.connect(self._reload_cat)
        self.category = QComboBox()
        self.note = QLineEdit()
        self.note.setPlaceholderText("备注(可选)")
        f.addRow("图标", self.icon)
        f.addRow("名称", self.label)
        f.addRow("类型", self.type_combo)
        f.addRow("分类", self.category)
        f.addRow("备注", self.note)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("保存")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        f.addRow(btns)
        if self._tpl:
            self.icon.setText(self._tpl.get("icon", ""))
            self.label.setText(self._tpl.get("label", ""))
            t = self._tpl.get("type", "expense")
            self.type_combo.setCurrentIndex(0 if t == "expense" else 1)
            self._reload_cat()
            idx = self.category.findText(self._tpl.get("category", ""))
            if idx >= 0:
                self.category.setCurrentIndex(idx)
            self.note.setText(self._tpl.get("note", ""))
        else:
            self._reload_cat()

    def _reload_cat(self, *_):
        from app.services import category_service
        self.category.clear()
        t = self.type_combo.currentData()
        for c in category_service.list_categories(t):
            self.category.addItem(c.name, c.name)

    def get_data(self):
        return {
            "icon": self.icon.text().strip(),
            "label": self.label.text().strip(),
            "type": self.type_combo.currentData(),
            "category": self.category.currentText(),
            "note": self.note.text().strip(),
        }


class TemplateManagerDialog(QDialog):
    """常用记账模板管理:新增/编辑/删除/上移下移排序。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("常用记账模板")
        self.setMinimumSize(dtk.DIALOG_REPORT_W, dtk.DIALOG_MIN_W)
        self._templates = settings_service.get_templates()
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)
        tip = QLabel("首页快捷记账模板。点击后只需输入金额即可记账。")
        tip.setObjectName("SubMuted")
        root.addWidget(tip)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["图标", "名称", "类型", "分类", "备注"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(lambda r, c: self._edit(r))
        root.addWidget(self.table)

        ops = QHBoxLayout()
        b_add = QPushButton("新增")
        b_add.clicked.connect(self._add)
        b_edit = QPushButton("编辑")
        b_edit.clicked.connect(lambda: self._edit(self.table.currentRow()))
        b_del = QPushButton("删除")
        b_del.clicked.connect(self._delete)
        b_up = QPushButton("↑ 上移")
        b_up.clicked.connect(lambda: self._move(-1))
        b_down = QPushButton("↓ 下移")
        b_down.clicked.connect(lambda: self._move(1))
        for b in (b_add, b_edit, b_del, b_up, b_down):
            ops.addWidget(b)
        ops.addStretch()
        b_done = QPushButton("完成")
        b_done.setObjectName("Primary")
        b_done.clicked.connect(self.accept)
        ops.addWidget(b_done)
        root.addLayout(ops)
        self._load()

    def _load(self):
        self.table.setRowCount(len(self._templates))
        for i, t in enumerate(self._templates):
            self.table.setItem(i, 0, QTableWidgetItem(t.get("icon", "")))
            self.table.setItem(i, 1, QTableWidgetItem(t.get("label", "")))
            self.table.setItem(i, 2, QTableWidgetItem("收入" if t.get("type") == "income" else "支出"))
            self.table.setItem(i, 3, QTableWidgetItem(t.get("category", "")))
            self.table.setItem(i, 4, QTableWidgetItem(t.get("note", "")))

    def _add(self):
        dlg = TemplateEditDialog(parent=self)
        if dlg.exec() == TemplateEditDialog.Accepted:
            d = dlg.get_data()
            if not d["label"]:
                return
            self._templates.append(d)
            self._save_and_load()

    def _edit(self, row):
        if not (0 <= row < len(self._templates)):
            return
        dlg = TemplateEditDialog(self._templates[row], self)
        if dlg.exec() == TemplateEditDialog.Accepted:
            d = dlg.get_data()
            if not d["label"]:
                return
            self._templates[row] = d
            self._save_and_load()

    def _delete(self):
        row = self.table.currentRow()
        if not (0 <= row < len(self._templates)):
            return
        if QMessageBox.question(self, "确认删除",
                                f"删除模板「{self._templates[row].get('label','')}」?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._templates.pop(row)
        self._save_and_load()

    def _move(self, delta):
        row = self.table.currentRow()
        new_row = row + delta
        if not (0 <= row < len(self._templates)) or not (0 <= new_row < len(self._templates)):
            return
        self._templates[row], self._templates[new_row] = self._templates[new_row], self._templates[row]
        self._load()
        self.table.setCurrentCell(new_row, 0)

    def _save_and_load(self):
        settings_service.save_templates(self._templates)
        self._load()


class SettingsPage(QWidget):
    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(*dtk.PAGE_MARGINS)
        root.setSpacing(dtk.PAGE_SPACING)

        title = QLabel("设置与数据管理")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._tab_categories(), "分类管理")
        tabs.addTab(self._tab_recurring(), "固定收支")
        tabs.addTab(self._tab_data(), "数据导入导出")
        tabs.addTab(self._tab_about(), "关于")
        root.addWidget(tabs)

    # --------------------------------------------------------- 分类管理

    def _tab_categories(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(10)
        head = QHBoxLayout()
        self.btn_add_cat = QPushButton("＋ 新增分类")
        self.btn_add_cat.setObjectName("Primary")
        self.btn_add_cat.setCursor(Qt.PointingHandCursor)
        self.btn_add_cat.clicked.connect(self._add_category)
        head.addWidget(self.btn_add_cat)
        head.addStretch()
        self.cat_type_filter = QComboBox()
        self.cat_type_filter.addItem("全部", None)
        self.cat_type_filter.addItem("支出", "expense")
        self.cat_type_filter.addItem("收入", "income")
        self.cat_type_filter.currentIndexChanged.connect(self._load_categories)
        head.addWidget(QLabel("筛选"))
        head.addWidget(self.cat_type_filter)
        v.addLayout(head)

        self.cat_table = QTableWidget(0, 5)
        self.cat_table.setHorizontalHeaderLabels(["类型", "图标", "名称", "账单数", "操作"])
        self.cat_table.verticalHeader().setVisible(False)
        self.cat_table.setEditTriggers(QTableWidget.NoEditTriggers)
        h = self.cat_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.cat_table.cellDoubleClicked.connect(self._edit_category)
        v.addWidget(self.cat_table)
        return w

    def _load_categories(self, *_):
        tf = self.cat_type_filter.currentData()
        cats = category_service.list_categories(tf)
        self.cat_table.setRowCount(len(cats))
        for i, c in enumerate(cats):
            type_item = QTableWidgetItem("支出" if c.type == "expense" else "收入")
            icon_item = QTableWidgetItem(c.icon)
            name_item = QTableWidgetItem(c.name)
            if c.is_default:
                name_item.setData(Qt.UserRole, "default")
            cnt = category_service.category_transaction_count(c.id)
            cnt_item = QTableWidgetItem(str(cnt))
            cnt_item.setTextAlignment(Qt.AlignCenter)
            op_item = QTableWidgetItem("双击编辑")
            self.cat_table.setItem(i, 0, type_item)
            self.cat_table.setItem(i, 1, icon_item)
            self.cat_table.setItem(i, 2, name_item)
            self.cat_table.setItem(i, 3, cnt_item)
            self.cat_table.setItem(i, 4, op_item)
            self.cat_table.item(i, 0).setData(Qt.UserRole, c.id)
            # 第 4 列放删除按钮
            del_btn = QPushButton("删除")
            del_btn.setObjectName("Danger")
            del_btn.setFixedHeight(26)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(lambda _, cid=c.id: self._delete_category(cid))
            self.cat_table.setCellWidget(i, 4, del_btn)

    def _delete_category(self, cid: int):
        cat = category_service.get_category(cid)
        if not cat:
            return
        cnt = category_service.category_transaction_count(cid)
        msg = f"确定删除分类「{cat.name}」吗?"
        if cnt > 0:
            msg += f"\n该分类下有 {cnt} 条账单,删除后账单将变为未分类。"
        if QMessageBox.question(self, "确认删除", msg,
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            category_service.delete_category(cid)
            self._load_categories()
            if self.parent_window:
                self.parent_window.refresh_all()
        except ValueError as e:
            QMessageBox.warning(self, "删除失败", str(e))
        except Exception as e:  # noqa
            QMessageBox.critical(self, "删除失败", str(e))

    def _add_category(self):
        dlg = CategoryDialog(parent=self)
        if dlg.exec() == CategoryDialog.Accepted:
            d = dlg.get_data()
            try:
                category_service.add_category(d["name"], d["icon"], d["type"])
                self._load_categories()
                if self.parent_window:
                    self.parent_window.refresh_all()
            except ValueError as e:
                QMessageBox.warning(self, "输入有误", str(e))

    def _edit_category(self, row, col):
        item = self.cat_table.item(row, 0)
        if item is None:
            return
        cid = item.data(Qt.UserRole)
        cat = category_service.get_category(cid)
        if not cat:
            return
        dlg = CategoryDialog(cat, self)
        if dlg.exec() == CategoryDialog.Accepted:
            d = dlg.get_data()
            try:
                category_service.update_category(cid, d["name"], d["icon"])
                self._load_categories()
                if self.parent_window:
                    self.parent_window.refresh_all()
            except ValueError as e:
                QMessageBox.warning(self, "输入有误", str(e))

    # --------------------------------------------------------- 数据管理

    def _tab_data(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(12)

        # 数据库信息
        info_card = QFrame()
        info_card.setObjectName("Card")
        ic = QVBoxLayout(info_card)
        ic.setContentsMargins(18, 14, 18, 14)
        ic.addWidget(QLabel("数据库位置"))
        self.lbl_db = QLabel(settings_service.get_db_path())
        self.lbl_db.setObjectName("SubMuted")
        self.lbl_db.setWordWrap(True)
        ic.addWidget(self.lbl_db)
        _apply_shadow(info_card)
        v.addWidget(info_card)

        # 导出
        exp = QFrame()
        exp.setObjectName("Card")
        ev = QVBoxLayout(exp)
        ev.setContentsMargins(18, 14, 18, 14)
        ev.addWidget(QLabel("数据导出"))
        r = QHBoxLayout()
        b_json = QPushButton("导出 JSON(全量)")
        b_json.clicked.connect(self._export_json)
        b_csv = QPushButton("导出 CSV(账单)")
        b_csv.clicked.connect(self._export_csv)
        r.addWidget(b_json)
        r.addWidget(b_csv)
        r.addStretch()
        ev.addLayout(r)
        _apply_shadow(exp)
        v.addWidget(exp)

        # 导入
        imp = QFrame()
        imp.setObjectName("Card")
        iv = QVBoxLayout(imp)
        iv.setContentsMargins(18, 14, 18, 14)
        iv.addWidget(QLabel("数据导入(JSON)"))
        r2 = QHBoxLayout()
        b_import_merge = QPushButton("导入并合并")
        b_import_merge.clicked.connect(lambda: self._import("merge"))
        b_import_replace = QPushButton("导入并替换(清空现有数据)")
        b_import_replace.setObjectName("Danger")
        b_import_replace.clicked.connect(lambda: self._import("replace"))
        r2.addWidget(b_import_merge)
        r2.addWidget(b_import_replace)
        r2.addStretch()
        iv.addLayout(r2)
        tip = QLabel("「替换」模式会先清空当前所有账单/分类/预算再导入,请谨慎操作。")
        tip.setObjectName("SubMuted")
        tip.setWordWrap(True)
        iv.addWidget(tip)
        _apply_shadow(imp)
        v.addWidget(imp)

        # 备份恢复
        bak = QFrame()
        bak.setObjectName("Card")
        bv = QVBoxLayout(bak)
        bv.setContentsMargins(18, 14, 18, 14)
        bv.addWidget(QLabel("数据库备份 / 恢复"))
        r3 = QHBoxLayout()
        b_backup = QPushButton("备份数据库")
        b_backup.clicked.connect(self._backup)
        b_restore = QPushButton("从备份恢复")
        b_restore.setObjectName("Danger")
        b_restore.clicked.connect(self._restore)
        r3.addWidget(b_backup)
        r3.addWidget(b_restore)
        r3.addStretch()
        bv.addLayout(r3)
        rt = QLabel("恢复会用备份文件覆盖当前数据库,操作前请先备份。")
        rt.setObjectName("SubMuted")
        bv.addWidget(rt)
        _apply_shadow(bak)
        v.addWidget(bak)

        v.addStretch()
        return w

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出 JSON", "finance.json", "JSON (*.json)")
        if not path:
            return
        try:
            n = settings_service.export_json(path)
            QMessageBox.information(self, "导出成功", f"已导出 {n} 条账单到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", "transactions.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            n = settings_service.export_csv(path)
            QMessageBox.information(self, "导出成功", f"已导出 {n} 条账单到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _import(self, mode):
        path, _ = QFileDialog.getOpenFileName(self, "选择 JSON 文件", "", "JSON (*.json)")
        if not path:
            return
        msg = ("确认以「合并」方式导入吗?已存在的记录会被更新,新记录会被添加。"
               if mode == "merge"
               else "⚠️ 确认以「替换」方式导入吗?这会清空当前所有数据后用文件内容覆盖,不可撤销!")
        if QMessageBox.question(self, "确认导入", msg,
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            n = settings_service.import_json(path, mode)
            self.parent_window and self.parent_window.refresh_all()
            QMessageBox.information(self, "导入成功", f"已导入 {n} 条账单。")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    def _backup(self):
        import datetime as dt
        default = f"finance_backup_{dt.date.today().isoformat()}.db"
        path, _ = QFileDialog.getSaveFileName(self, "备份数据库", default, "SQLite (*.db)")
        if not path:
            return
        try:
            settings_service.backup_via_sqlite(path)
            QMessageBox.information(self, "备份成功", f"已备份到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "备份失败", str(e))

    def _restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择备份文件", "", "SQLite (*.db)")
        if not path:
            return
        if QMessageBox.question(
            self, "确认恢复",
            "⚠️ 恢复会用备份文件覆盖当前数据库!\n建议先用「备份数据库」保存当前数据。\n\n确定继续吗?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        try:
            settings_service.restore_database(path)
            self.parent_window and self.parent_window.refresh_all()
            QMessageBox.information(self, "恢复成功", "数据库已从备份恢复,请重新打开软件以确保数据一致。")
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", str(e))

    # --------------------------------------------------------- 固定收支

    def _tab_recurring(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(10)
        head = QHBoxLayout()
        b_add = QPushButton("＋ 新增固定收支")
        b_add.setObjectName("Primary")
        b_add.setCursor(Qt.PointingHandCursor)
        b_add.clicked.connect(self._add_recurring)
        head.addWidget(b_add)
        head.addStretch()
        v.addLayout(head)

        tip = QLabel("设置每月固定到账的收入(如生活费)或固定扣款的支出(如话费/会员)。"
                     "到账日当天会在首页提醒,可一键记入,每月只提醒一次。")
        tip.setObjectName("SubMuted")
        tip.setWordWrap(True)
        v.addWidget(tip)

        self.rec_table = QTableWidget(0, 6)
        self.rec_table.setHorizontalHeaderLabels(["类型", "名称", "金额", "日期", "启用", "操作"])
        self.rec_table.verticalHeader().setVisible(False)
        self.rec_table.setEditTriggers(QTableWidget.NoEditTriggers)
        h = self.rec_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.rec_table.cellDoubleClicked.connect(self._edit_recurring)
        v.addWidget(self.rec_table)
        return w

    def _load_recurring(self):
        items = recurring_service.list_recurring()
        self.rec_table.setRowCount(len(items))
        for i, r in enumerate(items):
            type_item = QTableWidgetItem("收入" if r.type == "income" else "支出")
            type_item.setForeground(Qt.darkGreen if r.type == "income" else Qt.red)
            name_item = QTableWidgetItem(r.name)
            amt_item = QTableWidgetItem(format_money(r.amount))
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            day_item = QTableWidgetItem(f"每月 {r.day_of_month} 号")
            day_item.setTextAlignment(Qt.AlignCenter)
            self.rec_table.setItem(i, 0, type_item)
            self.rec_table.setItem(i, 1, name_item)
            self.rec_table.setItem(i, 2, amt_item)
            self.rec_table.setItem(i, 3, day_item)
            self.rec_table.item(i, 0).setData(Qt.UserRole, r.id)

            toggle = QPushButton("✓ 启用" if r.enabled else "✗ 停用")
            toggle.setFixedHeight(26)
            toggle.setCursor(Qt.PointingHandCursor)
            toggle.clicked.connect(lambda _, rid=r.id: self._toggle_recurring(rid))
            self.rec_table.setCellWidget(i, 4, toggle)

            ops = QWidget()
            ops_layout = QHBoxLayout(ops)
            ops_layout.setContentsMargins(2, 2, 2, 2)
            ops_layout.setSpacing(4)
            edit = QPushButton("编辑")
            edit.setFixedHeight(26)
            edit.clicked.connect(lambda _, rid=r.id: self._open_recurring_editor(rid))
            delete = QPushButton("删除")
            delete.setObjectName("Danger")
            delete.setFixedHeight(26)
            delete.clicked.connect(lambda _, rid=r.id: self._delete_recurring(rid))
            ops_layout.addWidget(edit)
            ops_layout.addWidget(delete)
            self.rec_table.setCellWidget(i, 5, ops)

    def _add_recurring(self):
        dlg = RecurringDialog(parent=self)
        if dlg.exec() == RecurringDialog.Accepted:
            d = dlg.get_data()
            try:
                recurring_service.add_recurring(
                    d["name"], d["amount"], d["type"], d["category_id"],
                    d["day_of_month"], d["note"])
                self._load_recurring()
                if self.parent_window:
                    self.parent_window.refresh_all()
                    self.parent_window.feedback("已添加固定收支")
            except ValueError as e:
                QMessageBox.warning(self, "输入有误", str(e))

    def _edit_recurring(self, row, col):
        rid = self.rec_table.item(row, 0).data(Qt.UserRole)
        self._open_recurring_editor(rid)

    def _open_recurring_editor(self, rid: int):
        r = recurring_service.get_recurring(rid)
        if not r:
            return
        dlg = RecurringDialog(r, self)
        if dlg.exec() == RecurringDialog.Accepted:
            d = dlg.get_data()
            try:
                recurring_service.update_recurring(
                    rid, d["name"], d["amount"], d["type"], d["category_id"],
                    d["day_of_month"], d["note"])
                self._load_recurring()
                if self.parent_window:
                    self.parent_window.refresh_all()
                    self.parent_window.feedback("已更新固定收支")
            except ValueError as e:
                QMessageBox.warning(self, "输入有误", str(e))

    def _toggle_recurring(self, rid: int):
        recurring_service.toggle_enabled(rid)
        self._load_recurring()
        if self.parent_window:
            self.parent_window.refresh_all()
            self.parent_window.feedback("已更新固定收支状态")

    def _delete_recurring(self, rid: int):
        r = recurring_service.get_recurring(rid)
        if not r:
            return
        if QMessageBox.question(
            self, "确认删除", f"删除固定收支「{r.name}」吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        recurring_service.delete_recurring(rid)
        self._load_recurring()
        if self.parent_window:
            self.parent_window.refresh_all()
            self.parent_window.feedback("已删除固定收支")

    # --------------------------------------------------------- 关于

    def _tab_about(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 8, 4, 4)
        v.setSpacing(8)
        v.addWidget(QLabel("大学生个人财务管理助手"))
        sub = QLabel(
            "本地优先 · 无需联网 · 数据保存在本地\n\n"
            "核心理念:不仅记录钱花到哪里,更帮助判断接下来应该怎么花。\n\n"
            "技术栈:Python + PySide6 + SQLite"
        )
        sub.setObjectName("SubMuted")
        sub.setWordWrap(True)
        v.addWidget(sub)
        v.addStretch()
        return w

    def refresh(self):
        self._load_categories()
        if hasattr(self, "rec_table"):
            self._load_recurring()
