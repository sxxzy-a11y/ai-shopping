"""商品的多维度需求适配评分。

设计要点
--------
1. **纯函数**：除了 config 里的权重表，不读全局状态、不做 I/O。
   这是整个应用最需要单元测试的部分。
2. **权重全部来自 config.SCORING_WEIGHTS**，本模块不含任何权重字面量。
3. **缺数据即排除该维度**，而不是补默认值。被排除的维度会连同原因
   一起返回，界面据此说明「这个分是怎么算出来的、哪些没算」。

维度定义见 config.DIMENSION_LABELS。每个维度的取值口径：

- `budget_fit`   参考价相对预算的匹配度
- `need_fit`     使用场景重合度 + 核心需求的可量化满足度
- `performance_fit` 该类别下与性能/功能相关的参数档位
- `value`        同类别内「性能排位」与「价格排位」之差
- `portability`  该类别下与便携相关的重量/体积指标
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from src import config
from src.data_loader import Product
from src.demand_parser import Demand

# --------------------------------------------------------------------------
# 归一化工具
# --------------------------------------------------------------------------

#: 类别 → 参数名 → (得 0 分时的取值, 得 100 分时的取值)。
#: 两个端点反着写即可表达「越小越好」（例如重量）。
_SPEC_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "laptop": {
        "cpu_tier": (1, 5),
        "ram_gb": (8, 32),
        "battery_h": (4, 12),
        "weight_kg": (2.5, 1.0),
    },
    "phone": {
        "chip_tier": (1, 5),
        "camera_tier": (1, 5),
        "battery_mah": (4000, 6000),
        "weight_g": (230, 160),
    },
    "headphone": {
        "audio_tier": (1, 5),
        "battery_h": (5, 50),
        "weight_g": (300, 4),
    },
    "keyboard": {
        "weight_g": (900, 500),
        "noise_level": (5, 1),  # 越安静分越高
    },
}

#: 该类别下「性能/功能」维度读取的参数（按重要性排序）。
_PERFORMANCE_SPECS: dict[str, tuple[str, ...]] = {
    "laptop": ("cpu_tier", "ram_gb"),
    "phone": ("chip_tier", "camera_tier"),
    "headphone": ("audio_tier",),
    "keyboard": (),  # 键盘没有性能档位，改用功能项合成，见 _keyboard_feature_score
}

#: 核心需求关键词 → 可量化的参数名。用于 need_fit 的可解释部分。
_NEED_SIGNALS: dict[str, tuple[str, ...]] = {
    "性能": ("cpu_tier", "chip_tier", "ram_gb"),
    "续航": ("battery_h", "battery_mah"),
    "便携": ("weight_kg", "weight_g"),
    "轻便": ("weight_kg", "weight_g"),
    "音质": ("audio_tier",),
    "拍照": ("camera_tier",),
    "降噪": ("noise_cancelling",),
    "静音": ("noise_level",),
}

#: 同义场景词归一。用户说「写代码」「敲代码」都应落到「编程」。
#: 需求侧与商品侧都会过这个表，所以「摄影」和「拍照」能被认成同一个场景。
_USE_CASE_ALIASES: dict[str, str] = {
    "写代码": "编程",
    "敲代码": "编程",
    "开发": "编程",
    "学习": "学习",
    "上课": "学习",
    "网课": "学习",
    "打游戏": "游戏",
    "看电影": "影音",
    "看视频": "影音",
    "听歌": "影音",
    "听音乐": "影音",
    "音乐": "影音",
    "摄影": "拍照",
    "拍照片": "拍照",
    "差旅": "长途",
    "出差": "长途",
    "跑步": "运动",
    "健身": "运动",
    "剪视频": "视频剪辑",
    "文档": "办公",
}


def _scale(value: float, at_zero: float, at_hundred: float) -> float:
    """把取值线性映射到 0–100，超出端点截断。"""
    if at_zero == at_hundred:
        return 50.0
    ratio = (value - at_zero) / (at_hundred - at_zero)
    return max(0.0, min(100.0, ratio * 100.0))


def _numeric(value: Any) -> float | None:
    """尽力转成数值，转不了返回 None（bool 不算数值）。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _normalize_spec(category: str, key: str, value: Any) -> float | None:
    """按类别的取值范围把一个参数归一化到 0–100。无法归一化返回 None。"""
    if isinstance(value, bool):
        return 100.0 if value else 30.0
    number = _numeric(value)
    if number is None:
        return None
    bounds = _SPEC_RANGES.get(category, {}).get(key)
    if bounds is None:
        return None
    return _scale(number, *bounds)


