"""消费决策报告的组装与导出。

设计要点
--------
- **报告一经生成即固化**：`DecisionReport` 里存的是当时算出的分数与排序快照，
  不是指向商品的引用。历史报告再次打开时不会按当前数据重算——
  需求里明确要求「不覆盖历史结论」。
- **待核实项来自真实数据缺口**（缺字段、数据陈旧），不是泛泛的免责声明。
- 导出是纯字符串拼接，不依赖 Streamlit，因此可以脱离界面单测。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from src import config
from src.data_loader import Catalog, Product
from src.demand_parser import Demand
from src.recommender import RecommendationItem, RecommendationResult
from src.scoring import ScoreResult

#: 数据集超过这么多天就提示价格可能变化。
STALE_DAYS = 90


def now_local() -> datetime:
    """带本地时区的当前时间。本机应用，用本地时间比 UTC 更直观。"""
    return datetime.now().astimezone()


# --------------------------------------------------------------------------
# 报告数据结构
# --------------------------------------------------------------------------


@dataclass
class ReportItem:
    """报告里的一条商品记录——是**快照**，不引用当前商品数据。"""

    rank: int
    product_id: str
    name: str
    brand: str
    category_label: str
    price_label: str
    score_total: float
    match_level: str
    budget_label: str
    #: 推荐理由：来自各维度得分说明，可追溯到具体参数
    reasons: list[str] = field(default_factory=list)
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    data_source: str = ""
    updated_at: str = ""
    #: 该商品记录内部矛盾的说明（快照）。空列表表示没检测到矛盾。
    #: 有默认值，因此老的历史报告（JSON 里没有这一项）仍能正常打开。
    data_issues: list[str] = field(default_factory=list)

    @property
    def is_over_budget(self) -> bool:
        return self.budget_label.startswith("超出预算")


@dataclass
class DecisionReport:
    """一次完整的消费决策报告。"""

    created_at: str
    demand_summary: str
    #: 用户原始输入。只有展示用途，给默认值以便老记录也能打开。
    demand_text: str = ""
    #: 条件指纹。由**结构化条件**算出的稳定哈希，落库去重用：
    # 措辞不同但条件相同的两次分析视为同一组条件。
    signature: str = ""
    demand_facts: list[tuple[str, str]] = field(default_factory=list)
    filter_facts: list[tuple[str, str]] = field(default_factory=list)
    recommendations: list[ReportItem] = field(default_factory=list)
    over_budget: list[ReportItem] = field(default_factory=list)
    #: 预算内商品的**真实条数**（截断展示之前）。与 `over_budget_total` 对称。
    within_budget_total: int = 0
    #: 超出预算商品的**真实条数**（截断展示之前）。
    #: 报告是快照，条数也要固化——否则打开历史时要靠列表长度反推，
    #: 而截断之后那个长度已经不等于总数了。
    over_budget_total: int = 0
    relaxations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    to_verify: list[str] = field(default_factory=list)
    conclusion: str = ""
    dataset_disclaimer: str = ""

    @property
    def has_recommendations(self) -> bool:
        return bool(self.recommendations)

    def to_dict(self) -> dict:
        """转成可 JSON 序列化的结构，用于落库。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> DecisionReport:
        """从落库的结构还原。字段缺失时用默认值补齐，老记录也能打开。"""
        payload = dict(data)
        payload["recommendations"] = [
            ReportItem(**item) for item in payload.get("recommendations", [])
        ]
        payload["over_budget"] = [
            ReportItem(**item) for item in payload.get("over_budget", [])
        ]
        # JSON 里元组会变成列表，转回来以保持展示一致
        payload["demand_facts"] = [
            tuple(pair) for pair in payload.get("demand_facts", [])
        ]
        payload["filter_facts"] = [
            tuple(pair) for pair in payload.get("filter_facts", [])
        ]
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})


# --------------------------------------------------------------------------
# 组装
# --------------------------------------------------------------------------


def _to_report_item(
    item: RecommendationItem, score: ScoreResult, rank: int
) -> ReportItem:
    product = item.product
    # 推荐理由取各维度说明里得分较高的前三条——都带着具体数字和参数
    ordered = sorted(score.dimensions, key=lambda d: (-d.score, d.key))
    reasons = [f"{d.label}：{d.reason}" for d in ordered[:3]]

    return ReportItem(
        rank=rank,
        product_id=product.id,
        name=product.name or product.id,
        brand=product.brand,
        category_label=product.category_label,
        price_label=product.price_label,
        score_total=score.total,
        match_level=score.match_level,
        budget_label=item.budget_label,
        reasons=reasons,
        pros=list(product.pros),
        cons=list(product.cons),
        data_source=product.data_source,
        updated_at=product.updated_at,
        # 存疑说明一并写进快照：历史报告要能还原当时看到的东西，
        # 不能等到打开历史时才用「当前」的商品数据重算。
        data_issues=[issue.reason for issue in product.data_issues],
    )


