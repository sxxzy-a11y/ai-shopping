"""效果评测页的读取与空状态测试。

报告读取是纯函数，单独覆盖缺失、坏 JSON、未知 schema、指纹不匹配与正常
报告五种分支；页面本身用 AppTest 跑一遍，确认管理员可进入、普通用户被拒。
"""

from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from eval.report import load_report
from eval.runner import build_evaluation, load_cases
from src.auth import ROLE_ADMIN, ROLE_USER, User
from src.ui import state

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = PROJECT_ROOT / "data" / "evaluation" / "cases.json"

ADMIN_USER = User(username="root", role=ROLE_ADMIN)
NORMAL_USER = User(username="tester", role=ROLE_USER)


def _valid_report() -> dict:
    payload = load_cases(CASES_PATH)
    cases = [case for case in payload["cases"] if case["category"] == "工具调用"][:1]
    return build_evaluation(payload, cases).to_dict()


def _run_page(tmp_path, monkeypatch, report_path: Path, user: User = ADMIN_USER):
    monkeypatch.setenv("ZHIGOU_EVAL_REPORT_PATH", str(report_path))
    script = tmp_path / "dashboard_page.py"
    script.write_text(
        "from src.ui.pages import eval_dashboard\neval_dashboard.render(None)\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(script), default_timeout=30)
    at.session_state[state.KEY_USER] = user
    at.run()
    return at


def _text(at: AppTest) -> str:
    chunks: list[str] = []
    for attr in (
        "markdown",
        "caption",
        "title",
        "header",
        "subheader",
        "text",
        "info",
        "warning",
        "code",
        "expander",
        "dataframe",
    ):
        for element in getattr(at, attr, []):
            chunks.append(str(getattr(element, "value", "")))
    return "\n".join(chunks)


# --------------------------------------------------------------------------
# 纯读取函数
# --------------------------------------------------------------------------


def test_missing_report_returns_chinese_error(tmp_path):
    loaded = load_report(tmp_path / "missing.json")

    assert loaded.report is None
    assert "尚未生成" in loaded.error
    assert loaded.stale_reasons == []


def test_corrupt_json_is_reported_without_traceback(tmp_path):
    path = tmp_path / "report.json"
    path.write_text("not json", encoding="utf-8")

    loaded = load_report(path)

    assert loaded.report is None
    assert "JSON" in loaded.error


def test_unknown_schema_is_rejected(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"schema_version": 999}), encoding="utf-8")

    loaded = load_report(path)

    assert loaded.report is None
    assert "格式版本" in loaded.error


def test_missing_required_field_is_rejected(tmp_path):
    data = _valid_report()
    data.pop("metrics")
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    loaded = load_report(path)

    assert loaded.report is None
    assert "缺少必要字段" in loaded.error


def test_malformed_metric_is_rejected(tmp_path):
    data = _valid_report()
    data["metrics"][0]["numerator"] = "很多"
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    loaded = load_report(path)

    assert loaded.report is None
    assert "指标结构" in loaded.error


def test_valid_report_loads_without_stale_reasons(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_valid_report(), ensure_ascii=False), encoding="utf-8")

    loaded = load_report(path, cases_path=CASES_PATH)

    assert loaded.ok
    assert loaded.report is not None
    assert loaded.stale_reasons == []


def test_changed_inputs_are_flagged_as_stale(tmp_path):
    data = _valid_report()
    data["dataset"]["cases_sha256"] = "deadbeef"
    data["dataset"]["products_sha256"] = "deadbeef"
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    loaded = load_report(path, cases_path=CASES_PATH)

    assert loaded.ok
    assert "评测集已变化" in loaded.stale_reasons
    assert "商品数据已变化" in loaded.stale_reasons


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------


def test_page_shows_missing_state_and_command(tmp_path, monkeypatch):
    at = _run_page(tmp_path, monkeypatch, tmp_path / "missing.json")

    assert not at.exception
    text = _text(at)
    assert "尚未生成" in text
    assert "python -m eval.runner" in text


def test_page_renders_valid_report(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_valid_report(), ensure_ascii=False), encoding="utf-8")

    at = _run_page(tmp_path, monkeypatch, path)

    assert not at.exception
    text = _text(at)
    assert "这是自评" in text
    assert "需求理解准确率" in text
    assert "需人工复核" in text


def test_page_shows_corrupt_report_error(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_text("not json", encoding="utf-8")

    at = _run_page(tmp_path, monkeypatch, path)

    assert not at.exception
    assert "JSON" in _text(at)


def test_page_shows_unknown_schema_error(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"schema_version": 999}), encoding="utf-8")

    at = _run_page(tmp_path, monkeypatch, path)

    assert not at.exception
    assert "格式版本" in _text(at)


def test_page_warns_when_report_is_stale(tmp_path, monkeypatch):
    data = _valid_report()
    data["dataset"]["cases_sha256"] = "deadbeef"
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    at = _run_page(tmp_path, monkeypatch, path)

    assert not at.exception
    assert "报告可能已过期" in _text(at)


def test_page_rejects_non_admin(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_valid_report(), ensure_ascii=False), encoding="utf-8")

    at = _run_page(tmp_path, monkeypatch, path, user=NORMAL_USER)

    assert at.exception, "普通用户进入页面时必须在入口被权限守卫拒绝"
