"""筛选、评分与排序的测试。

覆盖 spec `recommendation-engine` 的全部 Scenario，以及阶段二验收点：
预算筛选正确、排序逻辑正确、缺参数安全处理、无匹配正确提示、
条件变更后重新计算。
"""

from __future__ import annotations

import pytest

from src import config
from src.data_loader import Catalog, Product
from src.demand_parser import Demand
from src.scoring import score_all, score_product
from src.recommender import recommend


def _fake_laptop(product_id: str, price: float, **specs) -> Product:
    """自造一件笔记本，用于**与数据集无关**的规则测试。

    有些规则（排序、截断）要验的是逻辑本身，用真实数据来验就会变成
    「这一版数据恰好满足」——数据集一换，断言跟着失效，而失败信息
    看上去像逻辑坏了。这里把要测的条件直接摆出来。
    """
    return Product(
        id=product_id,
        name=f"测试机 {product_id}",
        category="laptop",
        price=price,
        brand="测试品牌",
        specs=specs,
        use_cases=["办公"],
        pros=["测试用"],
        cons=["测试用"],
        data_source="测试夹具 · 非真实数据",
        updated_at="2026-10-15",
    )


def _fake_headphones(count: int, *, base_price: float = 800.0) -> Catalog:
    """一批自造耳机，价格每件递增 100 元。

    专供「超预算条数」那几条测试：截断只在候选数超过展示上限时才触发，
    而真实数据集每个类别恰好 10 件、上限也正好是 10——拿真数据来测，
    截断这一步永远走不到，测试会一直绿着却什么也没验证。
    """
    products = [
        Product(
            id=f"FH{index:03d}",
            name=f"测试耳机 {index}",
            category="headphone",
            price=base_price + index * 100,
            brand="测试品牌",
            specs={
                "driver_mm": 40, "connection": "蓝牙 5.3", "battery_h": 30,
                "weight_g": 250, "noise_cancelling": True, "audio_tier": 3,
            },
            use_cases=["通勤"],
            pros=["测试用"],
            cons=["测试用"],
            data_source="测试夹具 · 非真实数据",
            updated_at="2026-10-15",
        )
        for index in range(count)
    ]
    return Catalog(products=products)


# --------------------------------------------------------------------------
# 权重表（design.md D4：权重集中配置）
# --------------------------------------------------------------------------


@pytest.mark.parametrize("category", sorted(config.SCORING_WEIGHTS))
def test_weight_table_sums_to_one(category):
    """漏配或改错权重会直接让这条测试失败。"""
    weights = config.SCORING_WEIGHTS[category]
    assert sum(weights.values()) == pytest.approx(1.0)
    assert all(w > 0 for w in weights.values())


@pytest.mark.parametrize("category", sorted(config.SCORING_WEIGHTS))
def test_every_weight_key_has_a_chinese_label(category):
    for dimension in config.SCORING_WEIGHTS[category]:
        assert dimension in config.DIMENSION_LABELS


def test_categories_use_different_dimensions():
    """spec 要求：不同商品类别使用不同的评分权重。

    两个品类都保留便携性（天天带着走 / 握在手里），
    差异体现在其余维度的权重分配上。
    """
    assert "portability" in config.SCORING_WEIGHTS["laptop"]
    assert "portability" in config.SCORING_WEIGHTS["phone"]
    assert config.SCORING_WEIGHTS["laptop"] != config.SCORING_WEIGHTS["phone"], (
        "两个品类的权重表不能完全相同，否则「按品类自适应」名存实亡"
    )


def test_no_category_uses_the_durability_dimension():
    """「耐用性」已随非电子品类一并消失。

    它当年是为家电、家具、母婴这类耐用品设的维度，读的是 `durability_tier`。
    四个电子品类都没有这个参数——留着权重只会让每份报告里多出一个
    永远算不出分、只能标「数据缺失」的维度。
    """
    for category, weights in config.SCORING_WEIGHTS.items():
        assert "durability" not in weights, category


