"""把中文自然语言需求解析成结构化的 `Demand`。

设计要点（design.md D6）
------------------------
- 规则版与 AI 版**共用同一个输出类型** `Demand`，上层完全不感知当前是哪种模式。
- 规则版**只负责高置信字段**：预算数字、商品类别、用途、核心需求。
  拿不准的一律留空，交给界面控件补齐——需求明确禁止「猜测填充」。
- 本模块**不发起任何网络请求**，无密钥环境下必须完整可用。

已知限制
--------
中文数字只支持「三千」「两千五百」「一万二」这类按位书写的形式；
口语省略式（如「两千五」表示 2500）无法识别，会退回「未识别到预算」，
由界面追问补齐，而不是猜一个数字。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src import config
from src.errors import EmptyDemand, InvalidBudget

#: 需求来源，用于界面上标注「这条需求是怎么来的」。
DemandSource = Literal["structured", "rule", "ai", "merged"]


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------


class Demand(BaseModel):
    """结构化的消费需求。

    所有字段都允许为空。**空值代表「用户没说」，不代表某个默认值**——
    需求明确要求缺信息时追问或走结构化控件，而不是替用户猜。
    """

    model_config = ConfigDict(extra="ignore")

    #: 用户原始输入，仅用于报告中的需求摘要展示。
    raw_text: str = ""

    #: 商品类别键（laptop / phone / headphone / keyboard），空串表示未指定。
    category: str = ""

    #: 总预算（元）。None 表示未指定。
    budget: float | None = None

    #: 使用场景，例如 编程、游戏、通勤、学习。
    use_cases: list[str] = Field(default_factory=list)

    #: 核心需求，例如 性能、续航、性价比、便携。
    core_needs: list[str] = Field(default_factory=list)

    #: 可接受的妥协项，例如 可以重一点、不介意没有降噪。
    compromises: list[str] = Field(default_factory=list)

    #: 品牌偏好。
    brand_preferences: list[str] = Field(default_factory=list)

    #: 其他硬性限制，例如 必须静音、必须有独立显卡。
    hard_constraints: list[str] = Field(default_factory=list)

    #: 该需求对象的来源。
    source: DemandSource = "structured"

    # --- 派生属性 ---------------------------------------------------------

    @property
    def category_label(self) -> str:
        """类别中文名，未指定时返回空串。"""
        return config.category_label(self.category) if self.category else ""

    @property
    def has_category(self) -> bool:
        return bool(self.category)

    @property
    def has_budget(self) -> bool:
        return self.budget is not None

    @property
    def budget_label(self) -> str:
        """预算的中文展示文本。"""
        return f"{self.budget:.0f} 元" if self.budget is not None else "未设定"

    def missing_key_fields(self) -> list[str]:
        """返回缺失的**关键**字段的中文名，供界面定向追问使用。

        只有类别与预算算关键字段：没有类别就无法确定候选范围，
        没有预算就无法判断匹配度。其余字段缺失只会让推荐变粗，
        不至于无法进行，因此不追问。
        """
        missing: list[str] = []
        if not self.has_category:
            missing.append("商品类别")
        if not self.has_budget:
            missing.append("预算")
        return missing

    def is_ready_for_analysis(self) -> bool:
        """是否具备进入筛选流程的最低信息。"""
        return not self.missing_key_fields()

    def summary_line(self) -> str:
        """一行式需求摘要，用于历史记录列表与报告开头。"""
        parts: list[str] = []
        if self.category_label:
            parts.append(self.category_label)
        if self.budget is not None:
            parts.append(f"预算 {self.budget:.0f} 元")
        if self.use_cases:
            parts.append("用途：" + "、".join(self.use_cases[:3]))
        if self.core_needs:
            parts.append("看重：" + "、".join(self.core_needs[:3]))
        return " · ".join(parts) if parts else "未提供具体需求"


# --------------------------------------------------------------------------
# 关键词表
# --------------------------------------------------------------------------

#: 类别关键词 → 类别键。命中多个时按此表顺序取第一个。
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "laptop": ("笔记本", "笔记本电脑", "电脑", "本子", "笔电", "laptop"),
    "phone": ("手机", "电话", "phone", "智能机"),
    "headphone": ("耳机", "耳麦", "降噪豆", "蓝牙耳机", "headphone"),
    "keyboard": ("键盘", "机械键盘", "薄膜键盘", "keyboard"),
}

#: 用户可能提到、但本项目商品数据暂不覆盖的类别。
#: 命中后由界面明确说「暂不支持」，而不是当作用户没提类别、跨类别乱推荐。
_UNSUPPORTED_CATEGORY_TERMS: tuple[str, ...] = (
    "平板", "ipad", "显示器", "相机", "单反", "微单",
    "手表", "手环", "鼠标", "台式", "一体机", "主机", "打印机", "路由器",
)

#: 关键词 → 归一后的使用场景（取值与商品数据中的 use_cases 对齐）。
_USE_CASE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "编程": ("编程", "写代码", "敲代码", "代码", "python", "java", "开发", "程序", "刷题", "ide"),
    "学习": ("学习", "上课", "网课", "作业", "自习", "考研", "看书", "备考"),
    "办公": ("办公", "文档", "ppt", "excel", "表格", "论文", "会议", "写材料"),
    "游戏": ("游戏", "打游戏", "玩游戏", "steam", "3a", "开黑"),
    "影音": ("影音", "看视频", "看电影", "追剧", "听歌", "音乐", "刷剧"),
    "通勤": ("通勤", "上下班", "上下学", "地铁", "公交", "路上"),
    "视频剪辑": ("剪辑", "剪视频", "视频编辑", "达芬奇"),
    "三维渲染": ("渲染", "建模", "3d", "blender"),
    "运动": ("运动", "跑步", "健身", "锻炼", "夜跑"),
    "拍照": ("拍照", "摄影", "拍照片", "出片"),
    "图书馆": ("图书馆", "自习室", "阅览室"),
    "长途": ("长途", "出差", "旅行", "飞机", "高铁"),
    "录音": ("录音", "编曲", "混音", "音乐制作"),
    "客制化": ("客制化", "换轴", "diy"),
    "上网": ("上网", "浏览网页", "查资料"),
}

#: 关键词 → 核心需求。用于 need_fit 维度。
_CORE_NEED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "性能": ("性能", "跑得快", "流畅", "不卡", "配置高", "算力", "性能好"),
    "性价比": ("性价比", "划算", "实惠", "值一点", "价格合适"),
    "续航": ("续航", "电量", "电池", "不用充电", "全天"),
    # 「太重」单列一条：用户常写「不希望电脑太重」，中间夹了商品名，
    # 只匹配整句「不希望太重」会漏掉。
    "便携": (
        "便携", "轻便", "轻一点", "轻巧", "带出去", "不重",
        "别太重", "不太重", "太重", "太重了", "重量",
    ),
    "音质": ("音质", "好听", "声音好"),
    "降噪": ("降噪", "隔音"),
    "拍照": ("拍照好", "相机好", "镜头好"),
    "静音": ("静音", "安静", "不吵", "别吵", "声音小"),
}

#: 出现这些词，说明用户明确表示某项可以让步。
_COMPROMISE_MARKERS: tuple[str, ...] = (
    "可以重", "重一点没关系", "重也没关系",
    "不介意", "无所谓", "可以接受", "能接受", "也可以", "还行",
)

#: 出现这些词，说明后面跟着的是硬性要求而不是偏好。
_REQUIREMENT_MARKERS: tuple[str, ...] = (
    "必须", "一定要", "务必要", "非得", "非得要", "不能没有", "需要有", "得有", "只能",
)

#: 需求里可以转化为硬性限制的具体条件 → 限制名（与 recommender 的表对齐）。
_CONSTRAINT_TERMS: tuple[str, ...] = (
    "静音", "独显", "独立显卡", "降噪", "无线", "热插拔",
)

#: 中文数字
_CN_DIGITS: dict[str, int] = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_CN_UNITS: dict[str, int] = {"十": 10, "百": 100, "千": 1000, "万": 10000}
_CN_CHARS = "".join(_CN_DIGITS) + "".join(_CN_UNITS)

#: 预算相关的上下文词。数字要挨着这些词才算预算，避免把「14 寸」当成预算。
_BUDGET_CONTEXT: tuple[str, ...] = (
    "预算", "价位", "最多", "不超过", "上限", "以内", "左右", "大概",
    "元", "块", "rmb", "人民币",
)

#: 供界面下拉/多选控件使用的候选值。控件选项与解析器识别的词保持一致，
#: 避免出现「控件里能选、但解析器不认识」的错位。
AVAILABLE_USE_CASES: tuple[str, ...] = tuple(_USE_CASE_KEYWORDS)
AVAILABLE_CORE_NEEDS: tuple[str, ...] = tuple(_CORE_NEED_KEYWORDS)


# --------------------------------------------------------------------------
# 数字解析
# --------------------------------------------------------------------------


def _chinese_to_number(text: str) -> float | None:
    """把「三千」「两千五百」「一万二」「十五」这类中文数字转成数值。

    只处理按位书写的规范形式。口语省略式（「两千五」＝2500）识别不了，
    返回 None 由调用方按「未识别」处理——猜错一个预算比不猜更糟。
    """
    if not text:
        return None
    total = 0.0
    section = 0.0
    number = 0.0
    for char in text:
        if char in _CN_DIGITS:
            number = _CN_DIGITS[char]
        elif char in _CN_UNITS:
            unit = _CN_UNITS[char]
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = 0.0
            else:
                section += (number or 1) * unit
            number = 0.0
        else:
            return None
    return total + section + number


def _parse_amount(token: str) -> float | None:
    """解析一个金额片段，支持阿拉伯数字与中文数字，可带「千 / 万」后缀。"""
    token = token.strip()
    if not token:
        return None

    # 阿拉伯数字，可带千 / 万后缀
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([千万])?", token)
    if match:
        value = float(match.group(1))
        suffix = match.group(2)
        if suffix == "千":
            value *= 1000
        elif suffix == "万":
            value *= 10000
        return value

    # 中文数字，可带单位
    match = re.fullmatch(rf"[{_CN_CHARS}]+", token)
    if match:
        return _chinese_to_number(token)

    return None


def _extract_budget(text: str) -> float | None:
    """从自然语言里找出预算数字。

    策略：先找「预算」「不超过」这类上下文词**附近**的数字；
    找不到上下文就退而取第一个看起来像价格的数字（≥100 且 ≤ 200000），
    避免把「14 寸」「5.3 蓝牙」这类参数当成预算。
    """
    lowered = text.lower()

    # 优先：区间写法「3000-4000」。用户写区间时预算是上限，取右边那个。
    # 必须排在上下文匹配之前，否则「预算 3000-4000」会先被「预算 3000」截走。
    range_match = re.search(r"(\d{3,6})\s*[-~到至]\s*(\d{3,6})", lowered)
    if range_match:
        return float(range_match.group(2))

    # 其次：上下文词附近紧邻的数字（「预算 3000」「不超过 5000」）。
    # 捕获组带可选负号——「预算 -100」必须被识别为负数并报错，
    # 而不是让正则把负号丢掉、当成正数 100。
    pattern = (
        rf"(?:{'|'.join(re.escape(w) for w in _BUDGET_CONTEXT)})"
        rf"\s*[约为是]?\s*"
        rf"(-?\s*负?\s*(?:\d+(?:\.\d+)?\s*[千万]?|[{_CN_CHARS}]+))"
    )
    for match in re.finditer(pattern, lowered):
        amount = _parse_signed_amount(match.group(1))
        if amount is None:
            continue
        if amount < 0:
            raise InvalidBudget(
                "预算不能为负数，请填写一个大于 0 的金额，例如 3000。"
            )
        if amount > 0:
            return amount

    # 最后：兜底取第一个像价格的数字
    for match in re.finditer(r"(-?\s*负?\s*\d{3,6})", lowered):
        amount = _parse_signed_amount(match.group(1))
        if amount is None:
            continue
        if amount < 0:
            raise InvalidBudget(
                "预算不能为负数，请填写一个大于 0 的金额，例如 3000。"
            )
        if 100 <= amount <= 200_000:
            return amount

    return None


def _parse_signed_amount(token: str) -> float | None:
    """解析可能带负号的金额片段，「负100」「-100」「100」都要能读。"""
    negative = token.lstrip().startswith("-") or "负" in token
    magnitude = _parse_amount(re.sub(r"^[\s\-负]+", "", token))
    if magnitude is None:
        return None
    return -magnitude if negative else magnitude


#: 结构化预算字段里允许出现的后缀（去掉后仍是纯数字）。
_BUDGET_SUFFIX = re.compile(r"\s*(元|块|rmb|人民币)\s*$", re.IGNORECASE)

#: 结构化预算字段的合法形式：阿拉伯数字，可带小数。
_BUDGET_PLAIN = re.compile(r"^\d+(?:\.\d+)?$")

#: 先于合法形式判断的负数形式，用于给出「不能为负」而不是「格式不对」。
_BUDGET_NEGATIVE = re.compile(r"^-\s*\d+(?:\.\d+)?$")


def parse_budget_value(raw: str | float | int | None) -> float | None:
    """解析**结构化控件**里的预算输入。

    这里刻意**只接受阿拉伯数字**，不接受「三千」这类中文数字——
    规格明确要求「用户在预算字段填写『三千块』」时提示格式错误。
    中文数字只在自由文本里认（「预算三千」是自然表达，见 `_extract_budget`）。

    与自由文本解析的另一个区别：格式不对必须报错，而不是静默当成没填。

    Raises:
        InvalidBudget: 填了内容但不是合法的正数金额。
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise InvalidBudget("预算必须填写为大于 0 的数字，例如 3000。")
    if isinstance(raw, (int, float)):
        if raw <= 0:
            raise InvalidBudget("预算必须大于 0，请填写一个正整数金额。")
        return float(raw)

    text = str(raw).strip()
    if not text:
        return None

    stripped = _BUDGET_SUFFIX.sub("", text).strip()
    if not _BUDGET_PLAIN.match(stripped):
        # 负数要单独说清楚：用户填的是一个合法数字，只是符号不对。
        # 一律回「格式不正确」会让人以为是自己写错了格式，反而更迷惑。
        if _BUDGET_NEGATIVE.match(stripped):
            raise InvalidBudget("预算不能为负数，请填写一个大于 0 的金额，例如 3000。")
        raise InvalidBudget(
            f"预算「{text}」格式不正确，请填写为数字，例如 3000 或 3000 元。"
        )

    amount = float(stripped)
    if amount <= 0:
        raise InvalidBudget("预算必须大于 0，请填写一个正整数金额。")
    return amount