def _demand_facts(demand: Demand) -> list[tuple[str, str]]:
    return [
        ("商品类别", demand.category_label or "未指定"),
        ("预算", demand.budget_label),
        ("使用场景", "、".join(demand.use_cases) or "未提供"),
        ("核心需求", "、".join(demand.core_needs) or "未提供"),
        ("品牌偏好", "、".join(demand.brand_preferences) or "未限定"),
        ("硬性限制", "、".join(demand.hard_constraints) or "无"),
        ("可妥协项", "、".join(demand.compromises) or "未说明"),
    ]


def demand_signature(demand: Demand) -> str:
    """把结构化条件揉成一个稳定指纹，历史去重用。

    两个刻意的设计：
    - **不含原始文本**。措辞不同但条件相同的两次输入
      （「预算4000买办公本」和「4000 元的学习笔记本」）是同一组条件，
      应该得到同一枚指纹——这正是 README「同一组条件重复提交
      只存一条」承诺的语义。
    - **列表先排序**。同一组条件条目顺序不同（先说学习后说编程）
      也算同一组条件。
    """
    canonical = {
        "category": demand.category or "",
        "budget": demand.budget,
        "use_cases": sorted(demand.use_cases),
        "core_needs": sorted(demand.core_needs),
        "compromises": sorted(demand.compromises),
        "brand_preferences": sorted(demand.brand_preferences),
        "hard_constraints": sorted(demand.hard_constraints),
    }
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _filter_facts(result: RecommendationResult) -> list[tuple[str, str]]:
    return [
        ("候选商品", f"{result.candidate_count} 件"),
        ("预算内", f"{result.within_budget_total} 件"),
        ("超出预算", f"{result.over_budget_total} 件"),
        ("排序依据", config.SCORE_DISPLAY_NAME),
    ]


def _days_since(value: str) -> int | None:
    """把 'YYYY-MM-DD' 转成距今天数。解析不了返回 None。"""
    try:
        then = date.fromisoformat(value.strip()[:10])
    except (ValueError, AttributeError):
        return None
    return (date.today() - then).days


def collect_verification_items(result: RecommendationResult, catalog: Catalog) -> list[str]:
    """列出**具体**需要核实的事项。

    只写真实存在的缺口：商品缺哪些字段、数据集多久没更新、演示数据本身
    不包含哪些维度。不写「投资有风险」这类放之四海皆准的空话。
    """
    items: list[str] = []

    # 1) 缺字段的商品
    incomplete = [p for p in _touched_products(result) if not p.is_complete]
    for product in incomplete:
        missing = "、".join(product.missing_fields)
        items.append(
            f"{product.name or product.id} 缺少「{missing}」，相关评分维度未参与计算，"
            f"建议向卖家或厂商确认这几项。"
        )

    # 2) 字段都在、但记录内部互相矛盾的商品
    #    与 1) 是两类问题：那里是「没说」，这里是「说岔了」。
    for product in _touched_products(result):
        issues = product.data_issues
        if not issues:
            continue
        detail = "；".join(issue.reason for issue in issues)
        items.append(
            f"{product.name or product.id} 的记录内部存在互相矛盾的地方（{detail}），"
            f"这几处描述建议以厂商或平台的实际信息为准，不要直接采信。"
        )

    # 3) 数据集时效
    days = _days_since(catalog.dataset_updated_at)
    if days is not None and days > STALE_DAYS:
        items.append(
            f"本数据集更新于 {catalog.dataset_updated_at}，距今约 {days} 天，"
            f"参考价格可能已经变化，下单前请以实际售价为准。"
        )

    # 4) 演示数据本身没有的维度——这是数据边界，不是免责套话
    items.append(
        "本次分析依据的数据不包含销量、真实用户评价、售后政策与保修信息。"
        "这些因素可能影响你的决定，建议另行核实。"
    )

    # 4) 超预算商品的价格尤其需要确认
    if result.over_budget:
        items.append(
            f"有 {result.over_budget_total} 件商品超出预算，"
            f"报价浮动会直接影响它们是否进入可选范围，建议确认当前实际价格。"
        )
        # 只列了一部分时说清楚——报告是拿去核对的东西，条数不能含糊
        hidden = result.over_budget_hidden
        if hidden:
            items.append(
                f"本报告只列出了其中按需求匹配度排序的前 {len(result.over_budget)} 件，"
                f"另有 {hidden} 件超出预算更多的商品未列出。"
            )

    # 5) 没有任何匹配时，说清是数据覆盖不到，而不是「不存在这样的商品」
    if not result.has_results:
        items.append(
            "当前没有任何商品满足条件。这只说明在本数据集的范围内没有匹配项，"
            "不代表市场上没有合适的产品。"
        )

    return items


