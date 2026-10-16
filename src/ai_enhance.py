"""AI 增强层：自然语言需求理解与推荐解读。

职责边界
--------
`ai_service` 管「怎么把请求发出去」，本模块管「提示词怎么写、
模型的回答怎么**安全地**变成结构化数据」。

三条硬规则
----------
1. **模型输出一律当不可信输入处理。** 类别必须落在我们的枚举里，
   列表字段必须落在既有词表里，预算必须是正数。不在范围内的丢掉，
   不硬塞——否则下游匹配会全军覆没，而且没有任何报错。
2. **不许编造事实。** 需求解析只从用户原文提取；推荐解读只依据传入的
   商品数据。解读里出现的价格必须能在传入数据里找到。
3. **失败就降级。** 任何一步出错都抛领域异常，由界面回退到本地规则模式，
   绝不返回半成品当成有效结果。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence

from src import config
from src.ai_service import AIService, redact
from src.data_loader import Product
from src.demand_parser import AVAILABLE_CORE_NEEDS, AVAILABLE_USE_CASES, Demand
from src.errors import UpstreamResponseError

logger = logging.getLogger("zhigou.ai")

#: 允许的类别键。模型返回其他值一律丢弃。
_ALLOWED_CATEGORIES = set(config.CATEGORY_LABELS)

#: 使用场景 / 核心需求的既有词表。模型说的词不在表里就不采纳——
#: 采纳了也匹配不上商品数据，只会让用户看到「命中 0/N」的假象。
_ALLOWED_USE_CASES = set(AVAILABLE_USE_CASES)
_ALLOWED_CORE_NEEDS = set(AVAILABLE_CORE_NEEDS)

#: 只认这些硬性限制（与 recommender 里的校验表一致）。
_ALLOWED_CONSTRAINTS = {"静音", "独显", "独立显卡", "降噪", "无线", "热插拔"}


# --------------------------------------------------------------------------
# 需求解析
# --------------------------------------------------------------------------

_PARSE_SYSTEM = """你是一个消费需求解析器。你的唯一任务是把用户的一段中文购物需求\
转成结构化 JSON。

严格遵守：
1. 只输出 JSON，不要任何解释文字，不要用 markdown 代码块。
2. 只提取用户**明确说过**的信息。没说的一律留空，绝对不要推断或填补。
3. 字段含义：
   - category: 商品类别，只能取这些键：%s，没提到就填 null
   - budget: 总预算，单位元，只填数字。没提到或不是数字就填 null，不要猜
   - use_cases: 使用场景数组，只能从这些词里选：%s
   - core_needs: 用户看重的点，只能从这些词里选：%s
   - compromises: 用户明确表示可以让步的地方，用简短中文短语描述
   - brand_preferences: 用户提到的品牌名数组，没提到就空数组
   - hard_constraints: 用户用「必须」「一定要」这类强制语气提的条件，\
只能从这些词里选：%s
4. 用户说「不希望太重」「别太重」属于 core_needs 里的「便携」，不是硬性限制。
5. 用户说「我不介意没有降噪」是让步，不要放进 hard_constraints。

