"""自然语言记账解析器 —— 本地规则引擎,不依赖任何 AI API。

解析流程:
  1. 提取金额(最后一个数字)
  2. 判断收入/支出(关键词 + 默认)
  3. 匹配分类(关键词 → 分类名,可扩展)
  4. 提取日期关键词 → 具体日期
  5. 清理备注(去掉已被识别为金额/日期/分类的关键词)
  6. 计算置信度

设计原则:
  - 可独立测试,不依赖 UI
  - 关键词映射可扩展(通过 add_keyword_to_map)
  - 不崩溃,对任何输入都返回有效 ParseResult
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParseResult:
    """解析结果。amount 为 None 表示未识别到金额。"""
    amount: Optional[float]
    transaction_type: str           # 'income' / 'expense'
    category_name: str              # 分类名(字符串),UI 层通过 category_service 查找 id
    date: Optional[str]             # YYYY-MM-DD,None 表示日期不确定
    note: str
    confidence: str                 # 'high' / 'medium' / 'low'
    category_uncertain: bool = False  # 分类未明确(无关键词命中),需结合用户习惯推荐
    raw: str = ""                   # 原始输入(调试与展示)


# ---------------------------------------------------------------------------
# 关键词 → 分类名 映射(可扩展)
# 格式: (关键词, 分类名, 类型('income'/'expense'))
# 匹配时按关键词长度降序(长词优先,避免"吃"误匹配"吃饭")
# ---------------------------------------------------------------------------

_DEFAULT_KEYWORD_MAP: list[tuple[str, str, str]] = [
    # 支出 —— 餐饮
    ("早餐", "餐饮", "expense"),
    ("午饭", "餐饮", "expense"),
    ("晚餐", "餐饮", "expense"),
    ("晚饭", "餐饮", "expense"),
    ("夜宵", "餐饮", "expense"),
    ("吃饭", "餐饮", "expense"),
    ("外卖", "餐饮", "expense"),
    ("奶茶", "餐饮", "expense"),
    ("咖啡", "餐饮", "expense"),
    ("饮料", "餐饮", "expense"),
    ("水果", "餐饮", "expense"),
    ("零食", "餐饮", "expense"),
    ("面包", "餐饮", "expense"),
    ("蛋糕", "餐饮", "expense"),
    ("食堂", "餐饮", "expense"),
    ("吃", "餐饮", "expense"),
    ("喝", "餐饮", "expense"),
    # 支出 —— 交通
    ("地铁", "交通", "expense"),
    ("公交", "交通", "expense"),
    ("巴士", "交通", "expense"),
    ("打车", "交通", "expense"),
    ("出租车", "交通", "expense"),
    ("滴滴", "交通", "expense"),
    ("火车", "交通", "expense"),
    ("高铁", "交通", "expense"),
    ("飞机", "交通", "expense"),
    # 支出 —— 学习
    ("教材", "学习", "expense"),
    ("课程", "学习", "expense"),
    ("文具", "学习", "expense"),
    ("打印", "学习", "expense"),
    ("论文", "学习", "expense"),
    ("考试", "学习", "expense"),
    ("资料", "学习", "expense"),
    ("书", "学习", "expense"),
    ("学习", "学习", "expense"),
    # 支出 —— 购物
    ("衣服", "购物", "expense"),
    ("淘宝", "购物", "expense"),
    ("京东", "购物", "expense"),
    ("拼多多", "购物", "expense"),
    ("买东西", "购物", "expense"),
    ("购物", "购物", "expense"),
    ("买", "购物", "expense"),
    # 支出 —— 娱乐
    ("电影", "娱乐", "expense"),
    ("游戏", "娱乐", "expense"),
    ("KTV", "娱乐", "expense"),
    ("演出", "娱乐", "expense"),
    ("会员", "娱乐", "expense"),
    ("唱歌", "娱乐", "expense"),
    ("娱乐", "娱乐", "expense"),
    ("玩", "娱乐", "expense"),
    # 支出 —— 生活用品
    ("超市", "生活用品", "expense"),
    ("便利店", "生活用品", "expense"),
    ("日用", "生活用品", "expense"),
    # 支出 —— 医疗
    ("医院", "医疗", "expense"),
    ("看病", "医疗", "expense"),
    ("药", "医疗", "expense"),
    ("体检", "医疗", "expense"),
    # 支出 —— 礼物
    ("送", "礼物", "expense"),
    # 收入
    ("生活费", "生活费", "income"),
    ("到账", "生活费", "income"),
    ("兼职", "兼职", "income"),
    ("工资", "生活费", "income"),
    ("奖学金", "奖学金", "income"),
    ("红包", "红包", "income"),
    ("收到", "红包", "income"),
]

# 按关键词长度降序排序(长词优先匹配)
_KEYWORD_MAP: list[tuple[str, str, str]] = sorted(
    _DEFAULT_KEYWORD_MAP, key=lambda x: len(x[0]), reverse=True,
)


def add_keyword_to_map(keyword: str, category_name: str, type_: str) -> None:
    """扩展关键词映射(供管理界面调用,不破坏已有映射)。"""
    _KEYWORD_MAP.append((keyword, category_name, type_))
    _KEYWORD_MAP.sort(key=lambda x: len(x[0]), reverse=True)


# ---------------------------------------------------------------------------
# 金额提取
# ---------------------------------------------------------------------------

_AMOUNT_RE = re.compile(r"(-?\d+(?:\.\d+)?|\.\d+)")


def _extract_amount(text: str) -> tuple[Optional[float], str]:
    """提取金额,返回 (金额, 去掉金额后的文本)。

    - 支持普通整数/小数,以及 .16 / .5 这类无前导零小数 → 0.16 / 0.5
    - 取最后一个数字(最可能是金额)
    - 负数(-20)→ 返回 None(不可作为合法金额),由 service/确认框拦截
    """
    matches = list(_AMOUNT_RE.finditer(text))
    if not matches:
        return None, text
    m = matches[-1]                       # 取最后一个数字
    raw = m.group(0)
    if raw.startswith("."):               # .16 → 0.16
        raw = "0" + raw
    if raw.startswith("-."):              # -.5 → -0.5(仍会被判无效)
        raw = "-0" + raw[1:]
    try:
        amt = float(raw)
    except ValueError:
        return None, text
    if amt < 0:                           # 负金额无效
        return None, text
    cleaned = text[:m.start()] + text[m.end():]
    return amt, cleaned.strip()


# ---------------------------------------------------------------------------
# 日期提取
# ---------------------------------------------------------------------------

_DATE_KEYWORD_MAP = {
    "今天": 0,
    "今日": 0,
    "昨天": -1,
    "昨日": -1,
    "前天": -2,
    "前日": -2,
}

_YYYYMMDD_RE = re.compile(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})[日]?")
_MMDD_RE = re.compile(r"(\d{1,2})月(\d{1,2})日?")


def _extract_date(text: str, ref: Optional[datetime.date] = None) -> tuple[Optional[str], str, bool]:
    """提取日期,返回 (YYYY-MM-DD, 去掉日期文本后的文本, 是否确定)。

    确定:今天/昨天/前天/具体日期
    不确定:上周/模糊时间(返回 None)
    """
    ref = ref or datetime.date.today()
    cleaned = text

    # 1. 尝试具体日期格式 YYYY-MM-DD / YYYY年MM月DD日
    m = _YYYYMMDD_RE.search(cleaned)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = datetime.date(y, mo, d)
            cleaned = cleaned[:m.start()] + cleaned[m.end():]
            return dt.isoformat(), cleaned.strip(), True
        except ValueError:
            pass

    # 2. 尝试 MM月DD日(无年份,默认今年)
    m = _MMDD_RE.search(cleaned)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            dt = datetime.date(ref.year, mo, d)
            cleaned = cleaned[:m.start()] + cleaned[m.end():]
            return dt.isoformat(), cleaned.strip(), True
        except ValueError:
            pass

    # 2. 关键词:今天/昨天/前天
    for kw, offset in sorted(_DATE_KEYWORD_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if kw in cleaned:
            dt = ref + datetime.timedelta(days=offset)
            cleaned = cleaned.replace(kw, "", 1)
            return dt.isoformat(), cleaned.strip(), True

    # 3. "上周" / 模糊时间 → 不确定,返回 None
    if "上周" in cleaned or "上个月" in cleaned or "上星期" in cleaned:
        cleaned = cleaned.replace("上周", "").replace("上个月", "").replace("上星期", "")
        return None, cleaned.strip(), False

    return None, text, False


# ---------------------------------------------------------------------------
# 收入/支出判定
# ---------------------------------------------------------------------------

def _determine_type(text: str, matched_type: Optional[str]) -> str:
    """根据文本和关键词匹配结果判断类型。"""
    income_keywords = ["到账", "收入", "工资", "奖学金", "生活费"]
    for kw in income_keywords:
        if kw in text:
            return "income"
    return matched_type or "expense"


# ---------------------------------------------------------------------------
# 主解析函数
# ---------------------------------------------------------------------------

def parse(text: str, ref: Optional[datetime.date] = None) -> ParseResult:
    """解析自然语言输入,返回结构化结果。永不崩溃。"""
    raw = text.strip()
    if not raw:
        return ParseResult(
            amount=None, transaction_type="expense", category_name="其他",
            date=None, note="", confidence="low", category_uncertain=True, raw=raw,
        )

    ref = ref or datetime.date.today()

    # 1. 提取金额
    amount, remaining = _extract_amount(raw)

    # 2. 提取日期
    date, remaining, date_certain = _extract_date(remaining, ref)

    # 3. 关键词匹配分类
    matched_cat = None
    matched_type = None
    matched_keyword = ""
    for kw, cat_name, t in _KEYWORD_MAP:
        if kw in raw:  # 在原始文本中匹配(保留上下文)
            matched_cat = cat_name
            matched_type = t
            matched_keyword = kw
            break  # 长词优先,第一个匹配即最佳

    # 4. 确定类型
    transaction_type = _determine_type(raw, matched_type)

    # 5. 清理备注
    note = remaining
    if matched_keyword and matched_keyword in note:
        note = note.replace(matched_keyword, "", 1)
    note = note.strip()
    # 去掉残留的"花了""买了一个""买了""的""一个"等无意义词
    for junk in ("花了", "买了一个", "买了一本", "买了一", "买了", "买", "了", "的",
                 "一个", "一本", "刚刚", "今天", "昨天", "前天", "到账", "收到"):
        if note.startswith(junk):
            note = note[len(junk):].strip()
        if note.endswith(junk):
            note = note[:-len(junk)].strip()
    # 如果备注为空但原文本有意义,用分类名或关键词
    if not note and matched_keyword:
        # 去掉金额和日期后剩下的关键词
        for kw, _, _ in _KEYWORD_MAP:
            if kw in raw and kw not in (matched_keyword,):
                # 可能有其他关键词,但用匹配到的
                pass
        note = matched_keyword

    # 6. 分类名:收入匹配到收入分类,支出匹配到支出分类,交叉时修正
    if transaction_type == "income":
        if matched_cat and matched_type == "income":
            cat_name = matched_cat
        else:
            cat_name = "其他收入"
    else:
        if matched_cat and matched_type == "expense":
            cat_name = matched_cat
        else:
            cat_name = "其他"

    # 7. 日期默认:纯数字或未提及日期关键字时默认今天;提及"上周"等模糊词时留空让用户确认
    _AMBIGUOUS_DATE_WORDS = {"上周", "上个月", "上星期", "前几", "前几天"}
    if date is None:
        has_ambiguous = any(w in raw for w in _AMBIGUOUS_DATE_WORDS)
        if not has_ambiguous:
            date = ref.isoformat()
            date_certain = True

    # 8. 置信度
    if amount is None:
        confidence = "low"
    elif date is not None and date_certain:
        confidence = "high"
    else:
        confidence = "medium"
    # 分类不明确:置信度不高于 medium,提示用户确认(不擅自写入猜测分类)
    if matched_cat is None and confidence == "high":
        confidence = "medium"

    return ParseResult(
        amount=amount, transaction_type=transaction_type,
        category_name=cat_name, date=date, note=note,
        confidence=confidence, category_uncertain=(matched_cat is None),
        raw=raw,
    )