def _touched_products(result: RecommendationResult) -> list[Product]:
    seen: dict[str, Product] = {}
    for item in result.all_items():
        seen.setdefault(item.product.id, item.product)
    return list(seen.values())


def _build_conclusion(result: RecommendationResult) -> str:
    """最终建议。没有推荐时如实说明，不编造结论。"""
    best = result.best
    if best is None:
        return (
            "在本次给出的条件下没有找到合适的商品，因此不给出推荐。"
            "可以参考前面的放宽建议调整条件后重新分析。"
        )

    product = best.product
    if not result.has_within_budget:
        return (
            f"预算内没有可选商品。全部候选中匹配度最高的是 {product.name}"
            f"（{config.SCORE_DISPLAY_NAME} {best.score.total:.0f} 分，"
            f"{best.budget_label}）。若预算可上浮，可优先考虑这一件；"
            f"否则建议按上面的放宽建议调整条件。"
        )

    tail = ""
    if best.score.match_level in {"匹配度较低", "基本可用"}:
        tail = (
            "需要说明的是，它的匹配评分并不高，说明本次条件与可用商品之间存在"
            "一定差距，建议一并看看放宽建议。"
        )
    elif result.over_budget and (
        result.over_budget[0].score.total > best.score.total
    ):
        higher = result.over_budget[0]
        tail = (
            f"另外，超预算的 {higher.product.name} 匹配评分更高"
            f"（{higher.score.total:.0f} 分，{higher.budget_label}），"
            f"如果预算能上浮可以考虑。"
        )

    return (
        f"综合本次条件，建议优先考虑 {product.name}"
        f"（参考价 {product.price_label}，{config.SCORE_DISPLAY_NAME} "
        f"{best.score.total:.0f} 分，{best.score.match_level}）。"
        f"{tail}"
    )


def build_report(
    catalog: Catalog,
    demand: Demand,
    result: RecommendationResult,
    *,
    created_at: datetime | None = None,
) -> DecisionReport:
    """把一次分析组装成报告。

    报告一旦生成就固化了当时的分数与排序，后续商品数据变化不会影响它。
    """
    moment = created_at or now_local()

    recommendations = [
        _to_report_item(item, item.score, rank)
        for rank, item in enumerate(result.within_budget, start=1)
    ]
    over_budget = [
        _to_report_item(item, item.score, rank)
        for rank, item in enumerate(result.over_budget, start=1)
    ]

    return DecisionReport(
        created_at=moment.isoformat(timespec="seconds"),
        demand_summary=demand.summary_line(),
        demand_text=demand.raw_text,
        signature=demand_signature(demand),
        demand_facts=_demand_facts(demand),
        filter_facts=_filter_facts(result),
        recommendations=recommendations,
        over_budget=over_budget,
        within_budget_total=result.within_budget_total,
        over_budget_total=result.over_budget_total,
        relaxations=list(result.relaxations),
        notes=list(result.notes),
        to_verify=collect_verification_items(result, catalog),
        conclusion=_build_conclusion(result),
        dataset_disclaimer=catalog.disclaimer,
    )


# --------------------------------------------------------------------------
# 导出
# --------------------------------------------------------------------------


def _kv_lines(pairs: list[tuple[str, str]]) -> list[str]:
    return [f"- **{key}**：{value}" for key, value in pairs]


def _item_block(item: ReportItem, *, show_rank: bool = True) -> list[str]:
    heading = f"### {item.rank}. {item.name}" if show_rank else f"### {item.name}"
    lines = [
        heading,
        "",
        f"- 品牌：{item.brand or '未知'}　·　类别：{item.category_label}",
        f"- 参考价格：{item.price_label}　·　{item.budget_label}",
        f"- {config.SCORE_DISPLAY_NAME}：{item.score_total:.0f} / 100（{item.match_level}）",
    ]
    if item.reasons:
        lines.append("- 推荐理由：")
        lines.extend(f"    - {reason}" for reason in item.reasons)
    if item.pros:
        lines.append("- 优点：")
        lines.extend(f"    - {pro}" for pro in item.pros)
    if item.cons:
        lines.append("- 缺点：")
        lines.extend(f"    - {con}" for con in item.cons)
    if item.data_issues:
        lines.append("- ⚠️ **资料存疑**（以下几处记录内部互相矛盾，建议核实后再采信）：")
        lines.extend(f"    - {issue}" for issue in item.data_issues)
    lines.append(f"- 数据来源：{item.data_source or '信息缺失'}（更新于 {item.updated_at or '未知'}）")
    lines.append("")
    return lines


