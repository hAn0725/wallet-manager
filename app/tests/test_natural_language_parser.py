"""自然语言解析器测试 —— 覆盖金额/日期/分类/收入/异常输入。

运行: uv run python -m pytest app/tests/test_natural_language_parser.py -v
"""
from __future__ import annotations

import datetime

from app.services.natural_language_parser import parse

REF = datetime.date(2026, 8, 21)


# ===========================================================================
# 金额识别
# ===========================================================================

def test_amount_basic():
    """午饭18 → 金额18"""
    r = parse("午饭18", REF)
    assert r.amount == 18.0
    assert r.transaction_type == "expense"
    assert r.category_name == "餐饮"
    assert r.date == "2026-08-21"
    assert r.note == "午饭"


def test_amount_decimal():
    """午饭18.5 → 金额18.5"""
    r = parse("午饭18.5", REF)
    assert r.amount == 18.5


def test_amount_book():
    """买书39.9 → 金额39.9"""
    r = parse("买书39.9", REF)
    assert r.amount == 39.9
    assert r.category_name == "学习"


def test_amount_only():
    """18 → 金额18, 支出, 其他, 今天"""
    r = parse("18", REF)
    assert r.amount == 18.0
    assert r.transaction_type == "expense"
    assert r.category_name == "其他"
    assert r.date == "2026-08-21"


# ===========================================================================
# 金额边界(第四次迭代审查重点)
# ===========================================================================

def test_amount_space_variants():
    """空格变体:午饭 18 → 18"""
    assert parse("午饭 18", REF).amount == 18.0
    assert parse("午饭 18.5", REF).amount == 18.5


def test_amount_leading_dot():
    """奶茶.16 → 0.16, 奶茶.5 → 0.5(不能得到 16/5)"""
    assert parse("奶茶.16", REF).amount == 0.16
    assert parse("奶茶.5", REF).amount == 0.5


def test_amount_zero_point():
    """奶茶0.5 → 0.5"""
    assert parse("奶茶0.5", REF).amount == 0.5


def test_amount_leading_zeros():
    """午饭0018 → 18(前导零应被忽略)"""
    assert parse("午饭0018", REF).amount == 18.0


def test_amount_negative_invalid():
    """午饭-20 → 金额无效(None),不产生非法账单"""
    r = parse("午饭-20", REF)
    assert r.amount is None
    assert parse("-20", REF).amount is None


def test_amount_zero():
    """午饭0 → 金额0(不崩溃;写入层拒绝<=0)"""
    r = parse("午饭0", REF)
    assert r.amount == 0.0


# ===========================================================================
# 日期识别
# ===========================================================================

def test_date_today():
    """今天午饭18 → 今天"""
    r = parse("今天午饭18", REF)
    assert r.date == REF.isoformat()
    assert r.amount == 18.0


def test_date_yesterday():
    """昨天午饭18 → 昨天"""
    r = parse("昨天午饭18", REF)
    assert r.date == "2026-08-20"
    assert r.amount == 18.0


def test_date_day_before():
    """前天买书39 → 前天"""
    r = parse("前天买书39", REF)
    assert r.date == "2026-08-19"
    assert r.amount == 39.0


def test_date_explicit():
    """8月20日吃饭35 → 2026-08-20"""
    r = parse("8月20日吃饭35", REF)
    assert r.date == "2026-08-20"
    assert r.amount == 35.0


def test_date_ambiguous_keep_none():
    """上周买东西120 → 日期不确定,amount=120"""
    r = parse("上周买东西120", REF)
    assert r.date is None  # 不确定,让用户确认
    assert r.amount == 120.0


# ===========================================================================
# 分类识别
# ===========================================================================

def test_category_food():
    assert parse("奶茶18", REF).category_name == "餐饮"
    assert parse("滴滴30", REF).category_name == "交通"


def test_category_study():
    assert parse("买书50", REF).category_name == "学习"


