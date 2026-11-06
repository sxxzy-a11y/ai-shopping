"""评测 runner 自身的回归测试。

**runner 坏了，报告就是错的。** 这个文件不测推荐质量，只测评测资产：
能不能跑、单条失败会不会拖垮整体、重复跑结果是否一致、报告结构是否完整。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eval import checks
from eval.report import build_report, render_markdown
from eval.runner import build_evaluation, load_cases, main, run_cases

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = PROJECT_ROOT / "data" / "evaluation" / "cases.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return load_cases(CASES_PATH)


@pytest.fixture
def tool_cases(payload: dict) -> list[dict]:
    """工具调用用例跑得快，且不需要完整推荐链路。"""
    cases = [case for case in payload["cases"] if case["category"] == "工具调用"]
    assert cases, "评测集里没有工具调用用例"
    return cases[:2]


def _signature(result) -> list[tuple]:
    """只保留可复现的部分：通过状态与逐项检查，忽略耗时。"""
    return [
        (
            outcome.case_id,
            outcome.passed,
            [(name, ok) for name, ok, _detail in outcome.checks],
        )
        for outcome in result.outcomes
    ]


def test_runner_executes_subset(tool_cases):
    result = run_cases(tool_cases)

    assert len(result.outcomes) == len(tool_cases)
    assert result.duration_ms >= 0
    for outcome in result.outcomes:
        assert outcome.case_id
        assert outcome.category == "工具调用"
        assert outcome.checks, "每条用例至少应产生一项检查"
        assert outcome.duration_ms >= 0


def test_one_failure_does_not_stop_the_rest(tool_cases, monkeypatch):
    original = checks.run_tool_case

    def flaky(case, context):
        if case["id"] == tool_cases[0]["id"]:
            raise RuntimeError("boom")
        return original(case, context)

    monkeypatch.setattr(checks, "run_tool_case", flaky)
    result = run_cases(tool_cases)

    assert result.outcomes[0].passed is False
    assert "boom" in result.outcomes[0].error
    assert result.outcomes[1].checks, "第一条失败不应该让第二条没有结果"


def test_repeated_runs_are_stable(tool_cases):
    first = run_cases(tool_cases)
    second = run_cases(tool_cases)

    assert _signature(first) == _signature(second)


def test_report_has_versioned_structure_and_no_combined_score(tool_cases, payload):
    report = build_evaluation(payload, tool_cases)
    data = report.to_dict()

    assert data["schema_version"] == 1
    required = {
        "generated_at",
        "dataset",
        "retrieval",
        "summary",
        "metrics",
        "manual_metrics",
        "categories",
        "outcomes",
    }
    assert required <= set(data)
    assert data["retrieval"]["mode"] == "bm25"
    assert data["dataset"]["case_count"] == len(tool_cases)
    assert data["dataset"]["cases_sha256"]
    assert data["dataset"]["products_sha256"]

    for metric in data["metrics"]:
        assert {"key", "label", "definition", "numerator", "denominator", "display"} <= set(
            metric
        )
        assert isinstance(metric["numerator"], int)
        assert isinstance(metric["denominator"], int)

    assert "total_score" not in data
    assert all(
        item["status"] == "尚未测量（需人工复核）"
        for item in data["manual_metrics"]
    )


def test_zero_denominator_is_not_zero_percent():
    report = build_report([], dataset={}, retrieval={})
    data = report.to_dict()

    assert all(metric["display"] == "不适用" for metric in data["metrics"])
    assert "0%" not in report.to_json()


def test_markdown_and_json_use_the_same_metric_values(tool_cases, payload):
    report = build_evaluation(payload, tool_cases)
    markdown = render_markdown(report)

    for metric in report.metrics:
        assert metric.display in markdown
    assert "自评" in markdown
    assert "不合成总分" in markdown
    assert "目标 95%" not in markdown


def test_cli_output_dir_writes_both_formats(tmp_path, capsys):
    exit_code = main(["--only", "工具调用", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    report_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"
    assert report_path.exists()
    assert markdown_path.exists()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] > 0
    assert {item["category"] for item in payload["categories"]} == {"工具调用"}
    assert "自评" in markdown_path.read_text(encoding="utf-8")


def test_cli_unknown_category_returns_2(capsys):
    assert main(["--only", "不存在的类别"]) == 2
    assert "没有匹配" in capsys.readouterr().err


def test_cli_survives_narrow_encoding_console():
    """Windows 默认 GBK 控制台曾因 ✅ 抛 UnicodeEncodeError，整次评测中断。

    回归：终端编不了 emoji 时降级为 `[OK]`/`[FAIL]`，而不是让报告跑不出来。
    """
    env = {**os.environ, "PYTHONIOENCODING": "gbk"}
    completed = subprocess.run(
        [sys.executable, "-m", "eval.runner", "--only", "工具调用"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="gbk",
        errors="replace",
        env=env,
        timeout=180,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "UnicodeEncodeError" not in completed.stderr
    assert "[OK]" in completed.stdout, "窄编码终端应降级为 ASCII 标记"


def test_written_markdown_keeps_emoji(tmp_path):
    """降级只发生在终端；写出的报告文件仍是完整 UTF-8 内容。"""
    target = tmp_path / "report.md"
    assert main(["--only", "工具调用", "--write", str(target)]) == 0

    text = target.read_text(encoding="utf-8")
    assert "✅" in text, "文件里的通过标记不该被降级替换"


def test_compat_script_still_runs():
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "evaluate.py"),
            "--only",
            "工具调用",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=180,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["schema_version"] == 1
    assert payload["summary"]["total"] > 0