def to_markdown(report: DecisionReport) -> str:
    """导出为 Markdown。内容与界面一致，且保留演示数据来源标注。"""
    lines: list[str] = [
        "# 智购参谋 · 消费决策报告",
        "",
        f"生成时间：{report.created_at}",
        "",
        "## 一、需求摘要",
        "",
        f"{report.demand_summary}",
        "",
        *_kv_lines(report.demand_facts),
        "",
        "## 二、预算与筛选条件",
        "",
        *_kv_lines(report.filter_facts),
        "",
    ]

    # 八个部分**始终**输出。内容为空时写「无」，而不是让整节消失——
    # 报告格式固定，读者每次拿到的结构一致，也便于和规格逐条对照。
    lines += ["## 三、推荐商品及排序", ""]
    if report.recommendations:
        for item in report.recommendations:
            lines += _item_block(item)
    else:
        lines += ["在本次条件下没有预算内的匹配商品，因此没有推荐条目。", ""]

    lines += ["## 四、超出预算的候选", ""]
    if report.over_budget:
        lines += ["以下商品超出预算，不计入上面的推荐排序。", ""]
        for item in report.over_budget:
            lines += _item_block(item, show_rank=False)
    else:
        lines += ["无。", ""]

    lines += ["## 五、放宽条件的建议", ""]
    lines += [f"- {tip}" for tip in report.relaxations] if report.relaxations else ["无。"]
    lines.append("")

    lines += ["## 六、分析过程说明", ""]
    lines += [f"- {note}" for note in report.notes] if report.notes else ["无。"]
    lines.append("")

    lines += ["## 七、需要进一步核实的信息", ""]
    lines += [f"- {item}" for item in report.to_verify] if report.to_verify else ["无。"]
    lines.append("")

    lines += ["## 八、最终决策建议", "", report.conclusion, ""]

    lines += [
        "---",
        "",
        "### 数据说明",
        "",
        report.dataset_disclaimer or "本次分析使用的数据集未附带说明。",
        "",
        f"「{config.SCORE_DISPLAY_NAME}」衡量的是商品与本次需求的匹配程度，"
        "不是用户评价、销量排名或市场口碑。",
        "",
        "本报告由智购参谋自动生成，仅供决策参考。",
    ]
    return "\n".join(lines)


def to_csv(report: DecisionReport) -> str:
    """导出为 CSV。一行一件商品，含得分、价格与预算匹配状态。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "分区",
            "序号",
            "商品ID",
            "商品名称",
            "品牌",
            "类别",
            "参考价格",
            "预算匹配",
            f"{config.SCORE_DISPLAY_NAME}",
            "匹配档位",
            "优点",
            "缺点",
            "数据来源",
            "数据更新时间",
            "资料存疑",
        ]
    )

    for zone, items in (("预算内推荐", report.recommendations), ("超出预算", report.over_budget)):
        for item in items:
            writer.writerow(
                [
                    zone,
                    item.rank,
                    item.product_id,
                    item.name,
                    item.brand,
                    item.category_label,
                    item.price_label,
                    item.budget_label,
                    f"{item.score_total:.0f}",
                    item.match_level,
                    "；".join(item.pros),
                    "；".join(item.cons),
                    item.data_source,
                    item.updated_at,
                    "；".join(item.data_issues),
                ]
            )

    # CSV 用 utf-8-sig 写文件才能被 Excel 正确识别中文——这里加 BOM 提示调用方
    return buffer.getvalue()


def csv_bytes(report: DecisionReport) -> bytes:
    """CSV 的字节形式，带 BOM。

    不带 BOM 的话 Excel 打开中文会乱码，用户会以为是导出坏了。
    """
    return b"\xef\xbb\xbf" + to_csv(report).encode("utf-8")


def markdown_bytes(report: DecisionReport) -> bytes:
    return to_markdown(report).encode("utf-8")


def suggested_filename(report: DecisionReport, suffix: str) -> str:
    """生成导出文件名，例如 `智购参谋报告_20261012_2130.md`。"""
    stamp = report.created_at.replace("-", "").replace(":", "").replace("T", "_")[:15]
    return f"智购参谋报告_{stamp}.{suffix}"
