"""数据库表结构定义与默认种子数据。"""
from __future__ import annotations

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    icon        TEXT    NOT NULL DEFAULT '',
    type        TEXT    NOT NULL CHECK(type IN ('income','expense')),
    is_default  INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    amount      REAL    NOT NULL,
    category_id INTEGER,
    type        TEXT    NOT NULL CHECK(type IN ('income','expense')),
    date        TEXT    NOT NULL,                 -- YYYY-MM-DD
    note        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);
CREATE INDEX IF NOT EXISTS idx_transactions_cat  ON transactions(category_id);

CREATE TABLE IF NOT EXISTS budgets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    amount       REAL    NOT NULL,
    period_type  TEXT    NOT NULL CHECK(period_type IN ('natural_month','custom')),
    start_day    INTEGER NOT NULL DEFAULT 1,
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS savings_goals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    target_amount  REAL    NOT NULL,
    current_amount REAL    NOT NULL DEFAULT 0,
    note           TEXT    NOT NULL DEFAULT '',
    created_at     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# 默认分类 —— 支出
DEFAULT_EXPENSE_CATEGORIES = [
    ("餐饮", "🍜"),
    ("购物", "🛒"),
    ("交通", "🚇"),
    ("娱乐", "🎮"),
    ("学习", "📚"),
    ("生活用品", "🏠"),
    ("医疗", "💊"),
    ("礼物", "🎁"),
    ("其他", "📦"),
]

# 默认分类 —— 收入
DEFAULT_INCOME_CATEGORIES = [
    ("生活费", "💰"),
    ("兼职", "💼"),
    ("奖学金", "🏆"),
    ("红包", "🧧"),
    ("其他收入", "💵"),
]
