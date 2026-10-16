"""多商品比较的测试。

覆盖 spec `product-comparison` 的全部 Scenario：
三件商品比较表、数量不足与超限的拒绝、缺失字段标注、差异标注、
预算匹配状态、未设定预算的处理。
"""

from __future__ import annotations

import pytest

from src import config
from src.comparison import MISSING_TEXT, compare
from src.data_loader import Product
from src.demand_parser import Demand
from src.errors import (
    MixedCategoryComparison,
    TooFewForComparison,
    TooManyForComparison,
)


@pytest.fixture
def three_laptops(catalog):
    """三件**同类不同款**的笔记本，按价格从低到高取，便于阅读结果。"""
    return sorted(catalog.by_category("laptop"), key=lambda p: p.price or 0)[:3]


@pytest.fixture
def laptop_demand(catalog) -> Demand:
    """预算取在「第三便宜」和「第四便宜」之间。

    刻意不写死金额：写死一个数，数据集一换就可能变成「全部超预算」或
    「全部在预算内」，而「预算内 / 超预算」这两条分支里总有一条空着——
    测试仍然是绿的，只是有一半没测到。
    """
    prices = sorted(p.price for p in catalog.by_category("laptop") if p.price)
    return Demand(category="laptop", budget=(prices[2] + prices[3]) / 2)


def _row(table, label):
    """按标签取一行，取不到直接失败并列出所有可用标签。"""
    for row in table.rows:
        if row.label == label:
            return row
    raise AssertionError(f"比较表里没有「{label}」行，现有：{[r.label for r in table.rows]}")


# --------------------------------------------------------------------------
# 基本形态
# --------------------------------------------------------------------------


def test_three_products_produce_a_complete_table(three_laptops, laptop_demand):
    table = compare(three_laptops, laptop_demand)

    assert len(table) == 3
    assert table.headers == [p.name for p in three_laptops]

    labels = [row.label for row in table.rows]
    for required in ("参考价格", "品牌", "适用场景", "优点", "缺点", "预算匹配"):
        assert required in labels, f"比较表缺少「{required}」行"

    # 每行的单元格数必须与商品数一致，否则界面会错位
    for row in table.rows:
        assert len(row.values) == len(three_laptops)
        assert len(row.missing) == len(three_laptops)


def test_core_parameters_appear_as_rows(three_laptops, laptop_demand):
    table = compare(three_laptops, laptop_demand)
    labels = {row.label for row in table.rows}

    for param_label in ("处理器", "内存", "存储", "整机重量", "续航"):
        assert param_label in labels


def test_rows_carry_units(three_laptops, laptop_demand):
    table = compare(three_laptops, laptop_demand)

    assert "GB" in _row(table, "内存").values[0]
    assert "kg" in _row(table, "整机重量").values[0]


def test_boolean_parameters_are_rendered_in_chinese(catalog, laptop_demand):
    """布尔参数要显示成中文，而不是 True / False。

    两种取值都从数据里现取——数据集中独显本的占比会变，
    写死「前三件里一定有一件带独显」在换数据集后必然失败。
    """
    laptops = catalog.by_category("laptop")
    with_gpu = [p for p in laptops if p.spec("has_dedicated_gpu")]
    without_gpu = [p for p in laptops if not p.spec("has_dedicated_gpu")]
    assert with_gpu and without_gpu, "数据集里应当同时存在独显本与核显本"

    table = compare([with_gpu[0], without_gpu[0]], laptop_demand)
    values = _row(table, "独立显卡").values

    assert set(values) <= {"有", "无"}
    assert values[0] == "有"
    assert values[1] == "无"


# --------------------------------------------------------------------------
# 数量约束
# --------------------------------------------------------------------------


@pytest.mark.parametrize("count", [0, 1])
def test_fewer_than_minimum_products_is_rejected(catalog, count, laptop_demand):
    products = catalog.by_category("laptop")[:count]
    with pytest.raises(TooFewForComparison) as excinfo:
        compare(products, laptop_demand)

    assert str(config.MIN_COMPARE_COUNT) in str(excinfo.value)


