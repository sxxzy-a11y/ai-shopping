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
from src.errors import TooFewForComparison, TooManyForComparison


@pytest.fixture
def three_laptops(catalog):
    return [catalog.get(pid) for pid in ("LP001", "LP002", "LP003")]


@pytest.fixture
def laptop_demand() -> Demand:
    return Demand(category="laptop", budget=3000)


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


def test_boolean_parameters_are_rendered_in_chinese(three_laptops, laptop_demand):
    table = compare(three_laptops, laptop_demand)
    values = _row(table, "独立显卡").values

    assert set(values) <= {"有", "无"}
    assert "无" in values  # LP001 是核显本
    assert "有" in values  # LP002 带独显


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
    """spec：预算内标记预算内，超预算标记超出多少。"""
    cheap = catalog.get("LP004")   # 2499，预算内
    pricey = catalog.get("LP002")  # 5999，超预算
    mid = catalog.get("LP001")     # 3299，超预算

    table = compare([cheap, pricey, mid], laptop_demand)
    values = _row(table, "预算匹配").values

    assert values[0] == "预算内"
    assert values[1] == "超出预算 2999 元"
    assert values[2] == "超出预算 299 元"


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


def test_comparison_keeps_the_demo_data_source(catalog, laptop_demand):
    """spec：演示数据标注不能因为是「比较结果」就丢掉。"""
    table = compare([catalog.get(p) for p in ("LP001", "LP002", "LP003")], laptop_demand)

    for value in _row(table, "数据来源").values:
        assert "演示" in value


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
# 跨类别
# --------------------------------------------------------------------------


def test_cross_category_comparison_still_produces_aligned_rows(catalog):
    """比较不同类别的商品时，各商品没有的参数按缺失处理，表格不错位。"""
    items = [catalog.get("LP001"), catalog.get("PH001"), catalog.get("HP001")]
    table = compare(items, Demand(budget=3000))

    for row in table.rows:
        assert len(row.values) == 3

    # 处理器只有笔记本有，另外两件必须标缺失
    cpu_row = _row(table, "处理器")
    assert cpu_row.missing == [False, True, True]