def test_weight_table_covers_exactly_the_catalog_categories():
    """权重表与类别名表必须同集合，不能多也不能少。

    这两张表分开维护。少配一类不会报错：那个类别的商品照样能进库、
    照样被搜到，只是评分时找不到权重表——所以必须由测试来守。
    """
    assert set(config.SCORING_WEIGHTS) == set(config.CATEGORY_LABELS)


@pytest.mark.parametrize("category", sorted(config.SCORING_WEIGHTS))
def test_every_category_scores_without_errors(catalog, category):
    """每个品类的商品都能算出 0–100 的分，且维度不越出该类别的权重表。"""
    products = catalog.by_category(category)
    assert products, f"{category} 没有商品"

    results = score_all(products, Demand(category=category))

    assert len(results) == len(products)
    for product in products:
        result = results[product.id]
        assert 0.0 <= result.total <= 100.0
        assert all(
            d.key in config.SCORING_WEIGHTS[category] for d in result.dimensions
        ), f"{product.id} 出现了权重表外的维度"


# --------------------------------------------------------------------------
# 评分维度
# --------------------------------------------------------------------------


def test_laptop_scores_include_portability(catalog, student_laptop_demand):
    laptop = catalog.get("LP001")
    result = score_product(laptop, student_laptop_demand, catalog.by_category("laptop"))

    keys = {d.key for d in result.dimensions}
    assert "portability" in keys
    assert not any("便携性" in label for label, _ in result.excluded)


# （原 test_headphone_scores_exclude_portability_with_reason 已随耳机品类移除：
#   「排除维度必须给出原因」由 test_missing_specs_exclude_dimensions_instead_of_defaulting
#   用缺失参数的夹具继续守护；「按品类权重差异」由 test_categories_use_different_dimensions 守护。）


def test_score_total_is_weighted_average_of_dimensions(catalog, student_laptop_demand):
    laptop = catalog.get("LP003")
    result = score_product(laptop, student_laptop_demand, catalog.by_category("laptop"))

    weight_total = sum(d.weight for d in result.dimensions)
    expected = sum(d.score * d.weight for d in result.dimensions) / weight_total
    assert result.total == pytest.approx(expected, abs=0.05)


def test_bonus_and_penalty_track_dimension_ranks(catalog, student_laptop_demand):
    """spec：加分项对应得分最高的维度，扣分项对应得分最低的维度。

    维度分数可能并列，所以断言写成「属于最高/最低分那一组」，
    而不是绑死某一个具体维度。
    """
    checked = 0
    for laptop in catalog.by_category("laptop"):
        result = score_product(laptop, student_laptop_demand, catalog.by_category("laptop"))
        if len(result.dimensions) < 2:
            continue

        best = max(d.score for d in result.dimensions)
        worst = min(d.score for d in result.dimensions)
        best_labels = {d.label for d in result.dimensions if d.score == best}
        worst_labels = {d.label for d in result.dimensions if d.score == worst}

        assert any(label in result.bonus[0] for label in best_labels), (
            f"{laptop.id} 的加分项首位不是最高分维度：{result.bonus[0]}"
        )
        assert any(label in result.penalty[0] for label in worst_labels), (
            f"{laptop.id} 的扣分项首位不是最低分维度：{result.penalty[0]}"
        )
        checked += 1

    assert checked >= 5, "样本太少，这条测试没起到作用"


def test_bonus_and_penalty_are_deterministic_under_ties(catalog, student_laptop_demand):
    """并列分数不能让加分项在不同次运行间跳来跳去。"""
    peers = catalog.by_category("laptop")
    first = score_product(catalog.get("LP006"), student_laptop_demand, peers)

    assert len(first.dimensions) >= 2
    for _ in range(5):
        again = score_product(catalog.get("LP006"), student_laptop_demand, peers)
        assert again.bonus == first.bonus
        assert again.penalty == first.penalty
        assert again.total == first.total


def test_missing_specs_exclude_dimensions_instead_of_defaulting(catalog, minimal_laptop):
    """spec：缺参数商品仍能得到评分，缺失维度不参与计算并标明。"""
    result = score_product(minimal_laptop, _demand(), [minimal_laptop])

    labels = {d.key for d in result.dimensions}
    assert "performance_fit" not in labels
    assert "portability" not in labels

    excluded_labels = {label for label, _ in result.excluded}
    assert "性能功能适配" in excluded_labels
    assert "便携性" in excluded_labels
    # 每个被排除的维度都必须给出原因
    assert all(reason for _, reason in result.excluded)


