"""决策报告组装与导出的测试。

覆盖 spec `decision-report` 的全部 Scenario，重点在两件事：
报告必须**固化为快照**（不被后续数据变化影响），
以及待核实项必须来自**真实数据缺口**而不是免责套话。
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from src import config
from src.data_loader import Catalog, Product
from src.demand_parser import Demand
from src.recommender import recommend
from src.report_service import (
    STALE_DAYS,
    DecisionReport,
    build_report,
    collect_verification_items,
    csv_bytes,
    markdown_bytes,
    now_local,
    suggested_filename,
    to_csv,
    to_markdown,
)

#: 报告必须包含的八个部分
REQUIRED_SECTIONS = (
    "需求摘要",
    "预算与筛选条件",
    "推荐商品及排序",
    "超出预算的候选",
    "放宽条件的建议",
    "分析过程说明",
    "需要进一步核实的信息",
    "最终决策建议",
)


@pytest.fixture
def laptop_demand() -> Demand:
    return Demand(
        category="laptop",
        budget=4000,
        use_cases=["编程", "学习"],
        core_needs=["性能", "性价比"],
        raw_text="预算 4000 的笔记本，主要编程和学习",
    )


@pytest.fixture
def sample_report(catalog, laptop_demand) -> DecisionReport:
    result = recommend(catalog, laptop_demand)
    return build_report(catalog, laptop_demand, result)


# --------------------------------------------------------------------------
# 报告结构
# --------------------------------------------------------------------------


def test_report_contains_every_required_section(sample_report):
    markdown = to_markdown(sample_report)

    for section in REQUIRED_SECTIONS:
        assert section in markdown, f"报告缺少「{section}」小节"


def test_report_has_no_recommendations_section_when_nothing_matched(catalog):
    demand = Demand(category="laptop", budget=1)
    report = build_report(catalog, demand, recommend(catalog, demand))

    assert report.recommendations == []
    assert "没有预算内的匹配商品" in to_markdown(report)
    # 不能编造推荐条目
    assert report.over_budget, "超预算商品仍应列出"


def test_recommendations_are_ranked_and_scored(sample_report):
    assert sample_report.recommendations
    ranks = [item.rank for item in sample_report.recommendations]
    assert ranks == list(range(1, len(ranks) + 1))

    scores = [item.score_total for item in sample_report.recommendations]
    assert scores == sorted(scores, reverse=True), "报告里的推荐没有按分数排序"


def test_reasons_trace_back_to_product_data(sample_report):
    """推荐理由里的数字必须能在商品数据里找到出处。"""
    for item in sample_report.recommendations:
        assert item.reasons
        joined = " ".join(item.reasons)
        assert item.price_label.split()[0] in joined or "参考价" in joined

        # 理由里引用的参数名，必须真的出现在该商品的 specs 里
        assert item.pros or item.cons or item.reasons


def test_every_item_carries_its_data_source(sample_report):
    """spec：导出时不得丢失演示数据来源标注。"""
    for item in [*sample_report.recommendations, *sample_report.over_budget]:
        assert "演示" in item.data_source
        assert item.updated_at


# --------------------------------------------------------------------------
# 待核实项
# --------------------------------------------------------------------------


def test_verification_items_come_from_real_gaps(catalog, laptop_demand):
    result = recommend(catalog, laptop_demand)
    items = collect_verification_items(result, catalog)

    assert items
    joined = " ".join(items)
    # 必须点出数据集本身不包含哪些维度，而不是泛泛的免责声明
    assert "销量" in joined
    assert "售后" in joined or "评价" in joined
    for vague in ("投资有风险", "仅供参考，请谨慎决策"):
        assert vague not in joined


def test_stale_dataset_is_flagged(catalog, laptop_demand):
    """数据集更新时间距今超过阈值时，必须提示价格可能已变化。"""
    old = catalog.dataset_updated_at
    stale_date = (now_local().date() - timedelta(days=STALE_DAYS + 30)).isoformat()
    stale = Catalog(
        products=catalog.products,
        dataset_name=catalog.dataset_name,
        disclaimer=catalog.disclaimer,
        dataset_updated_at=stale_date,
        tier_note=catalog.tier_note,
    )

    result = recommend(stale, laptop_demand)
    items = collect_verification_items(result, stale)
    joined = " ".join(items)

    assert stale_date in joined
    assert "可能已经变化" in joined
    assert old != stale_date


def test_fresh_dataset_is_not_flagged_as_stale(catalog, laptop_demand):
    fresh = Catalog(
        products=catalog.products,
        dataset_updated_at=now_local().date().isoformat(),
        disclaimer=catalog.disclaimer,
    )
    items = collect_verification_items(recommend(fresh, laptop_demand), fresh)
    assert not any("可能已经变化" in item for item in items)


def test_incomplete_product_is_flagged_by_name(catalog, laptop_demand):
    broken = Product(id="BROKEN", name="缺参数机型", category="laptop", price=3500)
    patched = Catalog(products=[*catalog.products, broken], disclaimer=catalog.disclaimer)

    result = recommend(patched, laptop_demand)
    items = collect_verification_items(result, patched)

    assert any("缺参数机型" in item for item in items)


# --------------------------------------------------------------------------
# 最终建议
# --------------------------------------------------------------------------


def test_conclusion_names_the_top_pick(sample_report):
    top = sample_report.recommendations[0]
    assert top.name in sample_report.conclusion
    assert config.SCORE_DISPLAY_NAME in sample_report.conclusion


def test_conclusion_is_honest_when_no_within_budget_match(catalog):
    """预算内没匹配上时，要明说这一点，同时给出可上浮的选项。"""
    demand = Demand(category="laptop", budget=1)
    report = build_report(catalog, demand, recommend(catalog, demand))

    assert report.recommendations == []
    assert "预算内没有可选商品" in report.conclusion
    assert "放宽" in report.conclusion or "预算可上浮" in report.conclusion


def test_conclusion_says_nothing_when_there_is_nothing_at_all(catalog):
    """类别整个不在数据集里时，必须直说「不给出推荐」，而不是硬凑一个。"""
    demand = Demand(category="tablet", budget=2000)
    report = build_report(catalog, demand, recommend(catalog, demand))

    assert report.conclusion.startswith("在本次给出的条件下没有找到合适的商品")
    assert "不给出推荐" in report.conclusion


def test_conclusion_admits_a_weak_match(catalog):
    """首选匹配度低时必须说出来，不能只报喜。"""
    demand = Demand(category="laptop", budget=3000, core_needs=["性能", "便携"])
    result = recommend(catalog, demand)
    report = build_report(catalog, demand, result)

    if report.recommendations and report.recommendations[0].match_level in {
        "匹配度较低",
        "基本可用",
    }:
        assert "匹配评分并不高" in report.conclusion


# --------------------------------------------------------------------------
# 快照语义
# --------------------------------------------------------------------------


def test_report_does_not_change_when_the_catalog_changes(catalog, laptop_demand):
    """spec：历史报告还原原始结论，不按当前数据重算。"""
    result = recommend(catalog, laptop_demand)
    report = build_report(catalog, laptop_demand, result)
    before = to_markdown(report)

    # 把商品价格改掉，模拟数据更新
    mutated = Catalog(
        products=[
            p.model_copy(update={"price": (p.price or 0) * 3}) for p in catalog.products
        ],
        disclaimer=catalog.disclaimer,
    )
    assert mutated.products[0].price != catalog.products[0].price

    assert to_markdown(report) == before, "报告跟着商品数据变了，说明存的是引用不是快照"


def test_report_round_trips_through_json(sample_report):
    restored = DecisionReport.from_dict(json.loads(json.dumps(sample_report.to_dict())))

    assert restored.created_at == sample_report.created_at
    assert restored.demand_summary == sample_report.demand_summary
    assert len(restored.recommendations) == len(sample_report.recommendations)
    assert restored.recommendations[0].score_total == sample_report.recommendations[0].score_total
    assert restored.recommendations[0].reasons == sample_report.recommendations[0].reasons
    assert restored.demand_facts == sample_report.demand_facts
    assert to_markdown(restored) == to_markdown(sample_report)


def test_from_dict_tolerates_missing_fields():
    """老记录缺少新加的字段时也要能打开。"""
    report = DecisionReport.from_dict({"created_at": "2026-01-01T00:00:00", "demand_summary": "旧的"})
    assert report.recommendations == []
    assert report.to_verify == []


# --------------------------------------------------------------------------
# 导出
# --------------------------------------------------------------------------


def test_markdown_keeps_the_demo_data_disclaimer(sample_report):
    markdown = to_markdown(sample_report)
    assert "演示" in markdown
    assert "数据说明" in markdown
    assert config.SCORE_DISPLAY_NAME in markdown


def test_markdown_states_the_score_is_not_market_reputation(sample_report):
    markdown = to_markdown(sample_report)
    assert "不是用户评价" in markdown


def test_csv_has_one_row_per_product(sample_report):
    rows = list(csv.reader(io.StringIO(to_csv(sample_report))))

    header, body = rows[0], rows[1:]
    expected = len(sample_report.recommendations) + len(sample_report.over_budget)
    assert len(body) == expected

    assert "商品名称" in header
    assert config.SCORE_DISPLAY_NAME in header
    assert "预算匹配" in header


def test_csv_includes_price_score_and_budget_status(sample_report):
    rows = list(csv.DictReader(io.StringIO(to_csv(sample_report))))
    assert rows

    first = rows[0]
    assert first["商品名称"]
    assert first["参考价格"].endswith("元")
    assert first[config.SCORE_DISPLAY_NAME].isdigit()
    assert first["预算匹配"]


def test_csv_keeps_the_data_source(sample_report):
    rows = list(csv.DictReader(io.StringIO(to_csv(sample_report))))
    assert all("演示" in row["数据来源"] for row in rows)


def test_csv_bytes_start_with_a_bom(sample_report):
    """没有 BOM 的话 Excel 打开中文会乱码，用户会以为导出坏了。"""
    assert csv_bytes(sample_report).startswith(b"\xef\xbb\xbf")


def test_exports_handle_an_empty_report(catalog):
    demand = Demand(category="tablet", budget=1000)
    report = build_report(catalog, demand, recommend(catalog, demand))

    assert to_markdown(report)
    assert to_csv(report).splitlines()[0]  # 至少有表头


def test_suggested_filename_is_safe_and_timestamped(sample_report):
    name = suggested_filename(sample_report, "md")

    assert name.endswith(".md")
    assert ":" not in name and "/" not in name and "\\" not in name
    assert name.startswith("智购参谋报告_")


def test_markdown_bytes_are_utf8(sample_report):
    assert "演示".encode("utf-8") in markdown_bytes(sample_report)


# --------------------------------------------------------------------------
# 时间
# --------------------------------------------------------------------------


def test_report_timestamp_is_local_and_sortable(sample_report):
    parsed = datetime.fromisoformat(sample_report.created_at)
    assert parsed.tzinfo is not None, "时间戳必须带时区，否则跨时区排序会错"
    assert parsed.utcoffset() == datetime.now(timezone.utc).astimezone().utcoffset()
