"""需求解析的测试。

覆盖 spec `demand-parsing` 的全部 Scenario：
完整解析、缺失字段留空、不重复追问、结构化覆盖自然语言、
空输入 / 负数预算 / 非数值预算的拒绝。

全部用例都不联网、不需要任何密钥。
"""

from __future__ import annotations

import pytest

from src.demand_parser import (
    Demand,
    detect_unsupported_category,
    follow_up_questions,
    merge_demand,
    parse_budget_value,
    parse_demand,
    unsupported_category_message,
)
from src.errors import EmptyDemand, InvalidBudget

# 需求方给的那个原始示例句，逐字照抄
FULL_EXAMPLE = (
    "我是一名大学生，预算 3000 元，想买一台主要用于 Python 编程、"
    "日常学习和偶尔玩游戏的笔记本电脑。我比较看重性能和性价比，"
    "不希望电脑太重。"
)


# --------------------------------------------------------------------------
# 完整需求
# --------------------------------------------------------------------------


def test_full_example_is_parsed_into_structured_fields(catalog):
    demand = parse_demand(FULL_EXAMPLE, known_brands=catalog.brands())

    assert demand.category == "laptop"
    assert demand.category_label == "笔记本电脑"
    assert demand.budget == 3000

    for expected in ("编程", "学习", "游戏"):
        assert expected in demand.use_cases, f"用途漏了「{expected}」"

    for expected in ("性能", "性价比", "便携"):
        assert expected in demand.core_needs, f"核心需求漏了「{expected}」"

    assert demand.source == "rule"
    assert demand.raw_text == FULL_EXAMPLE.strip()


def test_parsed_demand_is_ready_for_analysis_without_any_follow_up(catalog):
    demand = parse_demand(FULL_EXAMPLE, known_brands=catalog.brands())
    assert demand.is_ready_for_analysis()
    assert follow_up_questions(demand) == []


def test_screen_size_is_not_mistaken_for_budget():
    """「14 寸」「6.7 寸」这类参数不能被当成预算。"""
    demand = parse_demand("预算 3000，想要 14 寸的笔记本，屏幕大一点")
    assert demand.budget == 3000

    no_budget = parse_demand("想要一台 6.7 寸的手机")
    assert no_budget.budget is None


def test_budget_is_none_when_text_mentions_budget_but_no_number():
    demand = parse_demand("想买手机，预算还没想好，先看看")
    assert demand.budget is None


def test_chinese_numeral_budget_is_understood():
    assert parse_demand("预算三千元买笔记本").budget == 3000
    assert parse_demand("预算 5 千左右买手机").budget == 5000
    assert parse_demand("预算两千五百的耳机").budget == 2500


def test_budget_range_takes_the_upper_bound():
    assert parse_demand("预算 3000-4000 的笔记本").budget == 4000


# --------------------------------------------------------------------------
# 缺信息时留空，不猜
# --------------------------------------------------------------------------


def test_missing_fields_stay_empty_instead_of_being_guessed():
    demand = parse_demand("想买个耳机")

    assert demand.category == "headphone"
    assert demand.budget is None
    assert demand.use_cases == []
    assert demand.core_needs == []
    assert demand.has_budget is False


def test_unknown_category_leaves_category_empty():
    demand = parse_demand("想买个平板，预算 2000")
    assert demand.category == ""
    assert demand.budget == 2000


# --------------------------------------------------------------------------
# 追问
# --------------------------------------------------------------------------


def test_follow_up_only_asks_about_the_missing_key_field():
    demand = parse_demand("想买台笔记本")
    questions = follow_up_questions(demand)

    assert len(questions) == 1
    assert "预算" in questions[0]
    assert all("类别" not in q for q in questions)


def test_no_follow_up_when_category_and_budget_are_both_known():
    demand = parse_demand("预算 5000，想买手机")
    assert follow_up_questions(demand) == []


def test_follow_up_asks_both_when_both_missing():
    demand = parse_demand("帮我看看买什么好")
    questions = follow_up_questions(demand)

    assert len(questions) == 2
    assert any("类别" in q for q in questions)
    assert any("预算" in q for q in questions)


# --------------------------------------------------------------------------
# 结构化输入与自然语言的合并
# --------------------------------------------------------------------------


def test_structured_value_overrides_natural_language():
    parsed = parse_demand("预算 3000 买笔记本")
    structured = Demand(category="laptop", budget=5000)

    merged = merge_demand(structured, parsed)

    assert merged.budget == 5000, "结构化控件填了预算，就应以控件为准"
    assert merged.source == "merged"


def test_structured_fills_in_what_natural_language_missed():
    parsed = parse_demand("想买台笔记本，主要编程")
    structured = Demand(budget=4500)

    merged = merge_demand(structured, parsed)

    assert merged.budget == 4500          # 来自控件
    assert merged.category == "laptop"    # 来自自然语言
    assert "编程" in merged.use_cases