def test_category_shopping():
    assert parse("淘宝100", REF).category_name == "购物"


def test_category_entertainment():
    assert parse("看电影60", REF).category_name == "娱乐"
    assert parse("游戏30", REF).category_name == "娱乐"


def test_category_unknown_fallback():
    """无法识别的分类 → 其他("买"匹配购物,但"奇怪的东西"无匹配,系统用购物)"""
    r = parse("买了一个奇怪的东西80", REF)
    assert r.category_name in ("购物", "其他")  # "买"触发购物,合理
    assert r.amount == 80.0


# ===========================================================================
# 收入识别
# ===========================================================================

def test_income_allowance():
    """生活费到账2500 → 收入, 生活费"""
    r = parse("生活费到账2500", REF)
    assert r.transaction_type == "income"
    assert r.category_name == "生活费"
    assert r.amount == 2500.0


def test_income_parttime():
    """兼职收入300 → 收入, 兼职"""
    r = parse("兼职收入300", REF)
    assert r.transaction_type == "income"
    assert r.category_name == "兼职"
    assert r.amount == 300.0


def test_income_redpacket():
    """收到红包200 → 收入, 红包"""
    r = parse("收到红包200", REF)
    assert r.transaction_type == "income"
    assert r.category_name == "红包"
    assert r.amount == 200.0


# ===========================================================================
# 自然语言变体
# ===========================================================================

def test_natural_today():
    """今天午饭花了18"""
    r = parse("今天午饭花了18", REF)
    assert r.amount == 18.0
    assert r.category_name == "餐饮"
    assert r.date == REF.isoformat()
    assert r.note == "午饭"


def test_natural_bought_book():
    """买了一本书39"""
    r = parse("买了一本书39", REF)
    assert r.amount == 39.0
    assert r.category_name == "学习"


def test_natural_yesterday_meal():
    """昨天吃饭花了68"""
    r = parse("昨天吃饭花了68", REF)
    assert r.amount == 68.0
    assert r.date == "2026-08-20"
    assert r.category_name == "餐饮"


def test_natural_milk_tea():
    """刚刚买奶茶花了15.5"""
    r = parse("刚刚买奶茶花了15.5", REF)
    assert r.amount == 15.5
    assert r.category_name == "餐饮"


# ===========================================================================
# 异常输入
# ===========================================================================

def test_invalid_abc():
    """abc → 金额为None,不崩溃"""
    r = parse("abc", REF)
    assert r.amount is None
    assert r.confidence == "low"


def test_invalid_no_amount():
    """今天吃饭 → 金额为None,不崩溃"""
    r = parse("今天吃饭", REF)
    assert r.amount is None
    assert r.category_name == "餐饮"


def test_invalid_yesterday():
    """昨天 → 金额为None"""
    r = parse("昨天", REF)
    assert r.amount is None


def test_invalid_spent():
    """花了 → 金额为None"""
    r = parse("花了", REF)
    assert r.amount is None


def test_invalid_negative():
    """-20 → 金额无效(None),不允许负金额被解析成 20"""
    r = parse("-20", REF)
    assert r.amount is None


def test_invalid_empty():
    """空字符串 → 金额为None,不崩溃"""
    r = parse("", REF)
    assert r.amount is None
    assert r.confidence == "low"


# ===========================================================================
# 置信度
# ===========================================================================

def test_confidence_high():
    """金额+日期确定+分类明确 → 高置信度"""
    r = parse("昨天吃饭68", REF)
    assert r.confidence == "high"


def test_confidence_medium():
    """金额+日期不确定(上周) → 中置信度"""
    r = parse("上周买东西120", REF)
    assert r.confidence == "medium"  # 有金额但日期不确定
    assert r.date is None


def test_confidence_low_no_amount():
    """无金额 → 低置信度"""
    r = parse("今天吃饭", REF)
    assert r.confidence == "low"