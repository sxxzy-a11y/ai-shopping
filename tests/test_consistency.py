"""商品记录一致性检测的测试。

这个文件要同时守住两件相反的事：

1. **规则真的会响**——否则「检测」只是装饰。用构造的矛盾夹具证明每条规则都能命中。
2. **规则不会误响**——一条不准的规则会把正常商品污名化成「资料存疑」，比不做更糟。
   最难的一类是「肯定式 vs 否定式」：数据里真实存在「无独显」「不可折叠」这种
   **正确的否定句**，朴素关键词匹配会把它判成矛盾。

第 2 类里最有说服力的是 `test_flag_fires_on_real_text_...`：拿真实商品的真实文案，
只把参数从「有」改成「没有」，规则必须立刻响——证明匹配器认得出真实文本里的
肯定式，而不是碰巧什么都没匹配上。
"""

from __future__ import annotations

import pytest

from src import consistency
from src.consistency import Issue, check_catalog, check_product, mentions_positively
from src.data_loader import Catalog, Product, load_catalog


def _product(**overrides) -> Product:
    """构造一条最小商品，按需覆盖字段。"""
    base: dict = {"id": "T001", "name": "测试商品", "category": "laptop"}
    base.update(overrides)
    return Product(**base)


# 真实文案（取自 data/products.json），用于证明匹配器认得出肯定式提及。
# LP006 戴尔 游匣 G15 5530：参数 has_dedicated_gpu=true，pros 里写着「独显」。
_REAL_GPU_PRO_TEXT = "i7-13650HX + RTX4060 满血独显直连，1080p 高刷游戏流畅"


# --------------------------------------------------------------------------
# 否定感知的文本匹配
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("带独立显卡，游戏有加成", True),
        ("无独显，不适合 3D 游戏", False),
        ("没有独立显卡", False),
        ("不含独显", False),
        ("不支持折叠", False),
        ("可折叠，收纳方便", True),
        ("", False),
    ],
)
def test_mentions_positively_handles_negation(text: str, expected: bool):
    """否定式的提及不算数，肯定式的算。"""
    assert mentions_positively(text, ("独显", "独立显卡", "折叠")) is expected


def test_negation_window_is_bounded():
    """否定判定只看关键词前几个字符，太远的否定词不算数。"""
    # 「无」（前面第 4 字）超出 3 字窗口，因此后半句的「独显」算肯定式提及
    assert mentions_positively("这台机器无光驱，但是有独显", ("独显",)) is True
    # 紧邻的否定词在窗口内
    assert mentions_positively("这台机器无独显", ("独显",)) is False


# --------------------------------------------------------------------------
# R1 — 档位越界
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 6, -1, 99])
def test_tier_out_of_range_is_flagged(value: int):
    product = _product(specs={"cpu_tier": value})
    issues = check_product(product)
    assert [i.field for i in issues] == ["cpu_tier"]


@pytest.mark.parametrize("value", [1, 2, 3, 4, 5])
def test_tier_within_range_is_not_flagged(value: int):
    assert check_product(_product(specs={"cpu_tier": value})) == []


def test_tier_rule_only_covers_tier_keys():
    """档位校验只认档位键，别的参数取大数值不算越界。

    `noise_level`（键盘）与 `energy_grade`（家电）曾作为「不带 _tier 后缀的
    档位字段」走同一套校验，随那两个品类一起移除了。剩下的边界是反方向：
    不能把 `storage_gb = 9` 这种正常取值当成越界的档位。
    """
    assert [i.field for i in check_product(_product(specs={"cpu_tier": 9}))] == [
        "cpu_tier"
    ]
    assert check_product(_product(specs={"storage_gb": 9})) == []


def test_boolean_is_not_treated_as_a_tier_number():
    """`isinstance(True, int)` 为真——布尔值不能被当成档位 1 而漏判。"""
    assert check_product(_product(specs={"cpu_tier": True})) == []


def test_non_numeric_tier_is_ignored():
    """档位写成文字时不由本规则负责（属于格式问题，不是矛盾）。"""
    assert check_product(_product(specs={"cpu_tier": "未知"})) == []


# --------------------------------------------------------------------------
# R2 — 价格非正
# --------------------------------------------------------------------------