输出格式示例：
{"category": "laptop", "budget": 3000, "use_cases": ["编程", "学习"], \
"core_needs": ["性能", "性价比"], "compromises": [], "brand_preferences": [], \
"hard_constraints": []}""" % (
    "、".join(f'"{key}"' for key in sorted(_ALLOWED_CATEGORIES)),
    "、".join(sorted(_ALLOWED_USE_CASES)),
    "、".join(sorted(_ALLOWED_CORE_NEEDS)),
    "、".join(sorted(_ALLOWED_CONSTRAINTS)),
)


def _clean_vocab(values: object, allowed: set[str]) -> list[str]:
    """只保留词表内的项，去重保序。非列表输入返回空。"""
    if not isinstance(values, (list, tuple)):
        return []
    result: list[str] = []
    for item in values:
        text = str(item).strip()
        if text in allowed and text not in result:
            result.append(text)
    return result


def _clean_texts(values: object, *, limit: int = 6) -> list[str]:
    """自由文本列表：去空白、去重、限量。"""
    if not isinstance(values, (list, tuple)):
        return []
    result: list[str] = []
    for item in values:
        text = str(item).strip()
        if text and text not in result:
            result.append(text[:60])
        if len(result) >= limit:
            break
    return result


def _clean_budget(value: object) -> float | None:
    """预算必须是正数。字符串数字也接受，其余一律丢弃。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def demand_from_payload(payload: dict, raw_text: str) -> Demand:
    """把模型返回的 JSON 洗成 `Demand`。

    这个函数是**唯一**的入口，也是防线的位置：模型可以返回任何东西，
    它只把合法且在白名单内的部分采纳进来，其余静默丢弃。
    """
    category = str(payload.get("category") or "").strip()
    if category not in _ALLOWED_CATEGORIES:
        category = ""

    brands = _clean_texts(payload.get("brand_preferences"))
    constraints = [
        item for item in _clean_texts(payload.get("hard_constraints"))
        if item in _ALLOWED_CONSTRAINTS
    ]

    return Demand(
        raw_text=raw_text,
        category=category,
        budget=_clean_budget(payload.get("budget")),
        use_cases=_clean_vocab(payload.get("use_cases"), _ALLOWED_USE_CASES),
        core_needs=_clean_vocab(payload.get("core_needs"), _ALLOWED_CORE_NEEDS),
        compromises=_clean_texts(payload.get("compromises")),
        brand_preferences=brands,
        hard_constraints=constraints,
        source="ai",
    )


def parse_demand_with_ai(
    text: str, *, service: AIService, known_brands: Iterable[str] = ()
) -> Demand:
    """用大模型解析需求。

    Raises:
        领域异常。调用方应回退到 `demand_parser.parse_demand`。
    """
    known = {b for b in known_brands if b}
    brands_hint = (
        f"\n\n本次可选品牌只有：{'、'.join(sorted(known))}。"
        f"用户提到的品牌若不在其中，仍然如实填进 brand_preferences。"
        if known
        else ""
    )

    payload = service.complete_json(_PARSE_SYSTEM, f"用户需求：{text}{brands_hint}")
    demand = demand_from_payload(payload, text)

    logger.info(
        "AI 解析完成：category=%s budget=%s use_cases=%d core_needs=%d",
        demand.category or "(空)", demand.budget, len(demand.use_cases), len(demand.core_needs),
    )
    return demand


# --------------------------------------------------------------------------
# 推荐解读
# --------------------------------------------------------------------------

_EXPLAIN_SYSTEM = """你是一个消费决策助手。用户提出购买需求，系统已经用规则算出\
了候选商品的匹配评分。你的任务是**解释**这些结果，而不是重新排序或推荐新商品。

严格遵守：
1. 只输出 JSON，不要任何解释文字，不要用 markdown 代码块。
2. **只能使用下面提供的数据。** 不要补充任何未提供的信息——不要提销量、\
用户评价、保修、口碑、品牌历史、市场行情。这些数据里没有。
3. 不要编造价格。提到价格时必须与提供的数据完全一致。
4. 如果某个判断缺少数据支撑，就不要做这个判断。
5. 每条解读控制在 60 字以内，中文，具体、不空泛。避免「性价比高」「值得购买」\
这类没有信息量的套话。
6. 解读要指出这件商品**为什么**匹配或不匹配用户的具体需求，扣住评分维度说。
7. 提到商品时用**商品名称**，不要用商品 ID（不要出现 LP001 这种编号）。
8. 不要给商品下「销量第一」「口碑最好」「全网最低」「遥遥领先」这类结论——\
提供的数据里没有销量、用户评价、市场行情或行业排名，这些说法无据可依。
9. 某件商品的 `data_issues` 非空时，说明该商品这几处记录内部互相矛盾。\
**不要就这些方面下结论**，也不要把矛盾的属性当作事实复述；可以提醒用户\
这几处需要核实。其他没被标记的方面照常解读。

输出格式：
{"overview": "一到两句总结", \
"per_product": [{"product_id": "LP001", "why": "……"}]}"""