def normalize_use_case(text: str) -> str:
    """把场景词归一到统一写法。"""
    cleaned = text.strip()
    return _USE_CASE_ALIASES.get(cleaned, cleaned)


# --------------------------------------------------------------------------
# 结果类型
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionScore:
    """单个维度的得分及其解释。"""

    key: str
    score: float
    weight: float
    reason: str

    @property
    def label(self) -> str:
        return config.DIMENSION_LABELS.get(self.key, self.key)

    @property
    def contribution(self) -> float:
        """该维度对总分的加权贡献（未归一化前）。"""
        return self.score * self.weight


@dataclass(frozen=True)
class ScoreResult:
    """一件商品的完整评分结果。"""

    product_id: str
    total: float
    dimensions: list[DimensionScore] = field(default_factory=list)
    #: (维度中文名, 未参与计算的原因)
    excluded: list[tuple[str, str]] = field(default_factory=list)
    bonus: list[str] = field(default_factory=list)
    penalty: list[str] = field(default_factory=list)

    @property
    def match_level(self) -> str:
        """把总分翻成中文档位。措辞刻意避开「口碑」「好评」这类说法。"""
        if self.total >= 85:
            return "高度匹配"
        if self.total >= 70:
            return "较为匹配"
        if self.total >= 55:
            return "基本可用"
        return "匹配度较低"


# --------------------------------------------------------------------------
# 各维度计算
# --------------------------------------------------------------------------


def _score_budget_fit(product: Product, demand: Demand) -> tuple[float | None, str]:
    """预算匹配：刚好用满预算最优，超预算快速掉分。"""
    if demand.budget is None:
        return None, "未设定预算"
    if product.price is None:
        return None, "商品缺少参考价格"

    ratio = product.price / demand.budget
    if ratio <= 1.0:
        # 预算内：占用越充分说明选型越到位，70 分起步，用满预算满分。
        score = 70.0 + 30.0 * ratio
        reason = (
            f"参考价 {product.price:.0f} 元，占预算 {ratio * 100:.0f}%，在预算范围内"
        )
    else:
        # 超预算：每超 1% 扣 4 分，超 25% 归零。
        overage = ratio - 1.0
        score = max(0.0, 100.0 - 400.0 * overage)
        reason = (
            f"参考价 {product.price:.0f} 元，超出预算 "
            f"{product.price - demand.budget:.0f} 元（{overage * 100:.0f}%）"
        )
    return score, reason