def test_list_fields_are_unioned_not_replaced():
    parsed = parse_demand("预算 3000 买笔记本，想玩游戏")
    structured = Demand(use_cases=["编程"])

    merged = merge_demand(structured, parsed)

    assert set(merged.use_cases) == {"编程", "游戏"}


def test_structured_only_input_is_usable():
    demand = Demand(category="headphone", budget=500)
    assert demand.is_ready_for_analysis()


# --------------------------------------------------------------------------
# 非法输入
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_empty_input_is_rejected(text):
    with pytest.raises(EmptyDemand):
        parse_demand(text)


@pytest.mark.parametrize("value", [-100, -1, 0, "-500"])
def test_non_positive_budget_is_rejected(value):
    with pytest.raises(InvalidBudget):
        parse_budget_value(value)


@pytest.mark.parametrize("value", ["三千块", "三千", "abc", "很多钱", "3.4.5", "3000-4000"])
def test_unparseable_budget_is_rejected(value):
    with pytest.raises(InvalidBudget):
        parse_budget_value(value)


def test_structured_field_rejects_chinese_numerals_but_text_field_accepts_them():
    """这是有意为之的差异，对应 spec 里「预算字段填『三千块』应报错」的 Scenario。

    数字控件只收阿拉伯数字；自然语言里「预算三千」是正常表达，照常识别。
    """
    with pytest.raises(InvalidBudget):
        parse_budget_value("三千块")

    assert parse_demand("预算三千块买耳机").budget == 3000


@pytest.mark.parametrize(
    "text",
    ["预算 -100 买手机", "预算-100买手机", "笔记本预算负3000", "最多 -500 的耳机"],
)
def test_negative_budget_in_free_text_is_rejected(text):
    """自由文本里的负数预算同样要报错，不能被正则把负号吃掉当成正数。"""
    with pytest.raises(InvalidBudget):
        parse_demand(text)


def test_unsupported_category_is_detected(catalog):
    assert detect_unsupported_category("想买个平板，预算 2000") == "平板"
    assert detect_unsupported_category("想买相机") == "相机"
    assert detect_unsupported_category("预算 3000 的笔记本") is None


def test_unsupported_category_message_lists_what_is_supported():
    message = unsupported_category_message("平板")

    assert "平板" in message
    for label in ("笔记本电脑", "手机", "耳机", "键盘"):
        assert label in message


def test_unsupported_category_does_not_leak_into_a_supported_one():
    """「台式电脑」不该被当成笔记本——台式机不在支持范围内。"""
    assert detect_unsupported_category("想买台式电脑") == "台式"


def test_empty_structured_budget_is_treated_as_not_provided():
    """控件留空不是错误——预算本来就是可选字段，缺失会走追问。"""
    assert parse_budget_value(None) is None
    assert parse_budget_value("") is None
    assert parse_budget_value("   ") is None


def test_valid_structured_budget_is_accepted():
    assert parse_budget_value(3000) == 3000
    assert parse_budget_value(3000.5) == 3000.5
    assert parse_budget_value("3000") == 3000
    assert parse_budget_value("3000 元") == 3000
    assert parse_budget_value("3000块") == 3000
    assert parse_budget_value(" 4500 ") == 4500


# --------------------------------------------------------------------------
# 其他字段
# --------------------------------------------------------------------------


def test_brand_preference_is_matched_against_catalog_brands(catalog):
    demand = parse_demand("预算 3000，想要轻羽的笔记本", known_brands=catalog.brands())
    assert demand.brand_preferences == ["轻羽"]


def test_unknown_brand_is_not_invented(catalog):
    demand = parse_demand("想要一个不存在的牌子的手机", known_brands=catalog.brands())
    assert demand.brand_preferences == []


def test_hard_constraint_is_detected_only_with_a_requirement_marker():
    must = parse_demand("买耳机，必须有降噪")
    assert "降噪" in must.hard_constraints

    mere_preference = parse_demand("买耳机，我不介意没有降噪")
    assert "降噪" not in mere_preference.hard_constraints


def test_compromise_is_recorded():
    demand = parse_demand("买笔记本，预算 3000，重一点没关系")
    assert demand.compromises


def test_summary_line_mentions_the_key_facts():
    demand = parse_demand(FULL_EXAMPLE)
    summary = demand.summary_line()

    assert "笔记本电脑" in summary
    assert "3000" in summary


# --------------------------------------------------------------------------
# 本地模式
# --------------------------------------------------------------------------


def test_parsing_makes_no_network_calls(monkeypatch, catalog):
    """规则解析必须是纯本地的——这是「无密钥也能用」的基础。"""
    import socket

    def _explode(*args, **kwargs):
        raise AssertionError("需求解析过程中发生了网络访问")

    monkeypatch.setattr(socket.socket, "connect", _explode)
    monkeypatch.setattr(socket, "create_connection", _explode)

    demand = parse_demand(FULL_EXAMPLE, known_brands=catalog.brands())
    assert demand.budget == 3000