def _product_brief(product: Product, *, rank: int, score_total: float,
                   match_level: str, dimensions: list[tuple[str, float, str]],
                   budget_label: str) -> dict:
    """给模型看的商品摘要。只放数据里真有的字段。"""
    return {
        "product_id": product.id,
        "name": product.name,
        "brand": product.brand,
        "category": product.category_label,
        "price": product.price,
        "specs": product.specs,
        "use_cases": product.use_cases,
        "pros": product.pros,
        "cons": product.cons,
        # 记录内部有矛盾的地方。模型据此避开这些属性，输出侧还有程序化拦截兜底。
        "data_issues": [issue.reason for issue in product.data_issues],
        "rank": rank,
        "score": round(score_total, 1),
        "match_level": match_level,
        "budget_status": budget_label,
        "dimensions": [
            {"name": name, "score": round(value, 1), "reason": reason}
            for name, value, reason in dimensions
        ],
    }


def _demand_brief(demand: Demand) -> dict:
    return {
        "category": demand.category_label or None,
        "budget": demand.budget,
        "use_cases": demand.use_cases,
        "core_needs": demand.core_needs,
        "compromises": demand.compromises,
        "brand_preferences": demand.brand_preferences,
        "hard_constraints": demand.hard_constraints,
    }


#: 从文本里抓出形如「3299 元」「¥3,299」的价格。
#: 必须用「前面不是一个数字或逗号」做边界，否则「3,299 元」会被从逗号后切断、
#: 只抓到 299，反过来把真实价格误判成编造。
_PRICE_PATTERN = re.compile(r"(?<![\d,])(?:¥|￥)?\s*(\d{1,3}(?:,\d{3})+|\d{3,6})\s*元")


def find_invented_prices(text: str, allowed_prices: set[float]) -> list[float]:
    """找出解读里出现、但传入数据中不存在的价格。

    这是针对「编造事实」最具体、也最容易发生的一种：模型顺口说一个价格。
    数字对不上就说明它在编，对应的解读要被丢掉。
    """
    invented: list[float] = []
    for match in _PRICE_PATTERN.finditer(text):
        value = float(match.group(1).replace(",", ""))
        if not any(abs(value - allowed) < 0.5 for allowed in allowed_prices):
            invented.append(value)
    return invented


# --------------------------------------------------------------------------
# 参数数值断言校验
# --------------------------------------------------------------------------

#: 识别得出的单位 → (单位族, 换算成该族规范单位的倍数)。
#: 同族的数值先换算到统一单位再比较，`1.28 千克` 与 `1280 克` 才能对上。
#: 按字符串长度倒序参与正则，保证「千克」先于「克」、「小时」先于「时」命中。
_UNIT_FACTORS: dict[str, tuple[str, float]] = {
    "克": ("mass", 1.0),
    "g": ("mass", 1.0),
    "千克": ("mass", 1000.0),
    "公斤": ("mass", 1000.0),
    "kg": ("mass", 1000.0),
    "小时": ("time", 1.0),
    "时": ("time", 1.0),
    "h": ("time", 1.0),
    "gb": ("storage", 1.0),
    "tb": ("storage", 1024.0),
    "mah": ("battery", 1.0),
    "英寸": ("length", 1.0),
    "吋": ("length", 1.0),
    "寸": ("length", 1.0),
    "毫米": ("small_length", 1.0),
    "mm": ("small_length", 1.0),
}

#: 商品参数键 → (单位族, 换算倍数)。只有列在这里的字段参与数值校验。
_SPEC_UNIT_KEYS: dict[str, tuple[str, float]] = {
    "weight_g": ("mass", 1.0),
    "weight_kg": ("mass", 1000.0),
    "battery_h": ("time", 1.0),
    "ram_gb": ("storage", 1.0),
    "storage_gb": ("storage", 1.0),
    "battery_mah": ("battery", 1.0),
    "screen_size": ("length", 1.0),
}

_UNIT_ALTERNATION = "|".join(
    re.escape(u) for u in sorted(_UNIT_FACTORS, key=len, reverse=True)
)

#: 「数字 + 明确单位」。**裸数字不匹配**——序号、评分、年份混在里面，
#: 纳入校验会大量误杀。
_SPEC_CLAIM_PATTERN = re.compile(
    rf"(?<![\d.])(\d+(?:\.\d+)?)\s*({_UNIT_ALTERNATION})",
    re.IGNORECASE,
)