@pytest.mark.parametrize("price", [0, -1, -99.5])
def test_non_positive_price_is_flagged(price: float):
    issues = check_product(_product(price=price))
    assert [i.field for i in issues] == ["price"]


@pytest.mark.parametrize("price", [0.01, 199, 9999])
def test_positive_price_is_not_flagged(price: float):
    assert check_product(_product(price=price)) == []


def test_missing_price_is_left_to_missing_fields():
    """价格**缺失**归 missing_fields 管，本规则不重复报告。

    否则同一个缺陷会被贴两个标签（「信息不完整」+「资料存疑」），用户看到的是
    两条说明同一件事的提示。
    """
    product = _product(price=None)
    assert check_product(product) == []
    assert "price" in product.missing_fields


# --------------------------------------------------------------------------
# R3 — 优点与缺点重复
# --------------------------------------------------------------------------


def test_duplicate_pros_and_cons_is_flagged():
    product = _product(pros=["续航长", "重量轻"], cons=["续航长", "屏幕一般"])
    issues = check_product(product)
    assert len(issues) == 1
    assert issues[0].field == "pros"
    assert "续航长" in issues[0].reason


def test_overlapping_but_not_identical_items_are_not_flagged():
    """只是措辞相近不算重复——要求完全一致，避免把同义改写判成矛盾。"""
    product = _product(pros=["续航长"], cons=["续航一般"])
    assert check_product(product) == []


# --------------------------------------------------------------------------
# R5 / R6 — 参数说不支持，文字说支持
# --------------------------------------------------------------------------


def test_positive_claim_with_false_spec_is_flagged():
    product = _product(
        specs={"has_dedicated_gpu": False},
        pros=[_REAL_GPU_PRO_TEXT],
    )
    issues = check_product(product)
    assert [i.field for i in issues] == ["has_dedicated_gpu"]


def test_negated_claim_with_false_spec_is_not_flagged():
    """「无独显」与 `has_dedicated_gpu: false` 是**一致**的，不能报矛盾。"""
    product = _product(
        specs={"has_dedicated_gpu": False},
        cons=["无独显，大型 3D 游戏性能不足"],
    )
    assert check_product(product) == []


def test_boolean_claim_rule_checks_the_name_too():
    """名称写着「独立显卡」而参数为 false，同样是矛盾。"""
    product = _product(name="某某 独立显卡笔记本", specs={"has_dedicated_gpu": False})
    assert [i.field for i in check_product(product)] == ["has_dedicated_gpu"]


def test_true_spec_with_positive_claim_is_consistent():
    """参数说支持、文字也说支持——一致，不该报。"""
    product = _product(
        specs={"has_dedicated_gpu": True},
        pros=[_REAL_GPU_PRO_TEXT],
    )
    assert check_product(product) == []


def test_missing_boolean_spec_is_not_flagged():
    """参数里根本没这个字段时不能推断矛盾——缺数据不等于矛盾。"""
    product = _product(specs={}, pros=[_REAL_GPU_PRO_TEXT])
    assert check_product(product) == []


# --------------------------------------------------------------------------
# 规则不是空转（反向核对）
# --------------------------------------------------------------------------


def test_flag_fires_on_real_text_when_spec_contradicts():
    """用真实商品的真实文案，只把参数反过来，规则必须立刻响。

    这条是「规则不是空转」的关键证据：证明匹配器认得出真实文本里的肯定式提及，
    而不是碰巧在真实数据上什么都没匹配到。
    """
    consistent = _product(
        specs={"has_dedicated_gpu": True}, pros=[_REAL_GPU_PRO_TEXT]
    )
    assert check_product(consistent) == []

    contradicted = _product(
        specs={"has_dedicated_gpu": False}, pros=[_REAL_GPU_PRO_TEXT]
    )
    assert [i.field for i in check_product(contradicted)] == ["has_dedicated_gpu"]


def test_flag_fires_on_a_second_real_text():
    """换一条真实文案再验一次，证明不是碰巧只认得出那一句话。"""
    # 缺点里提到独显，参数却说没有——这是真会出现的写法：
    # 吐槽某个功能的副作用，仍然是在肯定它存在。
    real = "散热一般，独显满载时风扇声明显"
    consistent = _product(specs={"has_dedicated_gpu": True}, cons=[real])
    assert check_product(consistent) == []

    contradicted = _product(specs={"has_dedicated_gpu": False}, cons=[real])
    assert [i.field for i in check_product(contradicted)] == ["has_dedicated_gpu"]


