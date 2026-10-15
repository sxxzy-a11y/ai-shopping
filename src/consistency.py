"""商品记录的一致性检测。

职责边界：只回答「这条记录自己跟自己打不打得起来」。不碰加载、不碰评分、
不碰展示。纯函数，输入一条商品记录，输出它有哪些地方自相矛盾。

规则为什么这么少
----------------
一条不准的规则会把**正常商品**污名化成「资料存疑」——比不做更糟。所以这里
只保留经全量数据实测零误报的规则，且宁可漏放不可误杀。

规则为什么必须否定感知
----------------------
数据里真实存在「**无**独显」「**不可**折叠」这类句子。它们是**正确的否定陈述**，
朴素关键词匹配会把它们判成「说了独显但参数写着没有」，直接误报。
因此所有文本规则先判断关键词前面有没有否定词。

与 `Product.missing_fields` 的分工
---------------------------------
`missing_fields` 管「**字段缺失**」，本模块管「**字段矛盾**」。
二者是数据质量问题的两面，不重叠：缺 `pros` 由前者报告，
`pros` 说支持独显而参数写 false 由后者报告。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # 只为类型标注，避免与 data_loader 形成导入环
    from src.data_loader import Product

logger = logging.getLogger("zhigou.consistency")


# --------------------------------------------------------------------------
# 规则参数
# --------------------------------------------------------------------------

#: 档位类字段的取值范围（1 最低，5 最高）。取值说明见数据集的 `spec_tier_note`。
TIER_MIN = 1
TIER_MAX = 5

#: 以 `_tier` 结尾的字段一律按档位处理。这两个不带该后缀，单独列出。
TIER_EXTRA_KEYS: frozenset[str] = frozenset({"noise_level", "energy_grade"})

#: 否定词。关键词前 `NEGATION_WINDOW` 个字符内出现任一字符，即视为否定式。
#: 「没有」「不支持」「不含」都被其中的「没」「不」覆盖。
_NEGATIONS = "无不非没未缺乏缺少"

#: 否定判定窗口：往前看几个字符。
NEGATION_WINDOW = 3

#: 「参数说没有、文字却说有」的布尔字段。
#: 每项是 (字段名, 文本关键词, 展示名)。
_BOOLEAN_CLAIMS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("has_dedicated_gpu", ("独显", "独立显卡"), "独立显卡"),
    ("foldable", ("折叠",), "可折叠"),
)


@dataclass(frozen=True)
class Issue:
    """一处内部矛盾。

    Attributes:
        field: 被矛盾的属性键（参数名或字段名）。用于 AI 层按属性拦截解读。
        reason: 面向用户的中文说明，直接可展示。
    """

    field: str
    reason: str


# --------------------------------------------------------------------------
# 否定感知的文本匹配
# --------------------------------------------------------------------------


def mentions_positively(
    text: str,
    keywords: Iterable[str],
    *,
    window: int = NEGATION_WINDOW,
) -> bool:
    """文本里是否**肯定式**提到了任一关键词。

    关键词前 `window` 个字符内出现否定词时，该次出现不算数。
    这是「无独显」「不可折叠」不被误判为矛盾的原因。
    """
    if not text:
        return False
    for keyword in keywords:
        if not keyword:
            continue
        start = 0
        while True:
            index = text.find(keyword, start)
            if index == -1:
                break
            prefix = text[max(0, index - window) : index]
            if not any(char in _NEGATIONS for char in prefix):
                return True
            start = index + 1
    return False


def _claim_text(product: Product) -> str:
    """参与文本规则的文本：名称 + 优点 + 缺点。

    名称也纳入——名称写着「可折叠婴儿车」而 `foldable` 为 false，
    同样是自相矛盾。
    """
    parts = [product.name, *product.pros, *product.cons]
    return " ".join(part for part in parts if part)


# --------------------------------------------------------------------------
# 规则
# --------------------------------------------------------------------------
#
# 每条规则都是「输入 Product，输出 list[Issue]」的纯函数。
# 新增规则前先跑全量数据确认零误报，再补夹具测试。


def _is_tier_key(key: str) -> bool:
    return key.endswith("_tier") or key in TIER_EXTRA_KEYS


def _check_tier_range(product: Product) -> list[Issue]:
    """R1：档位类字段取值越界。

    档位是 1–5 的刻度（见数据集 `spec_tier_note`），越界说明数据写错了。
    布尔值不算数——`isinstance(True, int)` 为真，不排除会把 true 当成 1。
    """
    issues: list[Issue] = []
    for key, value in product.specs.items():
        if not _is_tier_key(key):
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not TIER_MIN <= value <= TIER_MAX:
            issues.append(
                Issue(
                    field=key,
                    reason=(
                        f"参数「{key}」的档位值是 {value}，"
                        f"超出 {TIER_MIN}–{TIER_MAX} 的取值范围"
                    ),
                )
            )
    return issues


def _check_price_positive(product: Product) -> list[Issue]:
    """R2：价格存在但不是正数。

    价格**缺失**由 `missing_fields` 负责，这里只管「写了但写错」——
    0 或负数会被预算筛选当成永远符合条件，属于会静默污染结果的一类。
    """
    if product.price is None:
        return []
    if product.price <= 0:
        return [
            Issue(
                field="price",
                reason=f"参考价是 {product.price:g}，不是正数，无法参与预算筛选",
            )
        ]
    return []


def _check_duplicate_pros_cons(product: Product) -> list[Issue]:
    """R3：优点与缺点出现完全相同的条目。

    同一条描述不能既是优点又是缺点——多半是先复制再改、漏改了其中一边。
    """
    duplicated = sorted(set(product.pros) & set(product.cons))
    if not duplicated:
        return []
    shown = "、".join(f"「{item}」" for item in duplicated[:3])
    return [
        Issue(
            field="pros",
            reason=f"同一条描述同时出现在优点与缺点里：{shown}",
        )
    ]


def _check_boolean_claims(product: Product) -> list[Issue]:
    """R5 / R6：参数写着不支持，文字却肯定地说支持。"""
    text = _claim_text(product)
    issues: list[Issue] = []
    for key, keywords, label in _BOOLEAN_CLAIMS:
        if product.specs.get(key) is not False:
            continue
        if mentions_positively(text, keywords):
            issues.append(
                Issue(
                    field=key,
                    reason=f"参数「{key}」标记为不支持{label}，但描述里提到支持{label}",
                )
            )
    return issues


_RULES: tuple[tuple[str, Any], ...] = (
    ("tier_range", _check_tier_range),
    ("price_positive", _check_price_positive),
    ("duplicate_pros_cons", _check_duplicate_pros_cons),
    ("boolean_claims", _check_boolean_claims),
)


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def check_product(product: Product) -> list[Issue]:
    """检测一条商品记录的内部矛盾。

    单条规则抛异常时只跳过该条规则并记日志，不让整次检测失败——
    调用方（`Product.data_issues`）在属性里被访问，抛异常会顺着界面炸开。
    """
    issues: list[Issue] = []
    for name, rule in _RULES:
        try:
            issues.extend(rule(product))
        except Exception:  # noqa: BLE001 —— 检测失败不应影响主流程
            logger.warning(
                "一致性规则 %s 在商品 %s 上执行失败，已跳过该规则",
                name,
                getattr(product, "id", "?"),
                exc_info=True,
            )
    return issues


def check_catalog(products: Sequence[Product]) -> dict[str, list[Issue]]:
    """批量检测，返回 {商品 ID: 问题列表}。只保留有问题的商品。

    `scripts/` 与测试用它做全量体检；界面走 `Product.data_issues` 单条读取。
    """
    found: dict[str, list[Issue]] = {}
    for product in products:
        issues = check_product(product)
        if issues:
            found[product.id] = issues
    return found
