"""通用工具:金额/日期格式化、预算周期计算、全局样式表。"""
from __future__ import annotations

import datetime
import os
import sys
from decimal import Decimal, ROUND_HALF_UP


# ---------------------------------------------------------------------------
# 金额格式化
# ---------------------------------------------------------------------------

def round2(amount) -> float:
    """四舍五入到 2 位小数,避免浮点误差。"""
    return float(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_money(amount, with_symbol: bool = True) -> str:
    """¥1,174  或  1,174.50

    整数不显示小数,非整数保留两位;千分位逗号。
    负数显示为 -¥180(负号在符号前)。
    """
    if amount is None:
        amount = 0
    amount = round2(amount)
    negative = amount < 0
    abs_amount = abs(amount)
    if abs(abs_amount - round(abs_amount)) < 1e-9:
        text = f"{int(round(abs_amount)):,}"
    else:
        text = f"{abs_amount:,.2f}"
    prefix = "-" if negative else ""
    sym = "¥" if with_symbol else ""
    return f"{prefix}{sym}{text}"


def parse_money(text: str) -> float:
    """宽松解析用户输入的金额:去逗号、空格、¥/￥/$。"""
    if text is None:
        return 0.0
    s = str(text).strip()
    if not s:
        return 0.0
    for ch in (",", " ", "¥", "￥", "$", "元"):
        s = s.replace(ch, "")
    try:
        return round2(float(s))
    except ValueError:
        raise ValueError("请输入有效的金额")


# ---------------------------------------------------------------------------
# 日期工具
# ---------------------------------------------------------------------------

def today() -> datetime.date:
    return datetime.date.today()


def to_date(value) -> datetime.date:
    """接受 date / 'YYYY-MM-DD' / 'YYYY-MM-DD HH:MM:SS'。
    None 或空串默认返回今天(记账时省略日期即代表今天)。"""
    if value is None:
        return today()
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    s = str(value).strip()
    if not s:
        return today()
    return datetime.date.fromisoformat(s[:10])


def iso(d) -> str:
    return d.isoformat() if isinstance(d, (datetime.date, datetime.datetime)) else str(d)


def _month_days(year: int, month: int) -> int:
    if month == 12:
        nxt = datetime.date(year + 1, 1, 1)
    else:
        nxt = datetime.date(year, month + 1, 1)
    return (nxt - datetime.timedelta(days=1)).day


def safe_date(year: int, month: int, day: int) -> datetime.date:
    """构造日期,day 超过该月天数时自动取当月最后一天(避免 2/30 报错)。"""
    day = min(day, _month_days(year, month))
    return datetime.date(year, month, day)


def get_cycle_range(period_type: str = "natural_month",
                    start_day: int = 1,
                    ref: datetime.date | None = None) -> tuple[datetime.date, datetime.date]:
    """返回当前预算周期的 [start, end] 闭区间。

    - natural_month: 本月 1 日 ~ 本月最后一天
    - custom: 以 start_day 为起点的月度周期
        今天 >= start_day -> 本月 start_day ~ 下月 start_day-1
        今天 <  start_day -> 上月 start_day ~ 本月 start_day-1
    """
    ref = ref or today()
    if period_type == "natural_month" or start_day <= 1:
        start = datetime.date(ref.year, ref.month, 1)
        end = safe_date(ref.year, ref.month, _month_days(ref.year, ref.month))
        return start, end

    if ref.day >= start_day:
        start = safe_date(ref.year, ref.month, start_day)
        # 下月 start_day - 1
        ny, nm = (ref.year + 1, 1) if ref.month == 12 else (ref.year, ref.month + 1)
        end = safe_date(ny, nm, start_day) - datetime.timedelta(days=1)
        return start, end
    else:
        py, pm = (ref.year - 1, 12) if ref.month == 1 else (ref.year, ref.month - 1)
        start = safe_date(py, pm, start_day)
        end = safe_date(ref.year, ref.month, start_day) - datetime.timedelta(days=1)
        return start, end


def cycle_days(period_type: str, start_day: int, ref: datetime.date | None = None) -> tuple[int, int, int]:
    """返回 (总天数, 已过天数, 剩余天数)。剩余天数至少为 0。"""
    ref = ref or today()
    start, end = get_cycle_range(period_type, start_day, ref)
    total = (end - start).days + 1
    elapsed = (ref - start).days + 1       # 今天算作已过 1 天
    elapsed = max(1, min(elapsed, total))
    remaining = max(0, total - elapsed)
    return total, elapsed, remaining


# ---------------------------------------------------------------------------
# 全局样式表
# ---------------------------------------------------------------------------

STYLE_SHEET = """
/* ============ 全局:苹果风 ============ */
QWidget {
    font-family: "SF Pro Display", "SF Pro Text", "PingFang SC",
                 "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px; color: #1d1d1f;
}
QMainWindow, QDialog { background: #f5f5f7; }
QWidget#PageRoot { background: #f5f5f7; }
QStackedWidget { background: #f5f5f7; }
QScrollArea { background: #f5f5f7; border: none; }

/* ============ 侧边栏(浅色毛玻璃风) ============ */
#SideBar { background: #ffffff; border-right: 1px solid #e5e5ea; }
#SideBar QListWidget {
    background: transparent; border: none; outline: none;
    color: #1d1d1f; font-size: 14px; padding: 4px 8px;
}
#SideBar QListWidget::item {
    padding: 9px 14px; margin: 2px 4px; border-radius: 10px;
}
#SideBar QListWidget::item:hover { background: #f0f0f2; }
#SideBar QListWidget::item:selected {
    background: #0071e3; color: #ffffff; font-weight: 600;
}
#SideBar QListWidget::item:selected:disabled { background: transparent; color:#86868b; }
QLabel#AppTitle { color:#1d1d1f; font-size:18px; font-weight:700; padding:22px 18px 2px 18px; }
QLabel#AppSub   { color:#86868b; font-size:11px; letter-spacing:1px; padding:0 18px 14px 18px; }
QLabel#PageTitle { color:#1d1d1f; font-size:22px; font-weight:700; }
QLabel#TodayBadge {
    color:#0071e3; font-size:12px; font-weight:600;
    background:#e8f0fe; border-radius:980px; padding:4px 12px;
}

/* ============ 卡片(白底大圆角,阴影由 GraphicsEffect 提供) ============ */
QFrame#Card {
    background: #ffffff; border: none; border-radius: 16px;
}
QLabel#CardTitle { color:#86868b; font-size:12px; font-weight:600; letter-spacing:0.5px; }
QLabel#BigNumber  { color:#1d1d1f; font-size:30px; font-weight:700; }
QLabel#HugeNumber { color:#1d1d1f; font-size:46px; font-weight:800; letter-spacing:-1px; }
QLabel#SubMuted   { color:#86868b; font-size:12px; }
QLabel#WarnLabel   { color:#ff9500; font-weight:600; }
QLabel#DangerLabel { color:#ff3b30; font-weight:700; }
QLabel#OkLabel     { color:#34c759; font-weight:600; }

/* ============ 输入控件 ============ */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTextEdit, QPlainTextEdit {
    background: #ffffff; border: 1px solid #d2d2d7; border-radius: 10px;
    padding: 8px 10px; selection-background-color: #0071e3; color:#1d1d1f;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QTextEdit:focus { border: 1.5px solid #0071e3; }
QLineEdit:disabled, QComboBox:disabled { background:#f5f5f7; color:#86868b; }

/* 下拉框与日期下拉箭头 */
QComboBox::drop-down, QDateEdit::drop-down {
    subcontrol-origin: padding; subcontrol-position: top right;
    width: 22px; border: none; border-left: 1px solid #e5e5ea;
}
QComboBox::down-arrow, QDateEdit::down-arrow {
    width: 0; height: 0; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid #86868b;
    margin-right: 7px;
}
QComboBox QAbstractItemView {
    background: #ffffff; border: 1px solid #d2d2d7; border-radius: 10px;
    selection-background-color: #e8f0fe; selection-color: #1d1d1f;
    outline: none; padding: 6px;
}
/* 数字微调器去掉上下箭头按钮(直接输入更简洁) */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button { width: 0; height: 0; border: none; }
/* 日期选择器:隐藏向上微调按钮,保留向下(日历弹窗)按钮 */
QDateEdit::up-button { width: 0; height: 0; border: none; }
QDateEdit::down-button { width: 26px; border: none; border-left: 1px solid #e5e5ea; }
QDateEdit::down-button:hover { background: #f5f5f7; }

/* ============ 按钮(胶囊形) ============ */
QPushButton {
    background: #ffffff; color: #1d1d1f; border: 1px solid #d2d2d7;
    border-radius: 980px; padding: 7px 18px; font-weight: 500;
}
QPushButton:hover { background: #f5f5f7; }
QPushButton:pressed { background: #e8e8ed; }
QPushButton:focus { outline: none; }
QPushButton#Primary { background: #0071e3; color: #ffffff; border: none; }
QPushButton#Primary:hover { background: #0077ed; }
QPushButton#Primary:pressed { background: #006edb; }
QPushButton#Danger { background: #ff3b30; color: #ffffff; border: none; }
QPushButton#Danger:hover { background: #ff453a; }
QPushButton:disabled { background:#f5f5f7; color:#aeaeb2; border:none; }

/* ============ 表格 ============ */
QTableWidget {
    background: #ffffff; alternate-background-color: #fafafa;
    border: 1px solid #e5e5ea; border-radius: 14px; gridline-color:#f0f0f2;
    outline: none;
}
QTableWidget::item { padding: 8px 10px; border: none; }
QTableWidget::item:selected { background: #e8f0fe; color: #1d1d1f; }
QHeaderView::section {
    background: #fafafa; color: #86868b; border: none;
    border-bottom: 1px solid #e5e5ea; padding: 10px; font-weight:600;
}
QTableCornerButton::section { background: #fafafa; border: none; }

/* ============ 进度条 ============ */
QProgressBar {
    background: #e8e8ed; border: none; border-radius: 999px;
    text-align: center; color: #1d1d1f; font-size: 11px; height: 14px;
}
QProgressBar::chunk { background: #0071e3; border-radius: 999px; }

/* ============ 滚动条 ============ */
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical {
    background: #d2d2d7; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #aeaeb2; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal {
    background: #d2d2d7; border-radius: 5px; min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #aeaeb2; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ============ 标签页 ============ */
QTabWidget::pane { border: none; }
QTabBar::tab {
    padding: 8px 16px; border: none; border-radius: 8px;
    color: #86868b; background: transparent; font-weight: 500;
}
QTabBar::tab:hover { background: #f0f0f2; }
QTabBar::tab:selected { color: #1d1d1f; font-weight: 600; }

/* ============ 日历弹窗 ============ */
QCalendarWidget QToolButton { border: none; border-radius: 6px; padding: 4px 8px; }
QCalendarWidget QToolButton:hover { background: #f0f0f2; }
QCalendarWidget QAbstractItemView {
    selection-background-color: #0071e3; selection-color: #ffffff;
    alternate-background-color: #fafafa; background: #ffffff; border: none;
}
QCalendarWidget QWidget#navigationbar { background: #ffffff; }

/* ============ 其他 ============ */
QMenu { background: #ffffff; border: 1px solid #e5e5ea; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 6px 24px; border-radius: 6px; }
QMenu::item:selected { background: #e8f0fe; color: #1d1d1f; }
QToolTip { background:#1d1d1f; color:#fff; border:none; padding:6px 10px; border-radius:8px; }
QMessageBox, QInputDialog { background:#ffffff; }
QMessageBox QLabel { min-width: 260px; }
QDialogButtonBox QPushButton { min-width: 64px; }
QGroupBox { border: 1px solid #e5e5ea; border-radius: 12px; margin-top: 12px; padding: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color:#86868b; }
"""


_CJK_FONT_READY = False


def install_cjk_font() -> None:
    """为 Qt 注册一个可用的中文回退字体（若系统字体发现失败）。

    部分精简版 Windows/CI 的 Qt 字体数据库不会自动枚举 CJK 字体，
    即使字体文件实际存在，界面仍会显示方框。优先使用 Windows 自带字体；
    找不到时静默跳过，让系统默认字体接管。
    """
    global _CJK_FONT_READY
    if _CJK_FONT_READY or sys.platform != "win32":
        return
    try:
        from PySide6.QtGui import QFontDatabase
        font_dir = os.path.join(os.environ.get("WINDIR", r"C:\\Windows"), "Fonts")
        for filename in ("NotoSansSC-VF.ttf", "msyh.ttc", "simhei.ttf", "simsun.ttc"):
            path = os.path.join(font_dir, filename)
            if os.path.isfile(path) and QFontDatabase.addApplicationFont(path) >= 0:
                _CJK_FONT_READY = True
                return
    except Exception:
        # 字体仅影响展示，绝不能阻断财务数据功能或应用启动。
        return


def today_display(ref=None) -> str:
    """返回 '今天 · 2026年8月21日 星期四' 格式。"""
    d = ref or today()
    weeks = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return f"今天 · {d.year}年{d.month}月{d.day}日 {weeks[d.weekday()]}"