def test_more_than_the_cap_is_rejected(catalog, laptop_demand):
    too_many = catalog.by_category("laptop")[: config.MAX_COMPARE_COUNT + 1]
    with pytest.raises(TooManyForComparison) as excinfo:
        compare(too_many, laptop_demand)

    assert str(config.MAX_COMPARE_COUNT) in str(excinfo.value)


def test_exactly_the_minimum_and_maximum_are_accepted(catalog, laptop_demand):
    laptops = catalog.by_category("laptop")

    assert len(compare(laptops[: config.MIN_COMPARE_COUNT], laptop_demand)) == config.MIN_COMPARE_COUNT
    assert len(compare(laptops[: config.MAX_COMPARE_COUNT], laptop_demand)) == config.MAX_COMPARE_COUNT


def test_duplicate_products_are_rejected(catalog, laptop_demand):
    same = catalog.get("LP001")
    with pytest.raises(ValueError):
        compare([same, same, same], laptop_demand)


# --------------------------------------------------------------------------
# 同类约束（spec: 比较范围限定在同一类别）
# --------------------------------------------------------------------------


def test_mixed_categories_are_rejected_with_a_clear_message(catalog, laptop_demand):
    """衣服和电脑放在一起比没有意义——跨类别混选必须被挡掉。"""
    laptop = catalog.by_category("laptop")[0]
    phone = catalog.by_category("phone")[0]

    with pytest.raises(MixedCategoryComparison) as excinfo:
        compare([laptop, phone], laptop_demand)

    message = str(excinfo.value)
    assert "同一类别" in message
    assert "笔记本电脑" in message and "手机" in message, "提示里应指出混选了哪些类别"


def test_mixed_categories_rejected_even_without_demand(catalog):
    """不传需求也一样拦——这是比较本身的规则，与本次需求无关。"""
    items = [catalog.by_category("laptop")[0], catalog.by_category("phone")[0]]
    with pytest.raises(MixedCategoryComparison):
        compare(items)


def test_same_category_still_compares_after_the_guard(catalog, laptop_demand):
    items = catalog.by_category("laptop")[:3]
    table = compare(items, laptop_demand)
    assert len(table) == 3


# --------------------------------------------------------------------------
# 缺失数据
# --------------------------------------------------------------------------


def test_missing_field_is_labelled_not_left_blank(catalog, laptop_demand):
    """spec：缺失字段标注为信息缺失，不留空、不用别的商品的值填充。"""
    broken = Product(
        id="BROKEN",
        name="缺参数机型",
        category="laptop",
        price=3500,
        brand="测试",
        data_source="演示数据 · 测试夹具",
        updated_at="2026-10-01",
    )
    table = compare([catalog.get("LP001"), catalog.get("LP002"), broken], laptop_demand)

    weight_row = _row(table, "整机重量")
    assert weight_row.values[2] == MISSING_TEXT
    assert weight_row.missing[2] is True
    # 其他列不受影响，也没有被 broken 的空值污染
    assert weight_row.values[0] != MISSING_TEXT
    assert weight_row.missing[0] is False

    use_case_row = _row(table, "适用场景")
    assert use_case_row.values[2] == MISSING_TEXT


def test_missing_cell_count_is_reported(catalog, laptop_demand):
    broken = Product(id="B2", name="空壳", category="laptop", price=3500)
    table = compare([catalog.get("LP001"), catalog.get("LP002"), broken], laptop_demand)

    assert table.missing_cells > 0


def test_row_with_no_data_at_all_is_omitted(catalog, laptop_demand):
    """所有商品都没有的参数不该占一整行「信息缺失」。"""
    table = compare(
        [catalog.get("LP001"), catalog.get("LP002"), catalog.get("LP003")],
        laptop_demand,
    )
    labels = [row.label for row in table.rows]
    # 笔记本数据里没有「键位布局」——那是键盘的参数
    assert "键位布局" not in labels


