"""设置页 —— 分类管理、数据导入导出、备份恢复、关于。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from app.services import category_service, settings_service
from app.ui.widgets import _apply_shadow


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


class SettingsPage(QWidget):
    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel("设置与数据管理")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._tab_categories(), "分类管理")
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