def test_disabled_score_naming_avoids_market_claims():
    """spec：评分不得暗示为真实市场口碑。"""
    assert config.SCORE_DISPLAY_NAME in {"系统匹配评分", "需求适配评分"}


def test_match_level_uses_explainable_wording(catalog, student_laptop_demand):
    result = score_product(catalog.get("LP001"), student_laptop_demand, catalog.by_category("laptop"))
    assert result.match_level in {"高度匹配", "较为匹配", "基本可用", "匹配度较低"}


# --------------------------------------------------------------------------
# 预算过滤
# --------------------------------------------------------------------------


def test_budget_splits_candidates_into_within_and_over(catalog, student_laptop_demand):
    result = recommend(catalog, student_laptop_demand)

    assert result.within_budget, "预算内应至少命中一件"
    for item in result.within_budget:
        assert item.product.price <= student_laptop_demand.budget
        assert item.within_budget is True
        assert item.budget_label == "预算内"

    for item in result.over_budget:
        assert item.product.price > student_laptop_demand.budget
        assert item.within_budget is False


def test_over_budget_item_reports_exact_overage(catalog, student_laptop_demand):
    result = recommend(catalog, student_laptop_demand)

    for item in result.over_budget:
        expected = item.product.price - student_laptop_demand.budget
        assert item.overage == pytest.approx(expected)
        assert f"{expected:.0f} 元" in item.budget_label


def test_over_budget_products_are_never_labelled_within_budget(catalog, student_laptop_demand):
    result = recommend(catalog, student_laptop_demand)

    for item in result.over_budget:
        assert item.budget_label != "预算内"
        assert "超出预算" in item.budget_label


def test_no_budget_labels_items_as_unset_not_within_budget(catalog):
    """spec：未设定预算时标注「未设定预算」，而不是「预算内」。"""
    from src.demand_parser import Demand

    demand = Demand(category="phone")
    result = recommend(catalog, demand)

    assert result.within_budget
    assert all(item.budget_label == "未设定预算" for item in result.all_items())


# --------------------------------------------------------------------------
# 排序
# --------------------------------------------------------------------------


def test_results_are_sorted_by_score_descending(catalog, wide_budget_laptop_demand):
    result = recommend(catalog, wide_budget_laptop_demand)
    totals = [item.score.total for item in result.within_budget]
    assert totals == sorted(totals, reverse=True)


def test_sorting_is_not_by_price(catalog, wide_budget_laptop_demand):
    """spec：不得仅按价格排序作为默认推荐顺序。"""
    result = recommend(catalog, wide_budget_laptop_demand)
    prices = [item.product.price for item in result.within_budget]

    assert prices != sorted(prices), "结果恰好按价格升序，说明排序退化成按价格排了"
    assert prices != sorted(prices, reverse=True)

    cheapest = min(catalog.by_category("laptop"), key=lambda p: p.price)
    assert result.within_budget[0].product.id != cheapest.id


def test_higher_need_match_outranks_cheaper_weak_item():
    """spec：价格更高但需求匹配更好的商品应排在前面。

    用自造的两件商品，不借数据集：这条验的是排序规则，而规则不该依赖
    「这一版数据里最便宜的那件恰好最弱」——那种依赖会变成一条看似在测
    排序、实则在测数据的断言。
    """
    weak = _fake_laptop(
        "WEAK", 3500, cpu_tier=1, ram_gb=8, storage_gb=256,
        weight_kg=1.9, battery_h=5, has_dedicated_gpu=False,
    )
    strong = _fake_laptop(
        "STRONG", 6000, cpu_tier=5, ram_gb=32, storage_gb=1024,
        weight_kg=1.4, battery_h=10, has_dedicated_gpu=True,
    )
    demand = Demand(category="laptop", budget=8000, use_cases=["办公"], core_needs=["性能"])

    result = recommend(Catalog(products=[weak, strong]), demand, limit=10)

    order = [item.product.id for item in result.within_budget]
    assert order == ["STRONG", "WEAK"], "性能需求下，更强但更贵的那件应当排前面"