# --------------------------------------------------------------------------
# 关键词提取
# --------------------------------------------------------------------------


def _match_keywords(text: str, table: dict[str, tuple[str, ...]]) -> list[str]:
    """返回命中的键，保持表定义顺序，去重。"""
    hits: list[str] = []
    for key, keywords in table.items():
        if any(keyword in text for keyword in keywords):
            hits.append(key)
    return hits


def _extract_category(text: str) -> str:
    """识别商品类别。命中多个时按表顺序取第一个（笔记本优先于「电脑」泛称）。"""
    for key, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return key
    return ""


def _extract_brands(text: str, known_brands: Iterable[str]) -> list[str]:
    """按数据集中已知的品牌名做匹配。不硬编码品牌清单。"""
    return [brand for brand in sorted(set(known_brands)) if brand and brand in text]


def _extract_hard_constraints(text: str) -> list[str]:
    """找出「必须 X」形式的硬性要求。

    只在明确的强制语气词后面才认，避免把「我不介意没有降噪」里的
    「降噪」误判成硬性要求。
    """
    found: list[str] = []
    for marker in _REQUIREMENT_MARKERS:
        start = 0
        while (index := text.find(marker, start)) != -1:
            tail = text[index + len(marker): index + len(marker) + 8]
            for term in _CONSTRAINT_TERMS:
                if term in tail and term not in found:
                    found.append(term)
            start = index + len(marker)
    return found