#: 数值比较的**相对**容差，用于吸收四舍五入：1.28 千克写成 1.3 千克算对得上。
#:
#: 刻意不用「按写法精度取半径」——那个方案会把 `1TB` 视作区间 [0.5, 1.5] TB，
#: 于是把数据里的 512GB 也包进去，等于放过了「1TB」这种量级级的高报。
#: 相对容差只容忍 2% 以内的出入，四舍五入过得去，量级差异过不去。
_SPEC_TOLERANCE_RATIO = 0.02

#: 相对容差的绝对下限，避免极小的数值因比例容差过窄而误杀。
_SPEC_TOLERANCE_FLOOR = 0.05

#: **小数**断言额外允许的取整半径：写到几位小数，就是精确到那一位的一半。
#:
#: 只对带小数点的断言生效，整数断言**不适用**——这正是上面那条注释担心的情况：
#: 若把 `1TB` 也按写法精度取半径，它就变成区间 [0.5, 1.5] TB，足以吞掉数据里的
#: 512GB。而 `1.4 千克` 的半径只有 0.05 千克，吞不掉任何东西。
#:
#: 真实参数的位数是杂的（1.36 千克、6.7 英寸、1.39 千克），模型顺手取整是
#: 正常表达，按 2% 相对容差卡会把「1.36 → 1.4」这类正常取整判成编造，
#: 进而丢掉整条解读——「校验过严」是这个模块踩过的坑，别再踩一次。
def _rounding_allowance(raw_number: str, factor: float) -> float:
    if "." not in raw_number:
        return 0.0
    decimals = len(raw_number.partition(".")[2])
    return 0.5 * (10.0**-decimals) * factor


def _matches_any_known(
    value: float, candidates: Sequence[float], *, rounding: float = 0.0
) -> bool:
    """该数值是否落在任一已知取值的容差范围内。"""
    for known in candidates:
        tolerance = max(
            _SPEC_TOLERANCE_FLOOR, abs(known) * _SPEC_TOLERANCE_RATIO, rounding
        )
        if abs(value - known) <= tolerance:
            return True
    return False


def spec_claim_values(products: Iterable[Product]) -> dict[str, list[float]]:
    """从商品记录里收集「单位族 → 允许取值」，作为断言校验的依据集。"""
    allowed: dict[str, list[float]] = {}
    for product in products:
        for key, (family, factor) in _SPEC_UNIT_KEYS.items():
            raw = product.specs.get(key)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                continue
            allowed.setdefault(family, []).append(float(raw) * factor)
    return allowed


# --------------------------------------------------------------------------
# 排他性结论校验
# --------------------------------------------------------------------------

#: 无数据支撑的排他性、绝对化表述。
#:
#: 共同特征：它们断言的**比较维度在数据集里根本不存在**——没有销量、
#: 没有用户评价、没有市场行情、没有行业排名。这些说法不可能从传入数据推出。
#:
#: 刻意不收「排名第一」「同类第一」这类含糊说法：系统**确实**会排序，
#: 「在本次推荐里排第一」是**真的**，收进来会误杀正确的解读。
#: 宁可漏放，不可误杀。
_ABSOLUTE_CLAIM_PATTERNS: tuple[str, ...] = (
    # 销量——数据集不含销量字段
    "销量第一",
    "销量最高",
    "销量冠军",
    "销量领先",
    "最畅销",
    # 口碑与用户评价——数据集明确不含
    "口碑最好",
    "口碑最佳",
    "口碑第一",
    "评价最高",
    "好评如潮",
    "好评率",
    "公认最好",
    # 全网与市场价——数据集里只有项目自造的参考价
    "全网最低",
    "全网最便宜",
    "历史最低价",
    "市场最低",
    # 行业地位
    "遥遥领先",
    "行业第一",
    "业内第一",
    "市场占有率",
)


def find_unsupported_claims(text: str) -> list[str]:
    """找出解读中无数据支撑的排他性、绝对化结论，返回命中的表述。"""
    if not text:
        return []
    return [pattern for pattern in _ABSOLUTE_CLAIM_PATTERNS if pattern in text]


# --------------------------------------------------------------------------
# 存疑属性校验
# --------------------------------------------------------------------------