def test_changing_core_needs_changes_the_order(catalog):
    """spec：结果随需求变化，且变化可由维度得分解释。"""
    from src.demand_parser import Demand

    common = dict(category="laptop", budget=8000, use_cases=["编程", "办公"])

    by_performance = recommend(catalog, Demand(**common, core_needs=["性能"]))
    by_portability = recommend(catalog, Demand(**common, core_needs=["便携"]))

    order_perf = [i.product.id for i in by_performance.within_budget]
    order_port = [i.product.id for i in by_portability.within_budget]

    assert order_perf != order_port, "调整核心需求后推荐顺序毫无变化"

    # 便携优先时，首选应确实更轻
    best_port = by_portability.within_budget[0].product
    best_perf = by_performance.within_budget[0].product
    assert best_port.spec("weight_kg") <= best_perf.spec("weight_kg")


def test_changing_budget_recomputes_candidates(catalog):
    """spec：调整预算后重新计算，不沿用上次结果。"""
    prices = sorted(p.price for p in catalog.by_category("laptop") if p.price)
    # 紧的一侧只够最便宜那件；松的一侧比最贵的还高，超预算一侧应当为空
    tight_budget = prices[0]
    loose_budget = prices[-1] + 1

    # 同样要放大限条数，否则两边的截断会掩盖真实的候选差异
    limit = len(catalog)
    tight = recommend(catalog, Demand(category="laptop", budget=tight_budget), limit=limit)
    loose = recommend(catalog, Demand(category="laptop", budget=loose_budget), limit=limit)

    tight_ids = {i.product.id for i in tight.within_budget}
    loose_ids = {i.product.id for i in loose.within_budget}

    assert tight_ids < loose_ids, "放宽预算后应有更多商品进入预算内"
    assert tight.over_budget, "预算收紧时应有商品落到超预算一侧"
    assert not loose.over_budget, "预算高于最贵商品时不应再有超预算项"

    # 同一件商品在两次分析中的预算匹配得分应当不同——说明确实是重算的
    shared = tight_ids & loose_ids
    assert shared
    sample = next(iter(shared))
    tight_score = next(i.score for i in tight.within_budget if i.product.id == sample)
    loose_score = next(i.score for i in loose.within_budget if i.product.id == sample)
    assert tight_score.total != loose_score.total or tight_score != loose_score


# --------------------------------------------------------------------------
# 无匹配与放宽建议
# --------------------------------------------------------------------------


def test_budget_below_cheapest_gives_price_specific_suggestion(catalog):
    from src.demand_parser import Demand

    result = recommend(catalog, Demand(category="laptop", budget=500))

    assert result.within_budget == []
    assert result.over_budget, "超预算商品仍应列出，而不是藏起来"
    assert result.relaxations

    cheapest = min(p.price for p in catalog.by_category("laptop"))
    joined = " ".join(result.relaxations)
    assert f"{cheapest:.0f}" in joined, "建议里应给出具体的最低参考价"
    assert "预算" in joined


def test_unknown_brand_gives_brand_relaxation(catalog):
    from src.demand_parser import Demand

    result = recommend(
        catalog,
        Demand(category="laptop", budget=8000, brand_preferences=["不存在的品牌"]),
    )

    assert result.within_budget == []
    joined = " ".join(result.relaxations)
    assert "品牌" in joined
    assert "不存在的品牌" in joined


def test_unsatisfiable_hard_constraint_gives_relaxation(catalog):
    from src.demand_parser import Demand

    # 手机的参数里没有「独立显卡」这一项，所以这条硬性要求一件都满足不了。
    # 预算给得足够高，确保候选被筛空的原因**只有约束**，
    # 而不是「同时也超了预算」——否则这条测试会因为预算而通过，测错了东西。
    prices = [p.price for p in catalog.by_category("phone") if p.price]
    result = recommend(
        catalog,
        Demand(category="phone", budget=max(prices) + 1, hard_constraints=["独显"]),
    )

    assert result.candidate_count == 0
    assert result.within_budget == []
    assert any("独显" in text or "限制" in text for text in result.relaxations)


