"""可复用 UI 组件:卡片(带柔和阴影)、统计卡、金额标签等。苹果风。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QSizePolicy,
    QVBoxLayout, QWidget,
)


def _apply_shadow(widget: QWidget, blur: int = 35, y: int = 6, alpha: int = 22):
    """给卡片加柔和投影,营造苹果风悬浮感。"""
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, y)
    eff.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(eff)


def card(parent_layout, title: str = "") -> QFrame:
    """创建一张卡片并加入布局。返回卡片本身,可在其上 layout.addWidget(...)。"""
    f = QFrame()
    f.setObjectName("Card")
    v = QVBoxLayout(f)
    v.setContentsMargins(20, 18, 20, 20)
    v.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setObjectName("CardTitle")
        v.addWidget(t)
    _apply_shadow(f)
    parent_layout.addWidget(f)
    return f


def _make_label(text: str, obj: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName(obj)
    lb.setAlignment(Qt.AlignCenter)
    return lb


class StatCard(QWidget):
    """小型统计卡:标题 + 大数值 + 可选副标题。"""

    def __init__(self, title: str, value: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(6)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        v.addWidget(t)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("BigNumber")
        self.value_label.setAlignment(Qt.AlignLeft)
        v.addWidget(self.value_label)
        self.sub_label = QLabel(subtitle)
        self.sub_label.setObjectName("SubMuted")
        self.sub_label.setWordWrap(True)
        v.addWidget(self.sub_label)
        _apply_shadow(self)

    def set_value(self, value: str):
        self.value_label.setText(value)

    def set_subtitle(self, subtitle: str):
        self.sub_label.setText(subtitle)

    def set_value_object(self, obj: str):
        self.value_label.setObjectName(obj)
        self.value_label.style().unpolish(self.value_label)
        self.value_label.style().polish(self.value_label)