#: 参数标签里的「程度词」后缀。剥掉之后才是模型真正会用的说法——
#: 它会说「处理器」，不会说「处理器档位」。
_LABEL_SUFFIXES = ("档位", "等级")

#: 没有 `config.SPEC_LABELS` 可用的属性，手工补关键词。
_ISSUE_FALLBACK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "price": ("价格", "售价", "价位"),
}


def _issue_keywords(field: str) -> tuple[str, ...]:
    """被标记存疑的属性 → 解读里出现即视为「在就它下结论」的关键词。

    取不到关键词的属性（例如 R3 标记的 `pros`——优缺点重复，没有可靠的
    文字特征）返回空元组，交由提示词约束，不做输出侧拦截。保守优先。
    """
    candidates: list[str] = []
    label = config.SPEC_LABELS.get(field)
    if label:
        candidates.append(label)
        for suffix in _LABEL_SUFFIXES:
            if label.endswith(suffix) and len(label) > len(suffix):
                candidates.append(label[: -len(suffix)])
    candidates.extend(_ISSUE_FALLBACK_KEYWORDS.get(field, ()))

    keywords: list[str] = []
    for word in candidates:
        # 单字关键词误杀风险太高，一律不要。
        if len(word) >= 2 and word not in keywords:
            keywords.append(word)
    return tuple(keywords)


def find_flagged_claims(text: str, product: Product) -> list[str]:
    """找出解读中**断言了该商品被标记存疑属性**的表述。

    只拦被标记的那几个属性，**不牵连**同一件商品的其他正常属性。
    """
    if not text:
        return []
    hits: list[str] = []
    for issue in product.data_issues:
        for keyword in _issue_keywords(issue.field):
            if keyword in text and keyword not in hits:
                hits.append(keyword)
    return hits


def find_unsupported_spec_claims(
    text: str, allowed: Mapping[str, Sequence[float]]
) -> list[str]:
    """找出解读中**没有数据依据**的带单位数值断言。

    Args:
        text: 模型生成的解读文本。
        allowed: 单位族 → 允许的规范化取值，由 `spec_claim_values()` 生成。

    返回无法对应的原始片段（如 `"20 小时"`），便于日志与测试断言。
    该族**完全没有数据**时不判定——缺数据不等于编造，宁可漏放。
    """
    unsupported: list[str] = []
    for match in _SPEC_CLAIM_PATTERN.finditer(text):
        raw_number, raw_unit = match.group(1), match.group(2)
        family, factor = _UNIT_FACTORS[raw_unit.lower()]
        candidates = allowed.get(family)
        if not candidates:
            continue  # 这一类数据压根没有，无从谈「与数据不符」
        scaled = float(raw_number) * factor
        rounding = _rounding_allowance(raw_number, factor)
        if _matches_any_known(scaled, candidates, rounding=rounding):
            continue
        unsupported.append(match.group(0).strip())
    return unsupported


def _sanitise_why(
    text: str,
    product: Product,
    allowed_prices: set[float],
    allowed_specs: Mapping[str, Sequence[float]],
) -> str | None:
    """清洗一条解读。不合法就返回 None，由调用方丢弃。

    检查链：**价格 → 参数数值 → 排他性结论**，任一环判定无依据即整条丢弃。
    沿用价格校验的既有策略——丢弃单条、保留规则结果，不整段失败。
    """
    cleaned = " ".join(str(text).split()).strip()
    if not cleaned:
        return None
    if len(cleaned) > 200:
        cleaned = cleaned[:200]

    invented = find_invented_prices(cleaned, allowed_prices)
    if invented:
        logger.warning(
            "AI 解读中出现数据里没有的价格 %s（商品 %s），已丢弃该条解读",
            invented,
            product.id,
        )
        return None

    unsupported = find_unsupported_spec_claims(cleaned, allowed_specs)
    if unsupported:
        logger.warning(
            "AI 解读中出现数据里没有的参数数值 %s（商品 %s），已丢弃该条解读",
            unsupported,
            product.id,
        )
        return None

    absolute = find_unsupported_claims(cleaned)
    if absolute:
        logger.warning(
            "AI 解读中出现无数据支撑的排他性结论 %s（商品 %s），已丢弃该条解读",
            absolute,
            product.id,
        )
        return None

    flagged = find_flagged_claims(cleaned, product)
    if flagged:
        logger.warning(
            "AI 解读就商品 %s 存疑的属性（%s）下了结论，已丢弃该条解读",
            product.id,
            "/".join(flagged),
        )
        return None
    return cleaned


