"""评测 runner：载入用例、构建上下文、逐条调度、计时与 CLI。

只负责「跑」和「收集结果」；指标体系与渲染在 `eval.report`，各场景的检查
在 `eval.checks`。这样 runner 本身可以被单独测试，不需要先解析报告文本。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from src import config, data_loader
from src.agent.registry import ToolContext
from src.knowledge.corpus import build_corpus
from src.knowledge.index import BM25Index

from . import checks
from .report import (
    CASES_PATH,
    EvaluationReport,
    build_report,
    dataset_metadata,
    render_markdown,
    render_terminal,
)

#: 当前 runner 实际使用的检索模式。页面只展示这里记录的事实。
RETRIEVAL = {
    "mode": "bm25",
    "label": "BM25 本地关键词检索",
    "detail": "未启用向量检索",
}


@dataclass
class RunResult:
    """一次运行的逐条结果与总耗时。"""

    outcomes: list[checks.Outcome]
    duration_ms: int


def load_cases(path: Path = CASES_PATH) -> dict:
    """读取评测集 JSON。文件缺失或格式错误时直接抛出，由 CLI 暴露给开发者。"""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload.get("cases"), list):
        raise ValueError(f"评测集缺少 cases 数组：{path}")
    return payload


def build_context() -> tuple[object, BM25Index, ToolContext]:
    """构建评测需要的商品目录、检索索引与工具上下文。"""
    catalog = data_loader.load_catalog()
    index = BM25Index(build_corpus(config.knowledge_dir(), catalog.products))
    context = ToolContext(catalog=catalog, knowledge_index=index)
    return catalog, index, context


def _dispatch(
    case: dict, catalog, index: BM25Index, context: ToolContext
) -> checks.Outcome:
    category = case["category"]
    if category in ("知识检索", "语料外反例", "幻觉场景4_知识库无资料"):
        return checks.run_knowledge_case(case, index)
    if category == "多商品比较":
        return checks.run_compare_case(case, catalog)
    if category == "工具调用":
        return checks.run_tool_case(case, context)
    if category == "不支持的类别":
        return checks.run_unsupported_case(case)
    if category == "幻觉场景5_资料自相矛盾":
        return checks.run_consistency_case(case)
    if category == "幻觉场景6_无依据的性能结论":
        return checks.run_claim_guard_case(case)
    return checks.run_demand_and_recommend_case(case, catalog)


def run_case(
    case: dict, catalog, index: BM25Index, context: ToolContext
) -> checks.Outcome:
    """跑单条用例。异常在这里被收住，不中断整次评测。"""
    started = time.perf_counter()
    try:
        outcome = _dispatch(case, catalog, index, context)
    except Exception as exc:  # noqa: BLE001 —— 单条失败不中断整体
        outcome = checks.Outcome(
            case_id=case["id"],
            category=case["category"],
            passed=False,
            error=f"{type(exc).__name__}: {exc}",
        )
    outcome.input = str(case.get("input", ""))
    outcome.duration_ms = int((time.perf_counter() - started) * 1000)
    return outcome


def run_cases(
    cases: list[dict],
    *,
    catalog=None,
    index: BM25Index | None = None,
    context: ToolContext | None = None,
) -> RunResult:
    """逐条执行用例并记录耗时。任一条失败不影响其余用例。"""
    if catalog is None or index is None or context is None:
        catalog, index, context = build_context()

    started = time.perf_counter()
    outcomes = [run_case(case, catalog, index, context) for case in cases]
    duration_ms = int((time.perf_counter() - started) * 1000)
    return RunResult(outcomes=outcomes, duration_ms=duration_ms)


def build_evaluation(
    payload: dict,
    cases: list[dict],
    *,
    cases_path: Path = CASES_PATH,
    products_path: Path | None = None,
    result: RunResult | None = None,
) -> EvaluationReport:
    """把一次运行汇总成报告对象。"""
    result = result or run_cases(cases)
    dataset = dataset_metadata(
        payload,
        cases_path=cases_path,
        products_path=products_path or config.products_path(),
        case_count=len(result.outcomes),
    )
    return build_report(
        result.outcomes,
        dataset=dataset,
        retrieval=RETRIEVAL,
        total_duration_ms=result.duration_ms,
    )


def evaluate(
    payload: dict | None = None, cases: list[dict] | None = None
) -> EvaluationReport:
    """便捷入口：载入评测集并跑完整套，返回报告对象。"""
    payload = payload or load_cases()
    return build_evaluation(payload, cases if cases is not None else payload["cases"])


def _configure_stdout() -> None:
    """窄编码终端兜底：不让一个符号把整次评测掀掉。

    Windows 默认控制台是 cp936/GBK，`render_markdown` 用 ✅/❌ 作通过标记，
    这两个字符编不出来时 `print` 会抛 `UnicodeEncodeError`，整次评测中断。
    这里只把错误策略放宽到 `replace`，**不改编码**——中文仍按本地编码显示，
    标记本身由 `_print` 换成 ASCII，可读性比变成问号好。
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(errors="replace")
    except (TypeError, ValueError, OSError):
        pass


def _print(text: str) -> None:
    """把报告打到终端；控制台编不了 ✅/❌ 时降级为 ASCII 标记。

    写文件走 `write_text(encoding="utf-8")`，报告内容里的 emoji 保持不变，
    所以这里只处理终端输出，不改变任何评测结果。
    """
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✅❌".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        text = text.replace("✅", "[OK]").replace("❌", "[FAIL]")
    print(text)


def render_categories(cases: list[dict]) -> str:
    """列出可用类别及用例数，供 `--list-categories` 与错误提示共用。"""
    counts: dict[str, int] = {}
    for case in cases:
        category = str(case.get("category") or "未分类")
        counts[category] = counts.get(category, 0) + 1

    lines = ["可用场景类别："]
    lines.extend(f"  {name}（{count} 条）" for name, count in sorted(counts.items()))
    lines.append("")
    lines.append("用法：python -m eval.runner --only <类别名>（支持名称片段匹配）")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="跑一遍效果评测")
    parser.add_argument("--only", help="只跑某个场景类别")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    parser.add_argument("--write", help="把 Markdown 报告写到指定文件")
    parser.add_argument(
        "--output-dir",
        help="把 report.json 与 report.md 写到指定目录（两者同源）",
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="列出可用的场景类别与用例数后退出",
    )
    args = parser.parse_args(argv)

    payload = load_cases()
    cases = payload["cases"]

    if args.list_categories:
        _print(render_categories(cases))
        return 0

    if args.only:
        cases = [case for case in cases if args.only in case["category"]]
        if not cases:
            # 原来的「没有匹配」让用户不知道能传什么，把可选项一起给出来。
            print(
                f"没有匹配「{args.only}」的用例。\n{render_categories(payload['cases'])}",
                file=sys.stderr,
            )
            return 2

    report = build_evaluation(payload, cases)

    if args.json:
        _print(report.to_json())
        return 0

    markdown = render_markdown(report)
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text(report.to_json(), encoding="utf-8")
        (output_dir / "report.md").write_text(markdown, encoding="utf-8")
        _print(f"报告已写入 {output_dir}")
        _print(render_terminal(report))
        return 0

    if args.write:
        Path(args.write).write_text(markdown, encoding="utf-8")
        _print(f"报告已写入 {args.write}")
        return 0

    _print(markdown)
    summary = report.summary
    _print(
        f"\n共 {summary['total']} 条，通过 {summary['passed']}，"
        f"失败 {summary['failed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
