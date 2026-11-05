"""评测报告的汇总、渲染与读取。

设计要点
--------
- **指标只算一次。** JSON、Markdown、终端三种输出都从 `EvaluationReport`
  读取同一组结构化的 `Metric`，避免三套数字各自漂移。
- **指标带分子分母。** 分母为零时展示「不适用」，不输出 0% 或推测值。
- **报告可被读取方校验。** `load_report()` 检查 schema 版本，并重新计算当前
  评测集与商品数据的指纹，识别「报告已过期」。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src import config

from .checks import Outcome

#: 报告结构版本。字段变化时递增，读取方据此拒绝猜测旧格式。
SCHEMA_VERSION = 1

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = PROJECT_ROOT / "data" / "evaluation" / "cases.json"

#: 报告必须包含的顶层字段。
REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "generated_at",
        "dataset",
        "retrieval",
        "summary",
        "metrics",
        "manual_metrics",
        "categories",
        "outcomes",
    }
)

#: 需要人工复核的指标——脚本只列明细，不给结论。
MANUAL_METRICS: tuple[tuple[str, str], ...] = (
    ("任务完成率", "用户能否通过系统完成预定的选购任务"),
    ("证据支持率", "推荐理由中能由商品资料支持的事实占比"),
)

#: 自动指标的定义。键与 `Metric.key` 对应。
METRIC_DEFINITIONS: dict[str, str] = {
    "demand_understanding": "分母＝标注了预期的字段数；分子＝解析结果与预期一致的字段数",
    "hard_constraints": "分母＝设置了预算的用例数；分子＝推荐商品价格全部在预算内的用例数",
    "retrieval_quality": "分母＝全部知识检索用例的检查项数；分子＝通过的检查项数",
    "hallucination": "分母＝幻觉场景用例数；分子＝行为符合预期（拒绝或说明）的用例数",
    "recommendation_relevance": "分母＝标注的必含与必排项数；分子＝实际结果与标注一致的项数",
}

#: 需求类用例的类别。这些类别的检查项参与需求理解与硬性条件指标。
_DEMAND_CATEGORIES = frozenset(
    {
        "需求理解",
        "预算边界",
        "幻觉场景1_不存在的商品",
        "幻觉场景2_商品缺参数",
        "幻觉场景3_预算低于全部候选",
    }
)

#: 知识检索类用例的类别。
_KNOWLEDGE_CATEGORIES = frozenset(
    {"知识检索", "语料外反例", "幻觉场景4_知识库无资料"}
)

#: 参与检索质量指标的具体检查项名称。
_KNOWLEDGE_CHECK_NAMES = frozenset(
    {
        "检索到资料",
        "判定为检索不到",
        "排第一的是 服务级/品类级",
        "排第一的是 品类级",
        "排第一的是 服务级",
    }
)


@dataclass(frozen=True)
class Metric:
    """一个自动指标。展示值是派生的，分子分母才是事实。"""

    key: str
    label: str
    definition: str
    numerator: int
    denominator: int

    @property
    def display(self) -> str:
        if self.denominator == 0:
            return "不适用"
        ratio = self.numerator / self.denominator * 100
        return f"{self.numerator}/{self.denominator}（{ratio:.1f}%）"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "definition": self.definition,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "display": self.display,
        }


@dataclass(frozen=True)
class CategorySummary:
    """按场景类别汇总的通过情况。"""

    category: str
    total: int
    passed: int

    @property
    def failed(self) -> int:
        return self.total - self.passed

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
        }


def _metric(key: str, label: str, pairs) -> Metric:
    pairs = list(pairs)
    return Metric(
        key=key,
        label=label,
        definition=METRIC_DEFINITIONS[key],
        numerator=sum(1 for _name, ok, _detail in pairs if ok),
        denominator=len(pairs),
    )


def summarise(outcomes: list[Outcome]) -> list[Metric]:
    """按指标汇总。**每个指标都连分母一起给**——数字脱离口径就会被误读。"""
    demand_checks = [
        check
        for outcome in outcomes
        if outcome.category in _DEMAND_CATEGORIES
        for check in outcome.checks
    ]
    understand = [
        check
        for check in demand_checks
        if check[0].startswith(("类别=", "预算="))
    ]
    budget = [check for check in demand_checks if check[0] == "全部满足预算"]
    knowledge = [
        check
        for outcome in outcomes
        if outcome.category in _KNOWLEDGE_CATEGORIES
        for check in outcome.checks
        if check[0] in _KNOWLEDGE_CHECK_NAMES
    ]
    hallucination = [
        outcome for outcome in outcomes if outcome.category.startswith("幻觉场景")
    ]
    relevance = [
        check
        for outcome in outcomes
        for check in outcome.checks
        if check[0].startswith(("包含 ", "排除 "))
    ]

    return [
        _metric("demand_understanding", "需求理解准确率", understand),
        _metric("hard_constraints", "硬性条件满足率", budget),
        _metric("retrieval_quality", "检索质量", knowledge),
        _metric(
            "hallucination",
            "幻觉场景通过率",
            [(o.case_id, o.passed, "") for o in hallucination],
        ),
        _metric("recommendation_relevance", "推荐相关性", relevance),
    ]


def category_summaries(outcomes: list[Outcome]) -> list[CategorySummary]:
    counts: dict[str, list[int]] = {}
    for outcome in outcomes:
        passed, total = counts.setdefault(outcome.category, [0, 0])
        counts[outcome.category] = [passed + int(outcome.passed), total + 1]
    return [
        CategorySummary(category=category, total=total, passed=passed)
        for category, (passed, total) in sorted(counts.items())
    ]


def file_sha256(path: Path) -> str:
    """文件内容指纹。文件不存在时返回空串，由调用方决定如何呈现。"""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def dataset_metadata(
    payload: dict, *, cases_path: Path, products_path: Path, case_count: int
) -> dict:
    return {
        "name": str(payload.get("name", "")),
        "version": str(payload.get("version", "")),
        "updated_at": str(payload.get("updated_at", "")),
        "case_count": case_count,
        "cases_sha256": file_sha256(cases_path),
        "products_sha256": file_sha256(products_path),
    }


def now_local() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class EvaluationReport:
    """一次评测运行的完整结果。三种渲染都从这里出发。"""

    generated_at: str
    dataset: dict
    retrieval: dict
    outcomes: list[Outcome]
    total_duration_ms: int = 0

    @property
    def summary(self) -> dict:
        passed = sum(1 for outcome in self.outcomes if outcome.passed)
        return {
            "total": len(self.outcomes),
            "passed": passed,
            "failed": len(self.outcomes) - passed,
            "duration_ms": self.total_duration_ms,
        }

    @property
    def metrics(self) -> list[Metric]:
        return summarise(self.outcomes)

    @property
    def manual_metrics(self) -> list[dict]:
        return [
            {
                "name": name,
                "definition": definition,
                "status": "尚未测量（需人工复核）",
            }
            for name, definition in MANUAL_METRICS
        ]

    @property
    def categories(self) -> list[CategorySummary]:
        return category_summaries(self.outcomes)

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": self.generated_at,
            "dataset": dict(self.dataset),
            "retrieval": dict(self.retrieval),
            "summary": self.summary,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "manual_metrics": self.manual_metrics,
            "categories": [category.to_dict() for category in self.categories],
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def build_report(
    outcomes: list[Outcome],
    *,
    dataset: dict,
    retrieval: dict,
    generated_at: str | None = None,
    total_duration_ms: int = 0,
) -> EvaluationReport:
    return EvaluationReport(
        generated_at=generated_at or now_local(),
        dataset=dataset,
        retrieval=retrieval,
        outcomes=outcomes,
        total_duration_ms=total_duration_ms,
    )


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------


def render_markdown(report: EvaluationReport) -> str:
    dataset = report.dataset
    lines: list[str] = [
        "# 效果评测报告",
        "",
        f"> 评测集：`data/evaluation/cases.json`（{dataset.get('version') or '未知版本'}，"
        f"更新于 {dataset.get('updated_at') or '未知'}）",
        f"> 生成时间：{report.generated_at}",
        f"> 检索模式：{report.retrieval.get('label') or '未记录'}",
        ">",
        "> **这是自评。** 评测集由本项目自行构造并标注，"
        "每条用例的构造依据记录在它的 `origin` 字段里。",
        "> 下面的数字只在所声明的口径下成立，**不是第三方基准**。",
        "",
        "---",
        "",
        "## 一、自动计算的指标",
        "",
        "| 指标 | 定义与分母 | 实测值 |",
        "|---|---|---|",
    ]
    for metric in report.metrics:
        lines.append(
            f"| **{metric.label}** | {metric.definition} | {metric.display} |"
        )

    lines += [
        "",
        "## 二、需人工复核的指标",
        "",
        "这两项**没有实测结论**——它们要人读，脚本给不出判定。",
        "把主观判断折进上面那张表会让读者以为是测量结果，所以单列。",
        "",
        "| 指标 | 定义 | 状态 |",
        "|---|---|---|",
    ]
    for item in report.manual_metrics:
        lines.append(f"| {item['name']} | {item['definition']} | {item['status']} |")

    lines += [
        "",
        "**复核材料**：下表列出每条需求类用例的首选商品与它的推荐理由，"
        "供人工判断「推荐是否相关」「理由是否有资料支持」。",
        "",
        "| 用例 | 输入 | 首选商品与推荐理由 |",
        "|---|---|---|",
    ]
    review_rows = [(o, row) for o in report.outcomes for row in o.review]
    if not review_rows:
        lines.append("| — | — | 本次没有产生推荐结果 |")
    for outcome, row in review_rows:
        lines.append(f"| `{outcome.case_id}` | {outcome.input} | {row} |")

    lines += [
        "",
        "## 三、逐条明细",
        "",
        "| 用例 | 类别 | 判定 | 说明 |",
        "|---|---|---|---|",
    ]
    for outcome in report.outcomes:
        mark = "✅" if outcome.passed else "❌"
        detail = outcome.error or next(
            (detail for _name, ok, detail in outcome.checks if not ok),
            "; ".join(f"{name}: {detail}" for name, _ok, detail in outcome.checks[:2]),
        )
        lines.append(
            f"| `{outcome.case_id}` | {outcome.category} | {mark} | {detail} |"
        )

    lines += ["", "## 四、失败项", ""]
    failed = [outcome for outcome in report.outcomes if not outcome.passed]
    if not failed:
        lines.append("本次没有失败项。")
    else:
        for outcome in failed:
            lines += [f"### `{outcome.case_id}`（{outcome.category}）", ""]
            for name, ok, detail in outcome.checks:
                lines.append(f"- {'✅' if ok else '❌'} {name}：{detail}")
            if outcome.error:
                lines.append(f"- ❌ 执行错误：{outcome.error}")
            lines.append("")

    lines += [
        "---",
        "",
        "## 五、口径说明与边界",
        "",
        "1. **自评**：评测集由本项目构造并标注，天然偏向系统已有的能力。",
        "   它的用途是「在明确定义的口径下达到什么水平」，不是「行业排名」。",
        "2. **只走公开入口**：脚本只调用对外函数，不读内部状态——",
        "   复用被测代码的中间结果等于自己测自己。",
        "3. **只报告实测值**：未执行的项目标注「尚未测量」，不写目标值或参考值。",
        "4. **不合成总分**：自动指标与人工指标分列，避免主观判断被误读成测量结果。",
        "",
        "### 关于「全绿」该怎么读",
        "",
        "**评测集一旦被用来驱动修复，其后再全绿就是预期结果，不是独立验证。**",
        "",
        "本项目的实际情况是：评测套件建成当天跑第一遍就找出四个缺陷，",
        "修复后重跑全绿。这条链路本身是健康的（评测起作用了），",
        "**当前的 100% 不能读成「系统质量 100%」**——它只说明「这套题现在都会做了」。",
        "",
        "要打破这个循环，只能靠**新增**用例（尤其是能想到的失败情形），",
        "而不是反复跑同一套。人工复核的两项也是为此而留。",
        "",
    ]
    return "\n".join(lines)


def render_terminal(report: EvaluationReport) -> str:
    """终端只读摘要：指标与总数，不重复整份 Markdown。"""
    lines = [f"{metric.label}：{metric.display}" for metric in report.metrics]
    summary = report.summary
    lines.append(
        f"共 {summary['total']} 条，通过 {summary['passed']}，失败 {summary['failed']}，"
        f"耗时 {summary['duration_ms'] / 1000:.1f}s"
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 读取与校验
# --------------------------------------------------------------------------


@dataclass
class LoadedReport:
    """读取结果。`error` 非空时页面只展示提示，不猜字段。"""

    path: Path
    report: dict | None = None
    error: str = ""
    stale_reasons: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.report is not None and not self.error


def _is_object(value) -> bool:
    return isinstance(value, dict)


def _is_summary(value) -> bool:
    return _is_object(value) and all(
        isinstance(value.get(key), int)
        for key in ("total", "passed", "failed", "duration_ms")
    )


def _is_metric(value) -> bool:
    return (
        _is_object(value)
        and isinstance(value.get("key"), str)
        and isinstance(value.get("label"), str)
        and isinstance(value.get("definition"), str)
        and isinstance(value.get("numerator"), int)
        and isinstance(value.get("denominator"), int)
        and isinstance(value.get("display"), str)
    )


def _is_check(value) -> bool:
    return (
        _is_object(value)
        and isinstance(value.get("name"), str)
        and isinstance(value.get("ok"), bool)
        and isinstance(value.get("detail"), str)
    )


def _is_outcome(value) -> bool:
    checks = value.get("checks") if _is_object(value) else None
    review = value.get("review", []) if _is_object(value) else None
    return (
        _is_object(value)
        and isinstance(value.get("id"), str)
        and isinstance(value.get("category"), str)
        and isinstance(value.get("passed"), bool)
        and isinstance(checks, list)
        and all(_is_check(check) for check in checks)
        and isinstance(review, list)
        and all(isinstance(row, str) for row in review)
    )


def _is_category(value) -> bool:
    return (
        _is_object(value)
        and isinstance(value.get("category"), str)
        and isinstance(value.get("passed"), int)
        and isinstance(value.get("total"), int)
        and isinstance(value.get("failed"), int)
    )


def _is_manual_metric(value) -> bool:
    return (
        _is_object(value)
        and isinstance(value.get("name"), str)
        and isinstance(value.get("definition"), str)
        and isinstance(value.get("status"), str)
    )


def load_report(
    path: Path,
    *,
    cases_path: Path | None = None,
    products_path: Path | None = None,
) -> LoadedReport:
    """读取报告并校验格式与输入指纹。

    任何读取/格式问题都转成中文 `error`，不向调用方抛异常——页面只需要
    根据结果决定是否渲染，而不是处理堆栈。
    """
    path = Path(path)
    if not path.exists():
        return LoadedReport(
            path=path,
            error="尚未生成评测报告。运行下方的命令生成后再回来查看。",
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return LoadedReport(
            path=path,
            error="报告文件不是合法 JSON，无法读取。请重新生成评测报告。",
        )

    if not _is_object(payload):
        return LoadedReport(
            path=path,
            error="报告文件的结构不正确，无法读取。请重新生成评测报告。",
        )

    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        return LoadedReport(
            path=path,
            error=(
                f"报告格式版本 {version!r} 与当前版本 {SCHEMA_VERSION} 不匹配，"
                "请重新生成评测报告。"
            ),
        )

    missing = REQUIRED_KEYS - set(payload)
    if missing:
        return LoadedReport(
            path=path,
            error=f"报告缺少必要字段：{'、'.join(sorted(missing))}。请重新生成。",
        )

    if not _is_object(payload.get("dataset")) or not _is_summary(
        payload.get("summary")
    ):
        return LoadedReport(
            path=path,
            error="报告的数据集或总览字段结构不正确，请重新生成评测报告。",
        )

    if not _is_object(payload.get("retrieval")):
        return LoadedReport(
            path=path,
            error="报告的检索模式字段结构不正确，请重新生成评测报告。",
        )

    metrics = payload.get("metrics")
    if not isinstance(metrics, list) or not all(_is_metric(item) for item in metrics):
        return LoadedReport(
            path=path,
            error="报告的指标结构不正确，请重新生成评测报告。",
        )

    categories = payload.get("categories")
    if not isinstance(categories, list) or not all(
        _is_category(item) for item in categories
    ):
        return LoadedReport(
            path=path,
            error="报告的分类结果结构不正确，请重新生成评测报告。",
        )

    manual = payload.get("manual_metrics")
    if not isinstance(manual, list) or not all(
        _is_manual_metric(item) for item in manual
    ):
        return LoadedReport(
            path=path,
            error="报告的人工指标结构不正确，请重新生成评测报告。",
        )

    outcomes = payload.get("outcomes")
    if not isinstance(outcomes, list) or not all(
        _is_outcome(item) for item in outcomes
    ):
        return LoadedReport(
            path=path,
            error="报告的逐条结果结构不正确，请重新生成评测报告。",
        )

    cases_path = Path(cases_path) if cases_path else CASES_PATH
    products_path = Path(products_path) if products_path else config.products_path()
    dataset = payload["dataset"]
    stale: list[str] = []

    expected_cases = str(dataset.get("cases_sha256", ""))
    current_cases = file_sha256(cases_path)
    if not expected_cases:
        stale.append("报告未记录评测集指纹")
    elif not current_cases:
        stale.append("当前评测集文件缺失")
    elif expected_cases != current_cases:
        stale.append("评测集已变化")

    expected_products = str(dataset.get("products_sha256", ""))
    current_products = file_sha256(products_path)
    if not expected_products:
        stale.append("报告未记录商品数据指纹")
    elif not current_products:
        stale.append("当前商品数据文件缺失")
    elif expected_products != current_products:
        stale.append("商品数据已变化")

    return LoadedReport(path=path, report=payload, stale_reasons=stale)
