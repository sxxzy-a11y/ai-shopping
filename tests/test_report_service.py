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
    demand_signature,
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


# --------------------------------------------------------------------------
# 导出失败（spec：导出失败时给出提示，不暴露堆栈）
# --------------------------------------------------------------------------


def test_export_error_carries_a_chinese_message():
    """导出失败走领域异常，界面只显示中文提示。"""
    from src.errors import ExportError, to_user_message

    error = ExportError(detail="PermissionError: [WinError 5] 拒绝访问")
    message = to_user_message(error)

    assert message == "导出失败，请检查目标位置是否可写后重试。"
    assert "WinError" not in message
    assert "PermissionError" not in message
    assert error.detail, "原始信息保留在 detail 里，供日志使用"


def test_export_helpers_never_touch_the_filesystem(sample_report):
    """导出函数只产出字节，不落盘。

    正因为不直接写文件，才没有「目标目录不可写」这条失败路径——
    真正的写入由浏览器下载完成，失败由浏览器提示。
    这条测试把这个设计约束固定下来。
    """
    import inspect

    from src import report_service

    for func in (report_service.markdown_bytes, report_service.csv_bytes,
                 report_service.to_markdown, report_service.to_csv):
        source = inspect.getsource(func)
        for banned in ("open(", "write_bytes", "write_text", "Path("):
            assert banned not in source, f"{func.__name__} 里出现了文件操作：{banned}"


# --------------------------------------------------------------------------
# 条件指纹（历史去重的依据）
# --------------------------------------------------------------------------


def test_demand_signature_ignores_raw_text():
    """措辞不同但条件相同 → 同一枚指纹。

    这是「同一组条件重复提交只存一条」承诺的前提：签名只能由
    结构化条件决定，不能被原始文本的表达方式带偏。
    """
    a = Demand(raw_text="预算4000买一台办公本", category="laptop", budget=4000)
    b = Demand(raw_text="4000 元的学习笔记本", category="laptop", budget=4000)

    assert demand_signature(a) == demand_signature(b)


def test_demand_signature_ignores_list_order():
    """同组条件条目顺序不同 → 同一枚指纹。"""
    a = Demand(category="laptop", budget=4000, use_cases=["编程", "学习"])
    b = Demand(category="laptop", budget=4000, use_cases=["学习", "编程"])

    assert demand_signature(a) == demand_signature(b)


def test_demand_signature_tracks_every_condition():
    """任一结构化条件变化都会改变指纹——去重不能把不同条件混成一条。"""
    base = Demand(category="laptop", budget=4000, use_cases=["编程"])

    variants = [
        base.model_copy(update={"budget": 4500}),
        base.model_copy(update={"category": "headphone"}),
        base.model_copy(update={"core_needs": ["续航"]}),
        base.model_copy(update={"brand_preferences": ["简一"]}),
        base.model_copy(update={"hard_constraints": ["必须静音"]}),
        base.model_copy(update={"compromises": ["可以重一点"]}),
    ]

    signatures = {demand_signature(base)} | {demand_signature(v) for v in variants}
    assert len(signatures) == len(variants) + 1, "不同条件撞出了同一枚指纹"


def test_built_report_carries_signature(catalog, laptop_demand):
    """build_report 组装报告时固化条件指纹，落库时由 save_analysis 读取。"""
    report = build_report(catalog, laptop_demand, recommend(catalog, laptop_demand))

    assert report.signature
    assert report.signature == demand_signature(laptop_demand)


# --------------------------------------------------------------------------
# 「资料存疑」标记（字段都在、但记录内部矛盾）
# --------------------------------------------------------------------------


@pytest.fixture
def flagged_product() -> Product:
    """一条内部矛盾的笔记本：「屏幕一般」同时出现在优点和缺点里。"""
    return Product(
        id="FLAG1",
        name="存疑笔记本",
        category="laptop",
        price=3999,
        brand="测试品牌",
        specs={"cpu_tier": 3},
        use_cases=["办公"],
        pros=["续航长", "屏幕一般"],
        cons=["屏幕一般"],
        data_source="演示数据",
        updated_at="2026-10-01",
    )


@pytest.fixture
def flagged_report(flagged_product, laptop_demand) -> DecisionReport:
    catalog = Catalog(products=[flagged_product])
    demand = laptop_demand.model_copy(update={"budget": 5000})
    result = recommend(catalog, demand)
    assert [item.product.id for item in result.within_budget] == ["FLAG1"]
    return build_report(catalog, demand, result)


def test_flagged_product_still_recommended(flagged_report):
    """存疑商品照常出现在推荐里——标记不是排除。

    标记若导致商品消失，就会诱使后来者「删数据解决校验」。
    """
    assert [item.product_id for item in flagged_report.recommendations] == ["FLAG1"]


def test_data_issue_listed_in_verification_items(flagged_report):
    """待核实清单里要说清楚**为什么**存疑，而不是只给一个标签。"""
    joined = "\n".join(flagged_report.to_verify)
    assert "存疑笔记本" in joined
    assert "互相矛盾" in joined
    assert "屏幕一般" in joined


