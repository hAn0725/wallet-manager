"""Design Tokens —— 统一的设计系统常量(间距/字号/圆角/按钮高度/页面留白)。

说明:
- 视觉颜色、字体、边框、进度条等由全局 QSS(STYLE_SHEET in helpers.py)统一管理,
  这里是 Python 侧布局/尺寸的单一事实来源,避免魔法数字散落在各页面。
- 修改全局间距/留白时,只需改这里,无需逐页排查。
"""
from __future__ import annotations

# ---------------- 布局留白 ----------------
PAGE_MARGINS = (24, 20, 24, 20)     # 页面根布局 contentMargins(left, top, right, bottom)
PAGE_SPACING = 14                    # 页面根布局子控件间距
CARD_MARGINS = (18, 16, 18, 18)     # 卡片内边距
CARD_SPACING = 10                    # 卡片内子控件间距

# ---------------- 尺寸 ----------------
BUTTON_HEIGHT = 36                   # 主操作按钮高度(首页记账等)
CHIP_HEIGHT = 30                     # 模板 chip / 小型按钮高度
SMALL_BUTTON_W = None                # (占位,便于统一调整小按钮宽度时使用)
TABLE_MAX_RECENT_H = 196             # 首页「最近记录」表格最大高度

# ---------------- 对话框 ----------------
DIALOG_MIN_W = 380                   # 编辑/确认类对话框最小宽度
DIALOG_REPORT_W = 460                # 报告类对话框宽度

# ---------------- 字号(与 QSS 对应,供 Python 内联样式引用) ----------------
FONT_TITLE_PX = 20
FONT_CARD_TITLE_PX = 12
FONT_BIG_PX = 30
FONT_HUGE_PX = 46
FONT_INPUT_PX = 14