def test_category_absent_from_dataset_gives_usable_alternatives(catalog):
    from src.demand_parser import Demand

    result = recommend(catalog, Demand(category="tablet", budget=2000))

    assert result.has_results is False
    joined = " ".join(result.relaxations)
    assert "笔记本电脑" in joined or "手机" in joined


def test_no_results_never_returns_a_bare_empty_list(catalog):
    """spec：无匹配时不得仅返回空列表。"""
    from src.demand_parser import Demand

    for demand in (
        Demand(category="laptop", budget=1),
        Demand(category="laptop", budget=8000, brand_preferences=["无此品牌"]),
        Demand(category="tablet", budget=2000),
    ):
        result = recommend(catalog, demand)
        assert result.relaxations, f"{demand} 没有给出任何放宽建议"


# --------------------------------------------------------------------------
# 其他行为
# --------------------------------------------------------------------------


def test_weaker_within_budget_pick_triggers_a_budget_tension_note():
    """预算内首选明显不如某件超预算商品时，必须主动说出来。

    用自造的两件商品，前提直接摆在明面上：便宜的弱、贵的好。
    拿真实数据来测的话，这条能不能过取决于这一版数据的价格与参数分布，
    失败信息只会说「62.5 > 77.8 不成立」，看不出其实是数据变了。
    """
    weak = _fake_laptop(
        "WEAK", 3500, cpu_tier=1, ram_gb=8, storage_gb=256,
        weight_kg=1.9, battery_h=5, has_dedicated_gpu=False,
    )
    strong = _fake_laptop(
        "STRONG", 6000, cpu_tier=5, ram_gb=32, storage_gb=1024,
        weight_kg=1.4, battery_h=10, has_dedicated_gpu=True,
    )
    demand = Demand(category="laptop", budget=4000, use_cases=["办公"], core_needs=["性能"])

    result = recommend(Catalog(products=[weak, strong]), demand, limit=10)

    best_within = result.within_budget[0]
    best_over = result.over_budget[0]
    assert best_over.score.total > best_within.score.total

    assert any(
        best_within.product.name in note and best_over.product.name in note
        for note in result.notes
    )


def test_only_requested_category_is_considered(catalog, student_laptop_demand):
    result = recommend(catalog, student_laptop_demand)
    assert all(i.product.category == "laptop" for i in result.all_items())


def test_limit_is_respected(catalog, wide_budget_laptop_demand):
    result = recommend(catalog, wide_budget_laptop_demand, limit=2)
    assert len(result.within_budget) <= 2


def test_best_prefers_within_budget_over_higher_scoring_over_budget(catalog, student_laptop_demand):
    result = recommend(catalog, student_laptop_demand)
    assert result.best.product.price <= student_laptop_demand.budget


def test_score_all_covers_every_product(catalog, student_laptop_demand):
    scores = score_all(catalog.products, student_laptop_demand)
    assert set(scores) == {p.id for p in catalog.products}


def _demand():
    from src.demand_parser import Demand

    return Demand(category="laptop", budget=3000)


# --------------------------------------------------------------------------
# 超预算条数如实展示（变更 fix-over-budget-count）
# --------------------------------------------------------------------------


def test_over_budget_total_is_the_real_count():
    """超预算条数是**真实总数**，不是截断后的列表长度。

    原问题：10 件超预算只显示 6 件，界面还把 6 说成总数。账面对不上——
    6 + 6 = 12 ≠ 16 件候选。
    """
    catalog = _fake_headphones(config.MAX_OVER_BUDGET_SHOWN + 5)
    result = recommend(catalog, Demand(category="headphone", budget=500))

    assert result.over_budget_total > 0
    assert (
        len(result.within_budget) + result.over_budget_total == result.candidate_count
    ), "预算内 + 超预算真实总数应当等于候选总数"