def explain_recommendations(
    demand: Demand,
    items: Sequence,  # list[RecommendationItem]
    *,
    service: AIService,
) -> dict[str, object]:
    """让模型解读推荐结果。返回 {overview, per_product: {id: why}, dropped: [...]}。

    Raises:
        领域异常。调用方应保留规则结果，只丢掉解读。
    """
    if not items:
        raise UpstreamResponseError("没有可解读的候选商品。")

    briefs = []
    # 允许出现的价格 = 候选商品的参考价 ∪ 用户预算。
    # 少了预算这一项，模型说「这三件都在 4000 元预算内」会被误判成编造价格，
    # 把本来正确的总述丢掉——真实联调时踩到过。
    allowed_prices: set[float] = set()
    if demand.budget is not None:
        allowed_prices.add(float(demand.budget))
    for rank, item in enumerate(items, start=1):
        product = item.product
        if product.price is not None:
            allowed_prices.add(float(product.price))
        dimensions = [
            (d.label, d.score, d.reason)
            for d in sorted(item.score.dimensions, key=lambda d: (-d.score, d.key))[:3]
        ]
        briefs.append(
            _product_brief(
                product,
                rank=rank,
                score_total=item.score.total,
                match_level=item.score.match_level,
                dimensions=dimensions,
                budget_label=item.budget_label,
            )
        )

    user = (
        "用户需求：\n"
        + json.dumps(_demand_brief(demand), ensure_ascii=False)
        + "\n\n候选商品（已按系统匹配评分排序）：\n"
        + json.dumps(briefs, ensure_ascii=False, indent=1)
        + "\n\n请按要求输出 JSON。"
    )

    payload = service.complete_json(_EXPLAIN_SYSTEM, user)

    by_id = {item.product.id: item.product for item in items}

    # 参数数值的允许集同样取候选商品的并集——模型可能拿另一件商品做对比。
    allowed_specs = spec_claim_values(by_id.values())

    per_product: dict[str, str] = {}
    dropped: list[str] = []
    raw_items = payload.get("per_product")
    if isinstance(raw_items, list):
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            product_id = str(entry.get("product_id") or "").strip()
            product = by_id.get(product_id)
            if product is None:
                continue  # 模型编了一个不存在的商品 ID，丢掉
            cleaned = _sanitise_why(
                entry.get("why", ""), product, allowed_prices, allowed_specs
            )
            if cleaned is None:
                dropped.append(product_id)
            else:
                per_product[product_id] = cleaned

    overview = " ".join(str(payload.get("overview") or "").split())[:300]
    if overview and (
        find_invented_prices(overview, allowed_prices)
        or find_unsupported_spec_claims(overview, allowed_specs)
        or find_unsupported_claims(overview)
    ):
        logger.warning("AI 总述里出现无数据依据的内容，已丢弃总述")
        overview = ""

    logger.info(
        "AI 解读完成：%d 条采用，%d 条因无数据依据被丢弃",
        len(per_product),
        len(dropped),
    )
    return {"overview": overview, "per_product": per_product, "dropped": dropped}


# --------------------------------------------------------------------------
# 知识问答：基于检索片段组织回答
# --------------------------------------------------------------------------

_ANSWER_SYSTEM = """你是消费决策助手的问答助手。用户问了一个选购问题，系统已经从\
知识库里检索到若干资料片段。请**直接回答用户的问题**。

严格遵守：
1. 只输出 JSON，不要任何解释文字，不要用 markdown 代码块。
2. **回答只依据提供的片段。** 片段里没有的事实（参数、价格、评价）一律不说，\
即使你知道也不说。
3. **直接回答问题本身**：把片段里的信息综合成一段给用户看的建议。\
不要出现「资料」「片段」「知识库」「没有覆盖」这类词，不要复述任务。
4. 用户问得宽（只问品牌、只问品类）也没关系：把片段里该品牌或该品类的要点\
综合起来讲，最后给一句「怎么选」的建议。
5. 实在没有任何片段能回答时，才用一句话说明暂时答不了这个问题、缺什么信息。\
除此之外不要做任何免责声明或自我说明。
6. 不要给结论性排名或口碑判断——不要出现「销量第一」「口碑最好」「全网最低」\
这类说法。
7. 不要给出具体价格。片段里若出现参考价，那是记录值，不是实时价格，\
也不要据此比较贵贱。
8. 回答用中文，**控制在 200 字以内**，直接说要点，不要客套。

输出格式：
{"answer": "……", "used_fragment_indexes": [1, 2]}"""