# --------------------------------------------------------------------------
# 差异标注
# --------------------------------------------------------------------------


def test_differing_values_are_flagged_for_highlighting(three_laptops, laptop_demand):
    table = compare(three_laptops, laptop_demand)

    assert _row(table, "参考价格").varies is True
    assert _row(table, "品牌").varies is True


def test_identical_values_are_not_flagged(three_laptops, laptop_demand):
    table = compare(three_laptops, laptop_demand)
    # LP001/LP002/LP003 三件都是笔记本，类别一致；这里用数据来源行验证一致行不被标记
    assert _row(table, "数据来源").varies is False


# --------------------------------------------------------------------------
# 预算匹配
# --------------------------------------------------------------------------


def test_budget_match_column_reflects_the_budget(catalog, laptop_demand):
    """spec：预算内标记预算内，超预算标记超出多少。

    商品与超出金额都从数据里算，不写死——写死的数字在数据集一换之后
    会变成「断言里的金额和它自己的预算对不上」，而失败信息看起来像是
    比较表算错了。
    """
    laptops = sorted(catalog.by_category("laptop"), key=lambda p: p.price or 0)
    budget = laptop_demand.budget
    within = [p for p in laptops if p.price <= budget]
    over = [p for p in laptops if p.price > budget]
    assert within and over, "夹具选出的预算应当同时造出两种预算状态"

    picks = [within[-1], over[0], over[1]]
    table = compare(picks, laptop_demand)
    values = _row(table, "预算匹配").values

    assert values[0] == "预算内"
    assert values[1] == f"超出预算 {over[0].price - budget:.0f} 元"
    assert values[2] == f"超出预算 {over[1].price - budget:.0f} 元"


def test_unset_budget_is_labelled_unset_not_within_budget(three_laptops):
    """spec：未设定预算时标注未设定预算，而非显示为预算内。"""
    table = compare(three_laptops, Demand(category="laptop"))

    values = _row(table, "预算匹配").values
    assert set(values) == {"未设定预算"}
    assert "预算内" not in values

    # 省略 demand 参数时同样如此
    assert set(_row(compare(three_laptops), "预算匹配").values) == {"未设定预算"}


# --------------------------------------------------------------------------
# 溯源
# --------------------------------------------------------------------------


def test_comparison_keeps_the_data_source(three_laptops, laptop_demand):
    """spec：来源标注不能因为是「比较结果」就丢掉。

    这条以前断言的是「来源里含『演示』二字」；数据集换成真实品牌之后，
    该守的变成了**每条都要有来源说明**——来源缺失比来源写得不好更严重，
    因为界面上一片空白看起来像「这条数据不需要出处」。
    """
    table = compare(three_laptops, laptop_demand)

    values = _row(table, "数据来源").values
    assert all(value.strip() for value in values), values


# --------------------------------------------------------------------------
# 界面用的转换
# --------------------------------------------------------------------------


def test_to_records_is_ready_for_a_dataframe(three_laptops, laptop_demand):
    table = compare(three_laptops, laptop_demand)
    records = table.to_records()

    assert len(records) == len(table.rows)
    assert all("比较维度" in record for record in records)
    for record in records:
        for header in table.headers:
            assert header in record


# --------------------------------------------------------------------------
# 缺失参数的对齐（同类之间）
# --------------------------------------------------------------------------


def test_missing_params_within_a_category_are_aligned(catalog, laptop_demand):
    """同类商品之间参数有缺有全时，表格按列对齐，缺失项逐格标注。"""
    complete = catalog.get("LP001")
    broken = Product(id="LP-BROKEN", name="缺参数机型", category="laptop", price=3500)

    table = compare([complete, broken], laptop_demand)

    for row in table.rows:
        assert len(row.values) == 2

    cpu_row = _row(table, "处理器")
    assert cpu_row.missing == [False, True], "缺参数的商品应标缺失，且不影响另一列"