def test_within_budget_limit_does_not_truncate_over_budget():
    """预算内推荐条数上限**不作用于**超预算列表——两者是各自独立的上限。

    这条针对的是根因：曾经两处共用同一个 `limit`，而它的文档写的是
    「预算内推荐条数上限」。钉死这个耦合，免得以后有人图省事又合回去。
    """
    catalog = _fake_headphones(15)
    demand = Demand(category="headphone", budget=1500)  # 价格 800–2200，两侧都有

    small = recommend(catalog, demand, limit=2)
    large = recommend(catalog, demand, limit=8)

    # limit 只管预算内：调大它，预算内条数变多（预算内只有 6 件，所以 8 也只得 6）
    assert len(small.within_budget) == 2, "受 limit 约束的是预算内这一侧"
    assert len(large.within_budget) > len(small.within_budget)

    # 而超预算列表完全不受影响
    assert len(small.over_budget) == len(large.over_budget)
    assert small.over_budget_total == large.over_budget_total


def test_over_budget_list_respects_its_own_cap():
    """超预算列表有自己的上限，且真实总数不受它影响。"""
    catalog = _fake_headphones(config.MAX_OVER_BUDGET_SHOWN + 5)
    result = recommend(catalog, Demand(category="headphone", budget=1))

    assert len(result.over_budget) <= config.MAX_OVER_BUDGET_SHOWN
    assert result.over_budget_total == result.candidate_count
    assert result.over_budget_total > len(result.over_budget), "夹具没有产生截断"


def test_over_budget_hidden_counts_the_gap():
    catalog = _fake_headphones(config.MAX_OVER_BUDGET_SHOWN + 5)
    result = recommend(catalog, Demand(category="headphone", budget=1))

    assert result.over_budget_hidden == (
        result.over_budget_total - len(result.over_budget)
    )
    assert result.over_budget_hidden > 0


def test_over_budget_hidden_is_zero_when_everything_shown(catalog):
    """候选数没超过上限时，不该出现「还有 N 件未显示」这种无中生有的提示。"""
    result = recommend(catalog, Demand(category="headphone", budget=1))

    assert result.over_budget_total <= config.MAX_OVER_BUDGET_SHOWN
    assert len(result.over_budget) == result.over_budget_total
    assert result.over_budget_hidden == 0


def test_over_budget_total_defaults_to_zero():
    """有默认值——老的历史快照没有这个字段也能反序列化。"""
    from src.recommender import RecommendationResult

    assert RecommendationResult(demand=Demand()).over_budget_total == 0


def test_within_budget_total_is_the_real_count(catalog):
    """预算内条数同样是**真实总数**——与超预算对称。

    前一变更修了超预算条数的截断问题，漏了预算内：统计行「预算内 6 件」
    在 17 件都在预算内时同样误导读者。两者对称，测试也成对。
    """
    budget = max(p.price for p in catalog.by_category("laptop")) + 1
    result = recommend(catalog, Demand(category="laptop", budget=budget))

    assert result.within_budget_total == result.candidate_count
    assert result.within_budget_total > len(result.within_budget), "夹具没有产生截断"
    assert result.within_budget_hidden == (
        result.within_budget_total - len(result.within_budget)
    )


def test_both_totals_close_the_books(catalog):
    """预算内真实总数 + 超预算真实总数 == 候选总数。两边都是真实值才对得上。"""
    for budget in (100, 500, 3000, 10000):
        for category in ("headphone", "laptop", "phone"):
            result = recommend(catalog, Demand(category=category, budget=budget))
            assert (
                result.within_budget_total + result.over_budget_total
                == result.candidate_count
            ), f"{category} 预算 {budget} 的账面不闭合"


def test_within_budget_hidden_is_zero_when_nothing_truncated(catalog):
    result = recommend(catalog, Demand(category="headphone", budget=500))
    assert result.within_budget_total == len(result.within_budget)
    assert result.within_budget_hidden == 0


def test_limit_only_changes_what_is_shown(catalog):
    """推荐条数上限只影响**展示**，不影响任何一类的真实总数。"""
    demand = Demand(category="laptop", budget=10000)
    small = recommend(catalog, demand, limit=2)
    large = recommend(catalog, demand, limit=8)

    assert len(small.within_budget) == 2
    assert len(large.within_budget) == 8
    assert small.within_budget_total == large.within_budget_total