def _score_need_fit(
    product: Product, demand: Demand
) -> tuple[float | None, str]:
    """需求匹配：使用场景重合度 + 核心需求的可量化满足度。"""
    parts: list[tuple[str, float]] = []

    # (a) 使用场景重合度
    wanted = {normalize_use_case(u) for u in demand.use_cases if u.strip()}
    if wanted:
        offered = {normalize_use_case(u) for u in product.use_cases if u.strip()}
        matched = wanted & offered
        parts.append(
            (
                f"用途命中 {len(matched)}/{len(wanted)}"
                f"（{'、'.join(sorted(matched)) or '无'}）",
                len(matched) / len(wanted) * 100.0,
            )
        )

    # (b) 核心需求里可量化的部分。
    #
    # 分母只算**能评估**的需求：像「性价比」这类由独立维度承担的项，
    # 如果也算进分母，界面上就会出现「命中 2/3」而实际只评估了 2 项，
    # 用户会误以为有一项评估过但没通过。所以拆成两条信息说清楚。
    need_scores: list[float] = []
    hit_needs: list[str] = []
    evaluable = 0
    handled_elsewhere: list[str] = []

    for need in demand.core_needs:
        label = need.strip()
        signals = _NEED_SIGNALS.get(label)
        if not signals:
            handled_elsewhere.append(label)
            continue

        evaluable += 1
        values = [
            normalized
            for key in signals
            if product.has_spec(key)
            and (normalized := _normalize_spec(product.category, key, product.spec(key)))
            is not None
        ]
        if values:
            need_scores.append(sum(values) / len(values))
            hit_needs.append(label)

    if evaluable:
        text = (
            f"核心需求命中 {len(hit_needs)}/{evaluable}"
            f"（{'、'.join(hit_needs) or '无'}）"
        )
        if handled_elsewhere:
            text += (
                f"；{'、'.join(handled_elsewhere)}"
                f"由对应维度单独衡量，未在此重复计分"
            )
        average = sum(need_scores) / len(need_scores) if need_scores else 0.0
        parts.append((text, average))

    if not parts:
        return None, "需求中没有可用于对比的场景或核心需求"

    total = sum(score for _, score in parts) / len(parts)
    reason = "；".join(text for text, _ in parts)
    return total, reason


def _keyboard_feature_score(product: Product) -> float | None:
    """键盘没有性能档位，用功能项合成一个「功能适配」分。"""
    specs = product.specs
    if not specs:
        return None
    score = 0.0
    if specs.get("hot_swappable"):
        score += 40.0  # 可换轴，手感可调
    if specs.get("wireless"):
        score += 30.0  # 无线，桌面更清爽
    switch_type = str(specs.get("switch_type", ""))
    if "机械" in switch_type or "轴" in switch_type:
        score += 30.0  # 机械结构，寿命与手感优于薄膜
    return max(0.0, min(100.0, score))


def _score_performance_fit(product: Product) -> tuple[float | None, str]:
    """性能/功能适配：读取该类别的性能参数并归一化。"""
    if product.category == "keyboard":
        score = _keyboard_feature_score(product)
        if score is None:
            return None, "缺少可评估的功能参数"
        features: list[str] = []
        if product.specs.get("hot_swappable"):
            features.append("热插拔")
        if product.specs.get("wireless"):
            features.append("无线")
        if "轴" in str(product.specs.get("switch_type", "")):
            features.append("机械轴")
        return score, "功能项：" + ("、".join(features) if features else "仅基础功能")

    keys = _PERFORMANCE_SPECS.get(product.category, ())
    if not keys:
        return None, "该类别没有定义性能评估参数"

    values: list[float] = []
    described: list[str] = []
    for key in keys:
        if not product.has_spec(key):
            continue
        normalized = _normalize_spec(product.category, key, product.spec(key))
        if normalized is None:
            continue
        values.append(normalized)
        described.append(f"{key}={product.spec(key)}")

    if not values:
        return None, "缺少可评估的性能参数"
    return sum(values) / len(values), "参数：" + "、".join(described)


def _score_value(
    product: Product, peers: Sequence[Product]
) -> tuple[float | None, str]:
    """性价比：同类别内「性能排位」与「价格排位」之差。

    排位都在 0–100 之间，排位越低代表越靠前（越便宜 / 性能越弱）。
    性能排位明显高于价格排位，即性能不错而价格不高，性价比就高。
    """
    priced = [p for p in peers if p.price is not None]
    if len(priced) < 2 or product.price is None:
        return None, "同类别商品不足 2 件，无法比较价格排位"

    capability = _score_performance_fit(product)[0]
    if capability is None:
        return None, "缺少性能参数，无法判断性价比"

    prices = sorted(p.price for p in priced if p.price is not None)
    cheaper_or_equal = sum(1 for value in prices if value <= product.price)
    price_rank = cheaper_or_equal / len(prices) * 100.0

    # 同类别内性能排位：算力高于本商品的占比
    peer_caps = [
        cap
        for peer in priced
        if (cap := _score_performance_fit(peer)[0]) is not None
    ]
    if len(peer_caps) < 2:
        return None, "同类别可比较性能的商品不足"
    weaker_or_equal = sum(1 for value in peer_caps if value <= capability)
    capability_rank = weaker_or_equal / len(peer_caps) * 100.0

    score = max(0.0, min(100.0, 50.0 + (capability_rank - price_rank) * 0.8))
    verdict = "偏高" if score >= 65 else ("中等" if score >= 45 else "偏低")
    reason = (
        f"同类别性能排位 {capability_rank:.0f}%、价格排位 {price_rank:.0f}%，"
        f"性价比{verdict}"
    )
    return score, reason