def _prices_in(text: str) -> set[float]:
    """把一段文本里出现的价格抽出来，作为该校验的允许集。"""
    prices: set[float] = set()
    for match in _PRICE_PATTERN.finditer(text):
        prices.add(float(match.group(1).replace(",", "")))
    return prices


def answer_from_knowledge(
    query: str,
    passages: Sequence[Any],
    *,
    service: AIService,
) -> str:
    """基于检索到的片段组织一段回答。

    Raises:
        领域异常。调用方应说明失败并建议重试，**不展示任何未通过校验的半成品**。

    校验用的是 `harden-ai-enhancement` 落地的那条链：价格必须来自片段原文，
    排他性结论一律拒绝。片段不足时要求模型自己说明，而不是补全。
    """
    if not passages:
        raise UpstreamResponseError("没有可依据的资料片段。")

    fragments = [
        {
            "index": index,
            "title": passage.title,
            "type": passage.type_label,
            "content": passage.excerpt,
        }
        for index, passage in enumerate(passages, start=1)
    ]
    user = (
        f"用户的问题：{query}\n\n"
        f"检索到的资料片段：\n{json.dumps(fragments, ensure_ascii=False, indent=1)}\n\n"
        f"请按要求输出 JSON。"
    )

    payload = service.complete_json(_ANSWER_SYSTEM, user)
    answer = " ".join(str(payload.get("answer") or "").split()).strip()
    if not answer:
        raise UpstreamResponseError("模型没有给出回答内容。")

    # 校验一：回答里出现的价格必须在片段原文里出现过。
    # 允许集取全部片段的并集——模型可能引用任意一条。
    allowed_prices: set[float] = set()
    for passage in passages:
        allowed_prices |= _prices_in(passage.excerpt)

    invented = find_invented_prices(answer, allowed_prices)
    if invented:
        raise UpstreamResponseError(f"回答里出现了资料中没有的价格：{invented}")

    # 校验二：排他性结论——与解读走同一张模式表。
    absolute = find_unsupported_claims(answer)
    if absolute:
        raise UpstreamResponseError(f"回答里出现了无依据的排他性结论：{absolute}")

    logger.info("知识问答作答完成：%d 个片段，回答 %d 字", len(passages), len(answer))
    return answer


#: 给界面用的数据共享说明。调用外部服务前必须展示。
def data_sharing_notice(demand: Demand, item_count: int) -> str:
    """说明启用 AI 后会把哪些数据发出去。"""
    parts = ["启用 AI 增强后，以下内容会发送给你配置的模型服务："]
    # 无条件列出「需求原文」：填写之前就说明白要发什么，比等填了再说负责。
    parts.append("· 你在上方输入的需求原文（填了才会发）")
    if demand.core_needs or demand.budget or demand.category:
        parts.append(
            f"· 你的筛选条件（类别、预算、用途、核心需求等，共 "
            f"{len(demand.core_needs)} 项偏好）"
        )
    else:
        parts.append("· 你在结构化控件里填的筛选条件（填了才会发）")
    # 数量在分析之前还不知道，不写死数字——写「0 件」会让人以为出了错
    if item_count > 0:
        parts.append(f"· {item_count} 件候选商品的名称、价格、参数与优缺点")
    else:
        parts.append("· 筛选出的候选商品的名称、价格、参数与优缺点（数量取决于你的条件）")
    parts.append("")
    parts.append(
        "不会发送：你的收藏、历史记录、任何身份或设备信息。"
        "商品数据是本机数据库里那份公开资料整理的数据（品牌与型号真实、参数经简化、未核验）。"
        "如果不想发送，保持本地模式即可。"
    )
    return "\n".join(parts)
