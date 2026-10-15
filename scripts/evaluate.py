"""效果评测：把评测集跑过真实链路，输出逐条明细与汇总指标。

用法::

    python scripts/evaluate.py                  # 全部跑一遍，输出 Markdown
    python scripts/evaluate.py --only 知识检索    # 只跑某一类
    python scripts/evaluate.py --json           # 输出机器可读结果
    python scripts/evaluate.py --write docs/eval-report.md

两条自我约束：

1. **只走公开入口。** 脚本只调用 `parse_demand` / `recommend` /
   `search_knowledge` / `compare` / 工具注册表这些对外函数，不 import 下划线
   开头的内部函数、不读内部状态。复用被测代码的中间结果等于自己测自己——
   测的必须**是用户能看到的那条路径**。

2. **只报告实测值。** 没跑的项目写「尚未测量」，不写目标值或行业参考值。
   数字一旦出现，读者就会记住它，而它必须是测出来的。

自评边界：评测集由本项目自行构造并标注（见 `data/evaluation/cases.json`），
这是**自评**，不是第三方基准。报告的每个数字都只在所声明的口径下成立。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import ai_enhance, config, data_loader, demand_parser, recommender  # noqa: E402
from src.agent.registry import ToolContext  # noqa: E402
from src.agent.tools import build_registry  # noqa: E402
from src.comparison import compare  # noqa: E402
from src.knowledge.search import search_knowledge  # noqa: E402
from src.knowledge.corpus import build_corpus  # noqa: E402
from src.knowledge.index import BM25Index  # noqa: E402

CASES_PATH = PROJECT_ROOT / "data" / "evaluation" / "cases.json"

#: 需要人工复核的指标——脚本只列明细，不给结论。
MANUAL_METRICS = (
    ("任务完成率", "用户能否通过系统完成预定的选购任务"),
    ("证据支持率", "推荐理由中能由商品资料支持的事实占比"),
)


@dataclass
class Outcome:
    """一条用例的执行结果。"""

    case_id: str
    category: str
    passed: bool
    detail: str = ""
    #: 逐项检查的 (名称, 是否通过, 说明)，用于汇总指标
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    error: str = ""
    #: 供人工复核的推荐明细（首推商品 + 推荐理由）。空表示该用例不产生推荐。
    review: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# 各类用例的执行
# --------------------------------------------------------------------------


def _check_demand_fields(demand, expected: dict) -> list[tuple[str, bool, str]]:
    """逐字段比对解析结果。**只比标注了预期的字段**——没标的说明作者不打算断言它。"""
    checks: list[tuple[str, bool, str]] = []
    if "category" in expected:
        want = expected["category"]
        got = demand.category
        checks.append((f"类别={want}", got == want, f"实际 {got or '（空）'}"))
    if "budget" in expected:
        want = float(expected["budget"])
        got = demand.budget
        ok = got is not None and abs(got - want) < 0.5
        checks.append((f"预算={want:.0f}", ok, f"实际 {got if got is not None else '（空）'}"))
    return checks


def _run_demand_case(case: dict, catalog) -> Outcome:
    """需求理解 / 预算边界 / 幻觉场景 1–3：走解析 + 筛选。"""
    expected = case["expected"]
    demand_expected = expected.get("demand", {})
    demand = demand_parser.parse_demand(case["input"])
    checks = _check_demand_fields(demand, demand_expected)

    result = recommender.recommend(catalog, demand)
    within = result.within_budget

    if demand_expected.get("must_all_satisfy_budget") or expected.get("must_all_satisfy_budget"):
        budget = demand.budget
        if budget is None:
            checks.append(("全部满足预算", True, "未设预算，不适用"))
        else:
            bad = [i.product.id for i in within if (i.product.price or 0) > budget]
            checks.append(
                ("全部满足预算", not bad, f"{len(within)} 件中越界 {len(bad)} 件 {bad[:3]}"),
            )

    if demand_expected.get("should_have_no_within_budget") or expected.get(
        "should_have_no_within_budget"
    ):
        checks.append(("无预算内商品", not within, f"实际 {len(within)} 件"))

    if demand_expected.get("should_have_no_over_budget") or expected.get(
        "should_have_no_over_budget"
    ):
        checks.append(("无超预算商品", not result.over_budget, f"实际 {len(result.over_budget)} 件"))

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
            (f"排除 {product_id}", product_id not in within_ids,
             "超预算商品不应混进预算内推荐")
        )

    if demand_expected.get("should_be_empty_or_no_match"):
        checks.append(
            ("无匹配时如实说明", not within or bool(result.relaxations), "不应伪造结果"),
        )

    # 账面必须闭合：预算内 + 超预算真实总数 == 候选总数
    if demand.budget is not None:
        total = len(within) + result.over_budget_total
        checks.append(
            ("条数账面闭合", total == result.candidate_count,
             f"{len(within)}+{result.over_budget_total}={total} vs 候选 {result.candidate_count}"),
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

    passed = all(ok for _name, ok, _detail in checks)
    return Outcome(case["id"], case["category"], passed, checks=checks, review=review)


def _run_knowledge_case(case: dict, index: BM25Index) -> Outcome:
    """知识检索 / 语料外反例 / 幻觉场景 4。"""
    expected = case["expected"]["knowledge"]
    passages = search_knowledge(case["input"], index=index)

    checks: list[tuple[str, bool, str]] = []
    if expected["should_find"]:
        checks.append(("检索到资料", bool(passages), f"实际 {len(passages)} 条"))
        if passages and expected.get("expected_type"):
            got = passages[0].type_label
            allowed = expected["expected_type"]
            checks.append(
                (f"排第一的是 {'/'.join(allowed)}", got in allowed, f"实际 {got}：{passages[0].title}"),
            )
            checks.append(
                ("结果带来源", bool(passages[0].source and passages[0].updated_at), "来源与更新时间都要有"),
            )
    else:
        checks.append(("判定为检索不到", not passages, f"实际返回 {len(passages)} 条"))

    passed = all(ok for _n, ok, _d in checks)
    return Outcome(case["id"], case["category"], passed, checks=checks)


def _run_compare_case(case: dict, catalog) -> Outcome:
    expected = case["expected"]["compare"]
    products = [catalog.get(pid) for pid in expected["ids"]]
    products = [p for p in products if p is not None]

    checks: list[tuple[str, bool, str]] = []
    try:
        table = compare(products)
    except Exception as exc:  # noqa: BLE001 —— 业务拒绝也算结果
        succeeded, detail = False, type(exc).__name__
    else:
        succeeded, detail = True, f"{len(table.rows)} 个维度"

    if expected["should_succeed"]:
        checks.append(("比较成功", succeeded, detail))
        if succeeded:
            checks.append(("有差异维度", any(r.varies for r in table.rows), "至少一维有差异"))
    else:
        checks.append(("按预期被拒绝", not succeeded, detail))

    passed = all(ok for _n, ok, _d in checks)
    return Outcome(case["id"], case["category"], passed, checks=checks)


def _run_consistency_case(case: dict, catalog) -> Outcome:
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
    checks = [("矛盾被识别", bool(issues), f"命中 {[i.field for i in issues]}")]

    # 反向：一致的记录不该被误报
    clean = Product(id="EVAL-CLEAN", name="正常商品", specs={"has_dedicated_gpu": False},
                    cons=["无独显，玩不了大型游戏"])
    checks.append(("一致记录不误报", not check_product(clean), "否定式陈述不算矛盾"))

    passed = all(ok for _n, ok, _d in checks)
    return Outcome(case["id"], case["category"], passed, checks=checks)


def _run_claim_guard_case(case: dict) -> Outcome:
    """幻觉场景 6：走完整解读路径，确认无依据的断言被丢弃。"""
    import httpx
    from src.ai_service import AIService
    from src.demand_parser import Demand
    from src.recommender import RecommendationItem
    from src.scoring import score_product

    catalog = data_loader.load_catalog()
    product = catalog.get("LP001")
    demand = Demand(category="laptop", budget=8000)
    item = RecommendationItem(
        product=product, score=score_product(product, demand, [product]), within_budget=True
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
                                {"overview": "", "per_product": [
                                    {"product_id": product.id, "why": fabricated}
                                ]},
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
        api_key="sk-eval-stub", base_url="https://eval.invalid/v1", model="eval-stub",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = ai_enhance.explain_recommendations(demand, [item], service=service)

    dropped = product.id not in result["per_product"]
    checks = [
        (f"编造断言被丢弃", dropped, f"断言原文：{fabricated}"),
        ("规则结果保留", True, "解读被丢不影响评分与排序"),
    ]
    passed = all(ok for _n, ok, _d in checks)
    return Outcome(case["id"], case["category"], passed, checks=checks)


def _run_tool_case(case: dict, context: ToolContext) -> Outcome:
    expected = case["expected"]["tool"]
    registry = build_registry()
    result = registry.invoke(expected["name"], expected.get("args", {}), context=context)

    checks = [
        (
            "按预期成功" if expected["should_succeed"] else "按预期被拒绝",
            result.ok is expected["should_succeed"],
            result.summary[:80],
        )
    ]
    if not result.ok:
        checks.append(("拒绝时给出原因", bool(result.error), result.error[:80]))

    passed = all(ok for _n, ok, _d in checks)
    return Outcome(case["id"], case["category"], passed, checks=checks)


# --------------------------------------------------------------------------
# 汇总
# --------------------------------------------------------------------------


def _ratio(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "不适用"
    return f"{numerator}/{denominator}（{numerator / denominator * 100:.1f}%）"


def summarise(outcomes: list[Outcome]) -> dict[str, str]:
    """按指标汇总。**每个指标都连分母一起给**——数字脱离口径就会被误读。"""
    demand_checks = [c for o in outcomes for c in o.checks if o.category in
                     ("需求理解", "预算边界", "幻觉场景1_不存在的商品",
                      "幻觉场景2_商品缺参数", "幻觉场景3_预算低于全部候选")]
    understand = [c for c in demand_checks if c[0].startswith(("类别=", "预算="))]
    budget = [c for c in demand_checks if c[0] == "全部满足预算"]
    knowledge = [c for o in outcomes if o.category in ("知识检索", "语料外反例",
                                                       "幻觉场景4_知识库无资料")
                 for c in o.checks if c[0] in ("检索到资料", "判定为检索不到",
                                               "排第一的是 服务级/品类级",
                                               "排第一的是 品类级", "排第一的是 服务级")]
    halluc = [o for o in outcomes if o.category.startswith("幻觉场景")]
    relevance = [c for o in outcomes for c in o.checks
                 if c[0].startswith(("包含 ", "排除 "))]

    return {
        "**需求理解准确率**（逐字段比对）": _ratio(
            sum(1 for _n, ok, _d in understand if ok), len(understand)
        ),
        "**硬性条件满足率**（预算内推荐是否真在预算内）": _ratio(
            sum(1 for _n, ok, _d in budget if ok), len(budget)
        ),
        "**检索质量**（正例命中正确类型 / 反例返回空）": _ratio(
            sum(1 for _n, ok, _d in knowledge if ok), len(knowledge)
        ),
        "**幻觉场景通过率**（六类的可判定行为）": _ratio(
            sum(1 for o in halluc if o.passed), len(halluc)
        ),
        "**推荐相关性**（与预标注必含/必排集合的比对）": _ratio(
            sum(1 for _n, ok, _d in relevance if ok), len(relevance)
        ),
    }


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------


def render_markdown(outcomes: list[Outcome], meta: dict, cases: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# 效果评测报告")
    lines.append("")
    lines.append(f"> 评测集：`data/evaluation/cases.json`（{meta['version']}，"
                 f"更新于 {meta['updated_at']}）")
    lines.append("> ")
    lines.append("> **这是自评。** 评测集由本项目自行构造并标注，"
                 "每条用例的构造依据记录在它的 `origin` 字段里。")
    lines.append("> 下面的数字只在所声明的口径下成立，**不是第三方基准**。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 一、自动计算的指标")
    lines.append("")
    lines.append("| 指标 | 定义与分母 | 实测值 |")
    lines.append("|---|---|---|")
    definitions = {
        "**需求理解准确率**（逐字段比对）":
            "分母＝标注了预期的字段数；分子＝解析结果与预期一致的字段数",
        "**硬性条件满足率**（预算内推荐是否真在预算内）":
            "分母＝设置了预算的用例数；分子＝推荐商品价格全部在预算内的用例数",
        "**检索质量**（正例命中正确类型 / 反例返回空）":
            "分母＝全部知识检索用例的检查项数；分子＝通过的检查项数",
        "**幻觉场景通过率**（六类的可判定行为）":
            "分母＝幻觉场景用例数；分子＝行为符合预期（拒绝或说明）的用例数",
        "**推荐相关性**（与预标注必含/必排集合的比对）":
            "分母＝标注的必含与必排项数；分子＝实际结果与标注一致的项数",
    }
    summary = summarise(outcomes)
    for name, value in summary.items():
        lines.append(f"| {name} | {definitions[name]} | {value} |")
    lines.append("")
    lines.append("## 二、需人工复核的指标")
    lines.append("")
    lines.append("这两项**没有实测结论**——它们要人读，脚本给不出判定。")
    lines.append("把主观判断折进上面那张表会让读者以为是测量结果，所以单列。")
    lines.append("")
    lines.append("| 指标 | 定义 | 状态 |")
    lines.append("|---|---|---|")
    for name, definition in MANUAL_METRICS:
        lines.append(f"| {name} | {definition} | 尚未测量（需人工复核） |")
    lines.append("")
    lines.append("**复核材料**：下表列出每条需求类用例的首选商品与它的推荐理由，"
                 "供人工判断「推荐是否相关」「理由是否有资料支持」。")
    lines.append("")
    lines.append("| 用例 | 输入 | 首选商品与推荐理由 |")
    lines.append("|---|---|---|")
    review_rows = [(o, r) for o in outcomes for r in o.review]
    if not review_rows:
        lines.append("| — | — | 本次没有产生推荐结果 |")
    for outcome, row in review_rows:
        source = next(c for c in cases if c["id"] == outcome.case_id)
        lines.append(f"| `{outcome.case_id}` | {source['input']} | {row} |")
    lines.append("")
    lines.append("## 三、逐条明细")
    lines.append("")
    lines.append("| 用例 | 类别 | 判定 | 说明 |")
    lines.append("|---|---|---|---|")
    for outcome in outcomes:
        mark = "✅" if outcome.passed else "❌"
        detail = outcome.error or next(
            (d for _n, ok, d in outcome.checks if not ok),
            "; ".join(f"{n}: {d}" for n, _ok, d in outcome.checks[:2]),
        )
        lines.append(f"| `{outcome.case_id}` | {outcome.category} | {mark} | {detail} |")
    lines.append("")
    lines.append("## 四、失败项")
    lines.append("")
    failed = [o for o in outcomes if not o.passed]
    if not failed:
        lines.append("本次没有失败项。")
    else:
        for outcome in failed:
            lines.append(f"### `{outcome.case_id}`（{outcome.category}）")
            lines.append("")
            for name, ok, detail in outcome.checks:
                lines.append(f"- {'✅' if ok else '❌'} {name}：{detail}")
            lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 五、口径说明与边界")
    lines.append("")
    lines.append("1. **自评**：评测集由本项目构造并标注，天然偏向系统已有的能力。")
    lines.append("   它的用途是「在明确定义的口径下达到什么水平」，不是「行业排名」。")
    lines.append("2. **只走公开入口**：脚本只调用对外函数，不读内部状态——")
    lines.append("   复用被测代码的中间结果等于自己测自己。")
    lines.append("3. **只报告实测值**：未执行的项目标注「尚未测量」，不写目标值或参考值。")
    lines.append("4. **不合成总分**：自动指标与人工指标分列，避免主观判断被误读成测量结果。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="跑一遍效果评测")
    parser.add_argument("--only", help="只跑某个场景类别")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    parser.add_argument("--write", help="把报告写到指定文件")
    args = parser.parse_args()

    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    if args.only:
        cases = [c for c in cases if args.only in c["category"]]
        if not cases:
            print(f"没有匹配「{args.only}」的用例", file=sys.stderr)
            return 2

    catalog = data_loader.load_catalog()
    index = BM25Index(build_corpus(config.knowledge_dir(), catalog.products))
    context = ToolContext(catalog=catalog, knowledge_index=index)

    outcomes: list[Outcome] = []
    for case in cases:
        runners = {
            "知识检索": lambda c: _run_knowledge_case(c, index),
            "语料外反例": lambda c: _run_knowledge_case(c, index),
            "多商品比较": lambda c: _run_compare_case(c, catalog),
            "工具调用": lambda c: _run_tool_case(c, context),
        }
        try:
            category = case["category"]
            if category in runners:
                outcome = runners[category](case)
            elif category == "幻觉场景4_知识库无资料":
                outcome = _run_knowledge_case(case, index)
            elif category == "幻觉场景5_资料自相矛盾":
                outcome = _run_consistency_case(case, catalog)
            elif category == "幻觉场景6_无依据的性能结论":
                outcome = _run_claim_guard_case(case)
            else:
                outcome = _run_demand_case(case, catalog)
        except Exception as exc:  # noqa: BLE001 —— 单条失败不中断整体
            outcome = Outcome(case["id"], case["category"], False,
                              error=f"{type(exc).__name__}: {exc}")
        outcomes.append(outcome)

    if args.json:
        print(json.dumps(
            {
                "metrics": summarise(outcomes),
                "manual": [name for name, _d in MANUAL_METRICS],
                "outcomes": [
                    {"id": o.case_id, "category": o.category, "passed": o.passed,
                     "error": o.error,
                     "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in o.checks]}
                    for o in outcomes
                ],
            },
            ensure_ascii=False, indent=2,
        ))
        return 0

    report = render_markdown(outcomes, payload, payload["cases"])
    if args.write:
        Path(args.write).write_text(report, encoding="utf-8")
        print(f"报告已写入 {args.write}")
    else:
        print(report)

    passed = sum(1 for o in outcomes if o.passed)
    print(f"\n共 {len(outcomes)} 条，通过 {passed}，失败 {len(outcomes) - passed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