def test_real_catalog_is_not_flagged():
    """硬验收线：现有全部商品，误报必须为 0。

    这条一旦失败，说明新加的规则把正常商品判成了「资料存疑」——
    先判断是规则误报还是数据确有缺陷，**不要为了让它变绿而改数据**。
    """
    catalog = load_catalog()
    found = check_catalog(catalog.products)
    detail = {
        pid: [f"{i.field}: {i.reason}" for i in issues] for pid, issues in found.items()
    }
    assert found == {}, f"现有数据出现误报，共 {len(found)} 条：{detail}"


# --------------------------------------------------------------------------
# 容错
# --------------------------------------------------------------------------


def test_check_product_does_not_raise_on_unexpected_specs():
    """参数里塞进奇怪的值时不能抛异常——本属性会被界面直接访问。"""
    product = _product(specs={"cpu_tier": [1, 2], "foldable": "no", "x": {"a": 1}})
    assert isinstance(check_product(product), list)


def test_check_catalog_only_returns_products_with_issues():
    products = [
        _product(id="OK1"),
        _product(id="BAD1", price=-5),
    ]
    found = check_catalog(products)
    assert set(found) == {"BAD1"}
    assert isinstance(found["BAD1"][0], Issue)


def test_issue_is_hashable_and_comparable():
    """Issue 做成 frozen dataclass，便于在测试与去重里当值使用。"""
    assert Issue(field="price", reason="x") == Issue(field="price", reason="x")
    assert len({Issue(field="a", reason="b"), Issue(field="a", reason="b")}) == 1


# --------------------------------------------------------------------------
# 与评分、筛选的关系
# --------------------------------------------------------------------------


def test_data_issues_do_not_affect_scoring():
    """存疑标记**不参与评分**。

    存疑是数据质量问题，不是商品劣势。把它算进分数等于把数据缺陷转嫁成
    商品缺点，用户会看到错误的推荐理由。这里用「优缺点重复」制造矛盾——
    评分不读 pros/cons，因此总分必须一模一样。
    """
    from src.demand_parser import Demand
    from src.scoring import score_product

    clean = _product(
        id="P1",
        specs={"cpu_tier": 3},
        pros=["续航长", "重量轻"],
        cons=["屏幕一般"],
        price=4999,
    )
    contradicted = _product(
        id="P1",
        specs={"cpu_tier": 3},
        pros=["续航长", "重量轻", "屏幕一般"],  # 「屏幕一般」同时出现在缺点里
        cons=["屏幕一般"],
        price=4999,
    )
    demand = Demand(raw_text="测试", category="laptop", budget=6000.0)

    assert check_product(clean) == []
    assert check_product(contradicted) != []

    assert score_product(clean, demand).total == score_product(contradicted, demand).total


def test_flag_does_not_remove_product_from_results():
    """存疑商品仍正常参与筛选——不因标记被排除。

    如果标记导致商品消失，就会诱使后来者「删数据解决校验」，
    这正是本变更要避免的。
    """
    from src.demand_parser import Demand
    from src.recommender import recommend

    flagged = _product(
        id="KEEP1",
        name="存疑笔记本",
        category="laptop",
        price=4999,
        specs={"cpu_tier": 3},
        pros=["续航长"],
        cons=["续航长"],  # 与优点重复 → 触发 R3
        use_cases=["办公"],
    )
    assert check_product(flagged) != []

    catalog = Catalog(products=[flagged])
    demand = Demand(raw_text="办公用笔记本", category="laptop", budget=6000.0)
    result = recommend(catalog, demand)

    assert [item.product.id for item in result.within_budget] == ["KEEP1"]


def test_loader_integration_does_not_raise_when_a_rule_fails(monkeypatch):
    """某条规则内部抛异常时，不牵连加载，也不让属性访问炸开。

    本属性会被界面直接访问（每张商品卡片都会读），抛异常会顺着渲染流程炸开。
    """

    def _boom(_product):
        raise RuntimeError("模拟规则内部错误")

    monkeypatch.setattr(consistency, "_RULES", (("boom", _boom),))
    product = _product()
    assert check_product(product) == []
