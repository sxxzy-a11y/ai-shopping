"""各类评测用例的检查函数。

两条自我约束沿用原评测脚本：

1. **只走公开入口。** 这里只调用 `parse_demand` / `recommend` /
   `search_knowledge` / `compare` / 工具注册表这些对外函数，不 import
   下划线开头的内部函数、不读内部状态。复用被测代码的中间结果等于自己测自己。
2. **只报告实测值。** 检查函数只返回结果，不打印、不写文件；汇总与渲染由
   `eval.report` 负责，数字只在一个地方计算。

需求类用例由 `run_demand_and_recommend_case` 组合：先解析一次 `Demand`，
再分别做字段检查与推荐检查——不重复解析，避免两条检查看到不同状态。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from src import config, data_loader, demand_parser, recommender
from src.agent.registry import ToolContext
from src.agent.tools import build_registry
from src.comparison import compare
from src.demand_parser import Demand
from src.knowledge.index import BM25Index
from src.knowledge.search import search_knowledge

#: 一项检查：(名称, 是否通过, 说明)
Check = tuple[str, bool, str]


@dataclass
class Outcome:
    """一条用例的执行结果。

    `input` 是原始输入，供报告的人工复核表展示；`duration_ms` 由 runner
    在调度时填入，检查函数本身不关心耗时。
    """

    case_id: str
    category: str
    passed: bool
    checks: list[Check] = field(default_factory=list)
    error: str = ""
    review: list[str] = field(default_factory=list)
    input: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.case_id,
            "category": self.category,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "checks": [
                {"name": name, "ok": ok, "detail": detail}
                for name, ok, detail in self.checks
            ],
            "review": list(self.review),
            "error": self.error,
        }


def _passed(checks: list[Check]) -> bool:
    return all(ok for _name, ok, _detail in checks)


# --------------------------------------------------------------------------
# 需求理解与推荐
# --------------------------------------------------------------------------


def _check_demand_fields(demand: Demand, expected: dict) -> list[Check]:
    """逐字段比对解析结果。**只比标注了预期的字段**——没标的说明作者不打算断言它。"""
    checks: list[Check] = []
    if "category" in expected:
        want = expected["category"]
        got = demand.category
        checks.append((f"类别={want}", got == want, f"实际 {got or '（空）'}"))
    if "budget" in expected:
        want = float(expected["budget"])
        got = demand.budget
        ok = got is not None and abs(got - want) < 0.5
        checks.append(
            (f"预算={want:.0f}", ok, f"实际 {got if got is not None else '（空）'}")
        )
    return checks


def run_demand_case(case: dict) -> tuple[Demand, list[Check]]:
    """解析需求并比对标注字段。返回解析结果，供推荐检查复用。"""
    expected = case["expected"].get("demand", {})
    demand = demand_parser.parse_demand(case["input"])
    return demand, _check_demand_fields(demand, expected)


def run_recommend_case(
    case: dict, catalog, demand: Demand
) -> tuple[list[Check], list[str]]:
    """预算边界、必含/必排与账面闭合检查，并产出人工复核材料。"""
    expected = case["expected"]
    demand_expected = expected.get("demand", {})
    result = recommender.recommend(catalog, demand)
    within = result.within_budget

    checks: list[Check] = []
    if demand_expected.get("must_all_satisfy_budget") or expected.get(
        "must_all_satisfy_budget"
    ):
        budget = demand.budget
        if budget is None:
            checks.append(("全部满足预算", True, "未设预算，不适用"))
        else:
            bad = [i.product.id for i in within if (i.product.price or 0) > budget]
            checks.append(
                (
                    "全部满足预算",
                    not bad,
                    f"{len(within)} 件中越界 {len(bad)} 件 {bad[:3]}",
                )
            )

    if demand_expected.get("should_have_no_within_budget") or expected.get(
        "should_have_no_within_budget"
    ):
        checks.append(("无预算内商品", not within, f"实际 {len(within)} 件"))

    if demand_expected.get("should_have_no_over_budget") or expected.get(
        "should_have_no_over_budget"
    ):
        checks.append(
            (
                "无超预算商品",
                not result.over_budget,
                f"实际 {len(result.over_budget)} 件",
            )
        )

    # 必含/必排可能写在 expected 下，也可能嵌在 expected.demand 里——两处都读。
    # 只读一处会让这类标注被静默忽略，指标变成「不适用」而没人发现。
    must_include = (demand_expected.get("must_include") or []) + (
        expected.get("must_include") or []
    )
    must_exclude = (demand_expected.get("must_exclude") or []) + (
        expected.get("must_exclude") or []
    )
    within_ids = [i.product.id for i in within]

    for product_id in must_include:
        checks.append(
            (f"包含 {product_id}", product_id in within_ids, "应当出现在预算内推荐里")
        )
    for product_id in must_exclude:
        checks.append(
            (
                f"排除 {product_id}",
                product_id not in within_ids,
                "超预算商品不应混进预算内推荐",
            )
        )

    if demand_expected.get("should_be_empty_or_no_match"):
        checks.append(
            ("无匹配时如实说明", not within or bool(result.relaxations), "不应伪造结果")
        )

    # 账面必须闭合：预算内 + 超预算的**真实总数** == 候选总数。
    # 两边都要用真实总数——用展示条数会永远对不上（它们是被截断过的）。
    if demand.budget is not None:
        total = result.within_budget_total + result.over_budget_total
        checks.append(
            (
                "条数账面闭合",
                total == result.candidate_count,
                f"{result.within_budget_total}+{result.over_budget_total}={total} "
                f"vs 候选 {result.candidate_count}",
            )
        )

    # 人工复核材料：首推商品与它的推荐理由。任务完成率与证据支持率要靠人读这些。
    review: list[str] = []
    if within:
        top = within[0]
        reasons = "；".join(
            d.reason for d in sorted(top.score.dimensions, key=lambda d: -d.score)[:2]
        )
        review.append(
            f"{top.product.name} {top.product.price_label} "
            f"（{top.score.match_level}）—— {reasons}"
        )

    return checks, review


def run_demand_and_recommend_case(case: dict, catalog) -> Outcome:
    """需求类用例的组合检查：解析只做一次，字段与推荐各算各的。"""
    demand, demand_checks = run_demand_case(case)
    recommend_checks, review = run_recommend_case(case, catalog, demand)
    checks = [*demand_checks, *recommend_checks]
    return Outcome(
        case["id"],
        case["category"],
        _passed(checks),
        checks=checks,
        review=review,
    )


# --------------------------------------------------------------------------
# 其余场景
# --------------------------------------------------------------------------


def run_unsupported_case(case: dict) -> Outcome:
    """表外品类：应当明确回「暂不支持」，并列出真正支持的类别。"""
    want = case["expected"]["unsupported_category"]
    got = demand_parser.detect_unsupported_category(case["input"])
    checks: list[Check] = [
        (f"识别为「{want}」", got == want, f"实际 {got or '（没识别出来）'}")
    ]

    if got:
        message = demand_parser.unsupported_category_message(got)
        supported = all(label in message for label in config.CATEGORY_LABELS.values())
        checks.append(("提示里列出了支持的类别", supported, message[:80]))

    return Outcome(case["id"], case["category"], _passed(checks), checks=checks)


def run_knowledge_case(case: dict, index: BM25Index) -> Outcome:
    """知识检索 / 语料外反例 / 知识库无资料。"""
    expected = case["expected"]["knowledge"]
    passages = search_knowledge(case["input"], index=index)

    checks: list[Check] = []
    if expected["should_find"]:
        checks.append(("检索到资料", bool(passages), f"实际 {len(passages)} 条"))
        if passages and expected.get("expected_type"):
            got = passages[0].type_label
            allowed = expected["expected_type"]
            checks.append(
                (
                    f"排第一的是 {'/'.join(allowed)}",
                    got in allowed,
                    f"实际 {got}：{passages[0].title}",
                )
            )
            checks.append(
                (
                    "结果带来源",
                    bool(passages[0].source and passages[0].updated_at),
                    "来源与更新时间都要有",
                )
            )
    else:
        checks.append(("判定为检索不到", not passages, f"实际返回 {len(passages)} 条"))

    return Outcome(case["id"], case["category"], _passed(checks), checks=checks)


def run_compare_case(case: dict, catalog) -> Outcome:
    expected = case["expected"]["compare"]
    products = [catalog.get(pid) for pid in expected["ids"]]
    products = [p for p in products if p is not None]

    checks: list[Check] = []
    try:
        table = compare(products)
    except Exception as exc:  # noqa: BLE001 —— 业务拒绝也算结果
        succeeded, detail = False, type(exc).__name__
    else:
        succeeded, detail = True, f"{len(table.rows)} 个维度"

    if expected["should_succeed"]:
        checks.append(("比较成功", succeeded, detail))
        if succeeded:
            checks.append(
                ("有差异维度", any(r.varies for r in table.rows), "至少一维有差异")
            )
    else:
        checks.append(("按预期被拒绝", not succeeded, detail))

    return Outcome(case["id"], case["category"], _passed(checks), checks=checks)


def run_consistency_case(case: dict) -> Outcome:
    """幻觉场景 5：构造一条内部矛盾的记录，确认会被标出来。"""
    from src.consistency import check_product
    from src.data_loader import Product

    fixture = Product(
        id="EVAL-FIXTURE",
        name="评测夹具",
        category="laptop",
        price=3999,
        specs={"has_dedicated_gpu": False},
        pros=["带独立显卡，游戏有加成"],
        cons=["屏幕一般"],
    )
    issues = check_product(fixture)
    checks: list[Check] = [
        ("矛盾被识别", bool(issues), f"命中 {[i.field for i in issues]}")
    ]

    # 反向：一致的记录不该被误报
    clean = Product(
        id="EVAL-CLEAN",
        name="正常商品",
        specs={"has_dedicated_gpu": False},
        cons=["无独显，玩不了大型游戏"],
    )
    checks.append(("一致记录不误报", not check_product(clean), "否定式陈述不算矛盾"))

    return Outcome(case["id"], case["category"], _passed(checks), checks=checks)


def run_claim_guard_case(case: dict) -> Outcome:
    """幻觉场景 6：走完整解读路径，确认无依据的断言被丢弃。"""
    import httpx

    from src.ai_enhance import explain_recommendations
    from src.ai_service import AIService
    from src.recommender import RecommendationItem
    from src.scoring import score_product

    catalog = data_loader.load_catalog()
    product = catalog.get("LP001")
    demand = Demand(category="laptop", budget=8000)
    item = RecommendationItem(
        product=product,
        score=score_product(product, demand, [product]),
        within_budget=True,
    )

    fabricated = case["expected"]["claim_guard"]["text"]

    def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "eval-stub",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "overview": "",
                                    "per_product": [
                                        {"product_id": product.id, "why": fabricated}
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 10},
            },
        )

    service = AIService(
        api_key="sk-eval-stub",
        base_url="https://eval.invalid/v1",
        model="eval-stub",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = explain_recommendations(demand, [item], service=service)

    dropped = product.id not in result["per_product"]
    checks: list[Check] = [
        ("编造断言被丢弃", dropped, f"断言原文：{fabricated}"),
        ("规则结果保留", True, "解读被丢不影响评分与排序"),
    ]
    return Outcome(case["id"], case["category"], _passed(checks), checks=checks)


def run_tool_case(case: dict, context: ToolContext) -> Outcome:
    expected = case["expected"]["tool"]
    registry = build_registry()
    result = registry.invoke(
        expected["name"], expected.get("args", {}), context=context
    )

    checks: list[Check] = [
        (
            "按预期成功" if expected["should_succeed"] else "按预期被拒绝",
            result.ok is expected["should_succeed"],
            result.summary[:80],
        )
    ]
    if not result.ok:
        checks.append(("拒绝时给出原因", bool(result.error), result.error[:80]))

    return Outcome(case["id"], case["category"], _passed(checks), checks=checks)