def _score_portability(product: Product) -> tuple[float | None, str]:
    """便携性：按类别的重量指标归一化。"""
    key = "weight_kg" if product.category == "laptop" else "weight_g"
    if not product.has_spec(key):
        return None, "缺少重量数据"
    normalized = _normalize_spec(product.category, key, product.spec(key))
    if normalized is None:
        return None, "重量数据无法解析"

    raw = product.spec(key)
    unit = "kg" if key == "weight_kg" else "g"
    return normalized, f"整机 {raw}{unit}"


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------


def score_product(
    product: Product, demand: Demand, peers: Sequence[Product] | None = None
) -> ScoreResult:
    """给一件商品打分。

    Args:
        product: 待评商品。
        demand: 用户需求。
        peers: 同类别商品集合，用于计算性价比排位。省略时只传自己，
               此时 `value` 维度会被排除。

    缺失的维度不会补默认分，而是记入 `excluded` 并从加权中剔除，
    最后按剩余维度的权重重新归一化。
    """
    peer_list = list(peers) if peers is not None else [product]
    weights = config.SCORING_WEIGHTS.get(product.category, {})

    computed: list[tuple[str, Callable[[], tuple[float | None, str]]]] = [
        ("budget_fit", lambda: _score_budget_fit(product, demand)),
        ("need_fit", lambda: _score_need_fit(product, demand)),
        ("performance_fit", lambda: _score_performance_fit(product)),
        ("value", lambda: _score_value(product, peer_list)),
        ("portability", lambda: _score_portability(product)),
    ]

    dimensions: list[DimensionScore] = []
    excluded: list[tuple[str, str]] = []
    weighted_sum = 0.0
    weight_total = 0.0

    for key, compute in computed:
        label = config.DIMENSION_LABELS.get(key, key)
        if key not in weights:
            excluded.append((label, f"{product.category_label}类别不设该维度"))
            continue
        score, reason = compute()
        if score is None:
            excluded.append((label, reason))
            continue
        weight = weights[key]
        dimensions.append(
            DimensionScore(key=key, score=score, weight=weight, reason=reason)
        )
        weighted_sum += score * weight
        weight_total += weight

    total = weighted_sum / weight_total if weight_total > 0 else 0.0

    # 加分项取分最高的两个维度，扣分项取最低的两个——与各维度实际得分直接对应，
    # 不是另写的通用文案。
    #
    # 排序用 (-score, key) 作为完整键而不是单看 score：否则并列时
    # sorted(reverse=True) 与 sorted() 给出的顺序相反，最高分维度可能
    # 落不到加分项里。这样 bonus[0] 恒为最高分维度、penalty[0] 恒为最低分维度。
    ranked = sorted(dimensions, key=lambda d: (-d.score, d.key))
    bonus = [f"{d.label} {d.score:.0f} 分：{d.reason}" for d in ranked[:2]]
    penalty = [f"{d.label} {d.score:.0f} 分：{d.reason}" for d in ranked[::-1][:2]]

    return ScoreResult(
        product_id=product.id,
        total=round(total, 1),
        dimensions=dimensions,
        excluded=excluded,
        bonus=bonus,
        penalty=penalty,
    )


def score_all(
    products: Iterable[Product], demand: Demand
) -> dict[str, ScoreResult]:
    """批量评分。自动按类别分组以正确计算性价比排位。"""
    by_category: dict[str, list[Product]] = {}
    for product in products:
        by_category.setdefault(product.category, []).append(product)

    return {
        product.id: score_product(product, demand, by_category.get(product.category, []))
        for product in products
    }