def _extract_compromises(text: str) -> list[str]:
    """找出用户主动表示可以让步的地方，取该短语所在的分句作为摘要。"""
    found: list[str] = []
    for marker in _COMPROMISE_MARKERS:
        if marker in text:
            index = text.find(marker)
            snippet = text[max(0, index - 6): index + len(marker) + 4].strip("，。、,;； ")
            if snippet and snippet not in found:
                found.append(snippet)
    return found


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------


def parse_demand(
    text: str,
    *,
    known_brands: Iterable[str] = (),
    source: DemandSource = "rule",
) -> Demand:
    """把一段中文需求描述解析成 `Demand`。

    解析不到的一律留空。**不会**为了「填满字段」而猜测任何值。

    Args:
        text: 用户输入的自然语言需求。
        known_brands: 已知品牌名集合，用于识别品牌偏好。通常传 `catalog.brands()`。
        source: 标记这条需求的来源。

    Raises:
        EmptyDemand: 输入为空或只有空白字符。
    """
    cleaned = text.strip()
    if not cleaned:
        raise EmptyDemand()

    lowered = cleaned.lower()

    return Demand(
        raw_text=cleaned,
        category=_extract_category(lowered),
        budget=_extract_budget(lowered),
        use_cases=_match_keywords(lowered, _USE_CASE_KEYWORDS),
        core_needs=_match_keywords(lowered, _CORE_NEED_KEYWORDS),
        compromises=_extract_compromises(cleaned),
        brand_preferences=_extract_brands(cleaned, known_brands),
        hard_constraints=_extract_hard_constraints(cleaned),
        source=source,
    )


