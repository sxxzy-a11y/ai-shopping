"""候选商品的筛选、评分编排、排序与放宽建议。

设计要点
--------
- **预算不是硬过滤**：超预算商品不会被删掉，而是单独成列并逐条标注
  超出金额。需求明确要求「不要将其伪装成预算内商品」，也没要求隐藏它——
  用户需要看到「再加多少钱能买到什么」。
- **排序依据是需求适配评分，不是价格**。需求明确禁止按价格排序。
- 无匹配结果时必须给出**具体可执行**的放宽建议，不能只返回空列表。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src import config
from src.data_loader import Catalog, Product
from src.demand_parser import Demand
from src.scoring import ScoreResult, score_all

# --------------------------------------------------------------------------
# 硬性限制的识别
# --------------------------------------------------------------------------

#: 可识别的硬性限制关键词 → 判定函数。
#: 判定函数返回 True 表示该商品满足这条限制。
_HARD_CONSTRAINT_CHECKS: dict[str, tuple[str, ...]] = {
    "静音": ("noise_level",),
    "安静": ("noise_level",),
    "独立显卡": ("has_dedicated_gpu",),
    "独显": ("has_dedicated_gpu",),
    "降噪": ("noise_cancelling",),
    "无线": ("wireless",),
    "热插拔": ("hot_swappable",),
}


def _check_hard_constraint(product: Product, constraint: str) -> tuple[bool | None, str]:
    """判断商品是否满足一条硬性限制。

    返回 (是否满足, 说明)。`None` 表示这条限制无法识别、未参与筛选。

    两条判定原则：

    - **无法识别的限制**：不参与筛选，只记一条说明。不因为读不懂就把商品全筛掉。
    - **能识别但数据里没有对应参数**：判为**不满足**。用户说「必须静音」，
      而数据里查不到该商品的静音参数，就不能替它出具「满足」的结论——
      那正是需求禁止的「把没有依据的判断当成结论」。
    """
    text = constraint.strip()
    keys = _HARD_CONSTRAINT_CHECKS.get(text)
    if keys is None:
        return None, f"无法识别的限制条件「{text}」，未参与筛选"

    key = keys[0]
    if not product.has_spec(key):
        return False, f"数据中没有「{key}」参数，无法确认是否满足限制「{text}」"

    value = product.spec(key)
    if key == "noise_level":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value <= 2
    else:
        ok = bool(value)
    return ok, f"限制「{text}」{'满足' if ok else '不满足'}"


# --------------------------------------------------------------------------
# 结果类型
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RecommendationItem:
    """一条推荐结果：商品 + 评分 + 预算匹配情况。"""

    product: Product
    score: ScoreResult
    within_budget: bool
    overage: float = 0.0
    #: 用户是否设定了预算。为 False 时不得把商品表述为「预算内」。
    budget_known: bool = True

    @property
    def budget_label(self) -> str:
        """预算匹配状态的中文描述。

        未设定预算时明确说「未设定预算」——把这种情况显示成「预算内」
        等于凭空给了一个用户没做过的判断。
        """
        if not self.budget_known:
            return "未设定预算"
        if self.within_budget:
            return "预算内"
        return f"超出预算 {self.overage:.0f} 元"


@dataclass
class RecommendationResult:
    """一次分析的完整结果。"""

    demand: Demand
    within_budget: list[RecommendationItem] = field(default_factory=list)
    over_budget: list[RecommendationItem] = field(default_factory=list)
    #: 无结果时给出的具体放宽建议。
    relaxations: list[str] = field(default_factory=list)
    #: 过程说明：被忽略的限制、信息不完整的商品、数据集提示等。
    notes: list[str] = field(default_factory=list)
    #: 通过类别与硬性限制筛选后的候选总数（未做预算切分前）。
    candidate_count: int = 0
    #: 超出预算的商品**真实条数**（截断展示之前）。
    #: 界面与导出展示条数时一律用它，不用 `len(over_budget)`——
    #: 截断之后列表长度就不再等于总数了。
    over_budget_total: int = 0

    @property
    def over_budget_hidden(self) -> int:
        """被截断掉、没有展示出来的超预算商品条数。"""
        return max(0, self.over_budget_total - len(self.over_budget))

    @property
    def has_results(self) -> bool:
        return bool(self.within_budget) or bool(self.over_budget)

    @property
    def has_within_budget(self) -> bool:
        return bool(self.within_budget)

    @property
    def best(self) -> RecommendationItem | None:
        """首选推荐。预算内优先，没有预算内才退回超预算中的最优。"""
        if self.within_budget:
            return self.within_budget[0]
        if self.over_budget:
            return self.over_budget[0]
        return None

    def all_items(self) -> list[RecommendationItem]:
        """预算内 + 超预算的合并列表，保持各自排序。"""
        return [*self.within_budget, *self.over_budget]


# --------------------------------------------------------------------------
# 筛选
# --------------------------------------------------------------------------


def _filter_candidates(
    catalog: Catalog, demand: Demand
) -> tuple[list[Product], list[str]]:
    """按类别与硬性限制筛出候选商品，返回 (候选, 说明)。"""
    notes: list[str] = []

    if demand.has_category:
        candidates = catalog.by_category(demand.category)
        if not candidates:
            notes.append(
                f"商品数据中没有「{demand.category_label}」类别的商品"
            )
            return [], notes
    else:
        candidates = list(catalog.products)
        notes.append("未指定商品类别，已在全部类别中检索")

    # 品牌偏好：按硬性条件处理。
    # 不命中时**不能**悄悄退回全部商品——那等于替用户撤销了他自己提的条件。
    # 正确做法是筛空，再由 _build_relaxations 给出「放宽品牌偏好」的具体建议。
    if demand.brand_preferences:
        wanted = {b.strip() for b in demand.brand_preferences if b.strip()}
        matched = [p for p in candidates if p.brand in wanted]
        if matched:
            notes.append(
                f"已按品牌偏好筛选：{'、'.join(sorted(wanted))}（{len(matched)} 件）"
            )
        else:
            notes.append(f"候选中没有品牌为 {'、'.join(sorted(wanted))} 的商品")
        candidates = matched

    # 硬性限制
    if demand.hard_constraints:
        # 无法识别的限制只在提示里说一次，不按商品重复
        for constraint in demand.hard_constraints:
            if constraint.strip() not in _HARD_CONSTRAINT_CHECKS:
                notes.append(
                    f"无法识别的限制条件「{constraint.strip()}」，未参与筛选"
                )

        kept: list[Product] = []
        unverifiable: set[str] = set()
        for product in candidates:
            satisfied = True
            for constraint in demand.hard_constraints:
                ok, explanation = _check_hard_constraint(product, constraint)
                if ok is None:
                    continue  # 无法识别的限制，上面已提示，不参与筛选
                if not ok:
                    satisfied = False
                    if "无法确认" in explanation:
                        unverifiable.add(constraint.strip())
            if satisfied:
                kept.append(product)

        if unverifiable:
            notes.append(
                f"「{'、'.join(sorted(unverifiable))}」在商品数据中缺少可校验的参数，"
                f"已按无法确认处理，对应商品未计入匹配结果"
            )
        if len(kept) != len(candidates):
            notes.append(
                f"已按硬性限制筛除 {len(candidates) - len(kept)} 件商品"
                f"（{'、'.join(demand.hard_constraints)}）"
            )
        candidates = kept

    # 去重说明，避免同一句提示刷屏
    notes = list(dict.fromkeys(notes))
    return candidates, notes


def _build_relaxations(
    catalog: Catalog, demand: Demand, candidates: list[Product]
) -> list[str]:
    """无匹配结果时，给出具体可执行的放宽建议。"""
    suggestions: list[str] = []

    # 建议一：预算不够时给出该类别的实际价格下限
    pool = candidates or (
        catalog.by_category(demand.category) if demand.has_category else catalog.products
    )
    priced = [p for p in pool if p.price is not None]
    if priced and demand.budget is not None:
        cheapest = min(priced, key=lambda p: p.price)
        if cheapest.price > demand.budget:
            suggestions.append(
                f"当前类别的最低参考价为 {cheapest.price:.0f} 元"
                f"（{cheapest.name}）。把预算提高到 {cheapest.price:.0f} 元以上"
                f"就能进入候选范围。"
            )
    elif not priced:
        suggestions.append("候选商品都缺少参考价格，建议先补全商品数据再分析。")

    # 建议二：品牌偏好把结果筛没了
    if demand.brand_preferences and not candidates:
        brands = "、".join(demand.brand_preferences)
        available = sorted({p.brand for p in catalog.by_category(demand.category)})
        suggestions.append(
            f"品牌偏好「{brands}」没有命中任何商品。"
            + (f"该类别可选品牌有：{'、'.join(available)}。" if available else "")
            + "试着放宽品牌偏好后重试。"
        )

    # 建议三：硬性限制过严
    if demand.hard_constraints and not candidates:
        suggestions.append(
            f"硬性限制「{'、'.join(demand.hard_constraints)}」组合后没有商品满足，"
            f"建议逐条去掉后看哪一条导致无结果。"
        )

    # 建议四：类别里根本没有商品
    if demand.has_category and not catalog.by_category(demand.category):
        suggestions.append(
            f"商品数据中暂不包含「{demand.category_label}」，"
            f"可改用以下类别之一："
            + "、".join(
                config.category_label(c) for c in catalog.present_categories()
            )
            + "。"
        )

    if not suggestions:
        suggestions.append(
            "当前条件下没有匹配商品。建议提高预算、放宽限制条件或更换商品类别后重试。"
        )
    return suggestions


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------


def recommend(
    catalog: Catalog,
    demand: Demand,
    limit: int = config.DEFAULT_RECOMMEND_LIMIT,
) -> RecommendationResult:
    """按需求筛选、评分并排序，产出推荐结果。

    Args:
        catalog: 已加载的商品数据集。
        demand: 用户需求。类别与预算缺失时仍会执行，但结果会更宽泛。
        limit: 预算内推荐条数上限。
    """
    candidates, notes = _filter_candidates(catalog, demand)

    # 数据质量提示：信息不完整的商品仍然参与，但要让用户知道
    incomplete = [p for p in candidates if not p.is_complete]
    if incomplete:
        names = "、".join(f"{p.name}（缺 {'、'.join(p.missing_fields)}）" for p in incomplete[:3])
        more = f" 等 {len(incomplete)} 件" if len(incomplete) > 3 else ""
        notes.append(f"以下商品信息不完整，相关维度未参与评分：{names}{more}")

    if not candidates:
        return RecommendationResult(
            demand=demand,
            relaxations=_build_relaxations(catalog, demand, candidates),
            notes=notes,
            candidate_count=0,
        )

    scores = score_all(candidates, demand)

    budget_known = demand.budget is not None

    within: list[RecommendationItem] = []
    over: list[RecommendationItem] = []
    for product in candidates:
        score = scores[product.id]
        if not budget_known or product.price is None:
            # 没有预算就没有「超预算」这回事，全部归入主列表，
            # 但 budget_known=False 保证界面标注「未设定预算」。
            within.append(
                RecommendationItem(
                    product=product,
                    score=score,
                    within_budget=True,
                    budget_known=budget_known,
                )
            )
            continue
        if product.price <= demand.budget:  # type: ignore[operator]
            within.append(
                RecommendationItem(product=product, score=score, within_budget=True)
            )
        else:
            over.append(
                RecommendationItem(
                    product=product,
                    score=score,
                    within_budget=False,
                    overage=product.price - demand.budget,
                )
            )

    # 两列都按需求适配评分降序——不是按价格。
    within.sort(key=lambda item: (-item.score.total, item.product.price or 0))
    over.sort(key=lambda item: (-item.score.total, item.product.price or 0))

    result = RecommendationResult(
        demand=demand,
        within_budget=within[:limit],
        # 超预算列表用**自己的**上限：`limit` 是「预算内推荐条数上限」，
        # 拿它截断超预算列表会让界面上报出比实际少的条数。
        over_budget=over[: config.MAX_OVER_BUDGET_SHOWN],
        over_budget_total=len(over),
        notes=notes,
        candidate_count=len(candidates),
    )

    if not result.within_budget:
        result.relaxations = _build_relaxations(catalog, demand, candidates)
    else:
        _append_budget_tension_note(result)
    return result


def _append_budget_tension_note(result: RecommendationResult) -> None:
    """预算内首选不如某件超预算商品时，明确说出来。

    这是这个产品存在的主要理由之一：用户被预算框住时，
    最需要知道的恰恰是「再多花多少能买到明显更合适的」，
    而不是被默默地只推荐预算内那件最差的。
    """
    if not result.within_budget or not result.over_budget:
        return
    best_within = result.within_budget[0]
    best_over = result.over_budget[0]
    if best_over.score.total <= best_within.score.total:
        return
    result.notes.append(
        f"预算内首选「{best_within.product.name}」的{config.SCORE_DISPLAY_NAME}"
        f"为 {best_within.score.total:.0f} 分，低于超预算的「{best_over.product.name}」"
        f"（{best_over.score.total:.0f} 分，超出 {best_over.overage:.0f} 元）。"
        f"若预算可上浮，后者更贴合你的需求。"
    )
