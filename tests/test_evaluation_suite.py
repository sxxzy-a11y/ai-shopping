"""评测集自身的校验。

**评测集错了，报告就是错的。** 这个文件不测系统，只测评测资产本身：
场景类别齐不齐、标注的商品是否真实存在、格式对不对。

为什么值得单独测：评测集的腐化是**静默**的。删掉一个品类、写错一个商品 ID、
漏掉一类幻觉场景——评测脚本照跑，报告照出，只是数字变得没有意义。
把校验做进测试，缺失会报错而不是悄悄通过。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import data_loader

CASES_PATH = Path(__file__).resolve().parent.parent / "data" / "evaluation" / "cases.json"

#: 必须覆盖的场景类别。少了任何一个，评测的覆盖面就有洞。
REQUIRED_CATEGORIES = {
    "需求理解",
    "预算边界",
    "知识检索",
    "语料外反例",
    "多商品比较",
    "工具调用",
    # 幻觉场景六类——README §13.3 定义的那六类，一类都不能少
    "幻觉场景1_不存在的商品",
    "幻觉场景2_商品缺参数",
    "幻觉场景3_预算低于全部候选",
    "幻觉场景4_知识库无资料",
    "幻觉场景5_资料自相矛盾",
    "幻觉场景6_无依据的性能结论",
}

#: 评测集规模的合理区间（roadmap 建议 30–50 条）
MIN_CASES, MAX_CASES = 30, 60


@pytest.fixture(scope="module")
def payload() -> dict:
    assert CASES_PATH.exists(), f"评测集不存在：{CASES_PATH}"
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cases(payload: dict) -> list[dict]:
    return payload["cases"]


@pytest.fixture(scope="module")
def catalog():
    return data_loader.load_catalog()


# --------------------------------------------------------------------------
# 规模与覆盖
# --------------------------------------------------------------------------


def test_case_count_is_within_the_planned_range(cases):
    assert MIN_CASES <= len(cases) <= MAX_CASES, (
        f"评测集有 {len(cases)} 条，超出 {MIN_CASES}–{MAX_CASES} 的计划区间"
    )


def test_every_required_category_is_covered(cases):
    present = {case["category"] for case in cases}
    missing = REQUIRED_CATEGORIES - present
    assert missing == set(), f"这些场景类别一条用例都没有：{sorted(missing)}"


def test_hallucination_scenarios_each_have_a_case(cases):
    """幻觉六类**每一类**都要有——这是 roadmap 明确要求的全覆盖。"""
    for index in range(1, 7):
        prefix = f"幻觉场景{index}_"
        hits = [c for c in cases if c["category"].startswith(prefix)]
        assert hits, f"幻觉场景 {index} 没有对应用例"


def test_no_category_is_dominated_by_a_single_kind(cases):
    """类别分布不该过度偏斜——全是同一类会让评测失去意义。"""
    from collections import Counter

    counts = Counter(case["category"] for case in cases)
    most = counts.most_common(1)[0]
    assert most[1] <= len(cases) * 0.35, f"「{most[0]}」占了 {most[1]} 条，过于集中"


# --------------------------------------------------------------------------
# 每条用例的格式
# --------------------------------------------------------------------------


def test_every_case_has_required_fields(cases):
    required = {"id", "category", "origin", "input", "expected"}
    for case in cases:
        missing = required - set(case)
        assert not missing, f"{case.get('id')} 缺少字段：{sorted(missing)}"


def test_every_case_explains_its_origin(cases):
    """`origin` 是**评测集的诚实性来源**——它说明这条用例依据什么构造的。

    没有它，读者会默认这是一套中立基准。
    """
    for case in cases:
        assert case["origin"].strip(), f"{case['id']} 没有说明构造依据"
        assert len(case["origin"]) >= 6, f"{case['id']} 的 origin 过于简略"


def test_case_ids_are_unique(cases):
    ids = [case["id"] for case in cases]
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert duplicates == set(), f"用例 ID 重复：{sorted(duplicates)}"


def test_inputs_are_not_blank(cases):
    for case in cases:
        assert str(case["input"]).strip(), f"{case['id']} 的输入为空"


def test_expected_is_not_empty(cases):
    for case in cases:
        assert case["expected"], f"{case['id']} 没有标注任何预期"


# --------------------------------------------------------------------------
# 标注的商品必须真实存在
# --------------------------------------------------------------------------


def _referenced_ids(case: dict) -> list[str]:
    """抽出用例里引用的商品 ID。"""
    expected = case["expected"]
    found: list[str] = []
    for key in ("must_include", "must_exclude"):
        found.extend(expected.get("demand", {}).get(key, []) or [])
        found.extend(expected.get(key, []) or [])
    compare = expected.get("compare") or {}
    found.extend(compare.get("ids", []) or [])
    return found


def test_referenced_product_ids_exist(cases, catalog):
    """标注指向不存在的商品会让评测结果失去意义——这是最需要拦住的一类错误。"""
    problems: list[str] = []
    for case in cases:
        for product_id in _referenced_ids(case):
            if catalog.get(product_id) is None:
                problems.append(f"{case['id']} 引用了不存在的商品 {product_id}")
    assert problems == [], "\n".join(problems)


def test_must_include_and_exclude_do_not_overlap(cases):
    """同一件商品不能既要求出现又要求不出现。"""
    for case in cases:
        demand = case["expected"].get("demand", {})
        include = set(demand.get("must_include") or [])
        exclude = set(demand.get("must_exclude") or [])
        assert not (include & exclude), f"{case['id']} 的必含与必排有重叠：{include & exclude}"


# --------------------------------------------------------------------------
# 预期的自洽性
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "left, right",
    [
        ("must_all_satisfy_budget", "should_have_no_within_budget"),
        ("should_have_no_within_budget", "should_have_no_over_budget"),
        ("must_include", "should_have_no_within_budget"),
    ],
)
def test_contradictory_expectations_are_not_both_set(cases, left, right):
    """自相矛盾的预期会让评测永远失败——那比没有评测更糟。"""
    problems = [
        case["id"]
        for case in cases
        if (case["expected"].get("demand", {}).get(left) or case["expected"].get(left))
        and (case["expected"].get("demand", {}).get(right) or case["expected"].get(right))
    ]
    assert problems == [], f"这些用例同时设置了 {left} 与 {right}：{problems}"


def test_knowledge_expectations_declare_find_or_not(cases):
    for case in cases:
        knowledge = case["expected"].get("knowledge")
        if knowledge is None:
            continue
        assert "should_find" in knowledge, f"{case['id']} 的知识预期没说要找得到还是找不到"
        if knowledge["should_find"]:
            assert knowledge.get("expected_type"), (
                f"{case['id']} 要求检索命中，但没说命中的应当是哪一类文档——"
                f"那样就只能测「有没有结果」，测不出「结果对不对」"
            )


def test_compare_expectations_declare_outcome(cases):
    for case in cases:
        compare = case["expected"].get("compare")
        if compare is None:
            continue
        assert "should_succeed" in compare, f"{case['id']} 的比较预期没说该成功还是该失败"
        assert len(compare.get("ids", [])) >= 1, f"{case['id']} 的比较预期没有给 ID"


def test_tool_expectations_declare_outcome(cases):
    for case in cases:
        tool = case["expected"].get("tool")
        if tool is None:
            continue
        assert "should_succeed" in tool, f"{case['id']} 的工具预期没说该成功还是该失败"
        assert tool.get("name"), f"{case['id']} 的工具预期没有工具名"


# --------------------------------------------------------------------------
# 文件本身的元信息
# --------------------------------------------------------------------------


def test_file_declares_it_is_self_authored(payload: dict):
    """报告与评测集都要声明这是**自评**——这是这个评测最容易被误读的地方。"""
    note = payload.get("note", "")
    assert "自评" in note or "自行" in note, "评测集没有声明它是本项目自建的"
    assert payload.get("updated_at"), "缺少更新时间"
    assert payload.get("name"), "缺少名称"