def merge_demand(structured: Demand, parsed: Demand) -> Demand:
    """合并结构化控件与自然语言两条来源。

    规则（对应 spec `demand-parsing`）：
    - 结构化控件填了的字段**覆盖**自然语言解析结果
    - 控件没填的字段用自然语言的结果补上
    - 列表类字段取并集，因为用户可能控件选一个、文字里又提一个
    """
    def pick(structured_value, parsed_value):
        return structured_value if structured_value else parsed_value

    return Demand(
        raw_text=parsed.raw_text,
        category=pick(structured.category, parsed.category),
        budget=structured.budget if structured.budget is not None else parsed.budget,
        use_cases=list(dict.fromkeys([*structured.use_cases, *parsed.use_cases])),
        core_needs=list(dict.fromkeys([*structured.core_needs, *parsed.core_needs])),
        compromises=list(dict.fromkeys([*structured.compromises, *parsed.compromises])),
        brand_preferences=list(
            dict.fromkeys([*structured.brand_preferences, *parsed.brand_preferences])
        ),
        hard_constraints=list(
            dict.fromkeys([*structured.hard_constraints, *parsed.hard_constraints])
        ),
        source="merged",
    )


def detect_unsupported_category(text: str) -> str | None:
    """识别用户提到、但商品数据里没有的类别。

    为什么要单独做这件事：「想买个平板」如果不处理，会被当成「没提类别」，
    于是系统跨全部类别推荐一堆笔记本和手机——用户要的是平板，
    给他推荐不存在的东西属于误导。界面拿到结果后应直接说明暂不支持，
    而不是假装理解了需求。
    """
    lowered = text.lower()
    for term in _UNSUPPORTED_CATEGORY_TERMS:
        if term in lowered:
            return term
    return None


def unsupported_category_message(term: str) -> str:
    """把不支持的类别转成中文提示，并列出真正支持的类别。"""
    available = "、".join(config.CATEGORY_LABELS.values())
    return (
        f"目前还不支持「{term}」这一类商品，商品数据里只包含：{available}。"
        f"换个类别试试？"
    )


def follow_up_questions(demand: Demand) -> list[str]:
    """针对缺失的关键字段生成中文追问。

    只问缺的那几项——已经提供的信息不再重复询问。
    """
    questions: list[str] = []
    if not demand.has_category:
        available = "、".join(config.CATEGORY_LABELS.values())
        questions.append(f"你想买什么类别的商品？目前支持：{available}。")
    if not demand.has_budget:
        questions.append("你的预算是多少？填一个大概的数字即可，比如 3000 元。")
    return questions