def test_data_issue_appears_in_markdown(flagged_report):
    markdown = to_markdown(flagged_report)
    assert "资料存疑" in markdown
    assert "屏幕一般" in markdown


def test_data_issue_gets_its_own_csv_column(flagged_report):
    rows = list(csv.reader(io.StringIO(to_csv(flagged_report))))
    header, first = rows[0], rows[1]
    assert "资料存疑" in header

    cell = first[header.index("资料存疑")]
    assert "屏幕一般" in cell


def test_clean_product_leaves_the_csv_column_empty(sample_report):
    """没有矛盾的商品，该列为空——不能因为多了个字段就写占位文字。"""
    rows = list(csv.reader(io.StringIO(to_csv(sample_report))))
    header = rows[0]
    index = header.index("资料存疑")
    assert all(row[index] == "" for row in rows[1:])


def test_data_issue_survives_snapshot_round_trip(flagged_report):
    """报告是快照：重新打开历史记录时，存疑说明要原样还原。

    不能等到打开历史时才用「当前」商品数据重算——那时数据可能已经变了。
    """
    restored = DecisionReport.from_dict(flagged_report.to_dict())
    issues = restored.recommendations[0].data_issues
    assert issues
    assert "屏幕一般" in issues[0]


def test_old_report_without_the_field_still_opens(flagged_report):
    """老的历史报告 JSON 里没有这个字段，也要能正常打开（向前兼容）。"""
    payload = flagged_report.to_dict()
    for item in payload["recommendations"]:
        item.pop("data_issues")

    restored = DecisionReport.from_dict(payload)
    assert restored.recommendations[0].data_issues == []


# --------------------------------------------------------------------------
# 报告不承载 AI 解读
# --------------------------------------------------------------------------


def test_report_carries_no_ai_generated_field(catalog, laptop_demand):
    """报告是**规则算出的快照**，不承载任何 AI 解读文字。

    AI 文字若进了报告，「同一条历史记录每次打开都不一样」就会发生——
    模型换了、超时了、某条解读被断言校验丢弃了，历史结论都会跟着变。
    这条断言把报告的字段集锁死：新增字段必须是有意的决定。
    """
    report = build_report(catalog, laptop_demand, recommend(catalog, laptop_demand))

    assert set(report.to_dict()) == {
        "created_at",
        "demand_summary",
        "demand_text",
        "signature",
        "demand_facts",
        "filter_facts",
        "recommendations",
        "over_budget",
        # 超预算商品的真实条数（截断展示之前）。加它是有意的：
        # 快照要能自证「当时一共几件超预算」，不能靠列表长度反推。
        "over_budget_total",
        "relaxations",
        "notes",
        "to_verify",
        "conclusion",
        "dataset_disclaimer",
    }


def test_report_item_carries_no_ai_note_field(catalog, laptop_demand):
    """同理，商品条目里也没有放 AI 解读的位置。"""
    report = build_report(catalog, laptop_demand, recommend(catalog, laptop_demand))
    item = report.to_dict()["recommendations"][0]

    assert "ai_note" not in item
    assert "why" not in item
    assert "overview" not in item


# --------------------------------------------------------------------------
# 超预算条数如实展示（变更 fix-over-budget-count）
# --------------------------------------------------------------------------


@pytest.fixture
def truncated_report(catalog):
    """预算压到很低，超预算候选多到被截断。"""
    demand = Demand(category="headphone", budget=100)
    result = recommend(catalog, demand)
    assert result.over_budget_hidden > 0, "夹具没有产生截断"
    return build_report(catalog, demand, result)


def test_filter_facts_use_the_real_total(truncated_report):
    facts = dict(truncated_report.filter_facts)
    assert facts["超出预算"] == f"{truncated_report.over_budget_total} 件"
    assert truncated_report.over_budget_total > len(truncated_report.over_budget)


def test_verification_items_disclose_what_is_hidden(truncated_report):
    joined = "\n".join(truncated_report.to_verify)
    assert "未列出" in joined
    assert str(truncated_report.over_budget_total) in joined


def test_markdown_export_carries_the_disclosure(truncated_report):
    markdown = to_markdown(truncated_report)
    assert "未列出" in markdown
    assert str(truncated_report.over_budget_total) in markdown


def test_report_without_truncation_has_no_extra_note(catalog):
    demand = Demand(category="headphone", budget=500)
    report = build_report(catalog, demand, recommend(catalog, demand))
    assert "未列出" not in "\n".join(report.to_verify)


def test_old_report_without_over_budget_total_still_opens(catalog):
    """老快照没有 over_budget_total，反序列化时取默认值。"""
    demand = Demand(category="headphone", budget=500)
    payload = build_report(catalog, demand, recommend(catalog, demand)).to_dict()
    payload.pop("over_budget_total", None)

    restored = DecisionReport.from_dict(payload)
    assert restored.over_budget_total == 0
