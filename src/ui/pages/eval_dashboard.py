"""效果评测页：只读最近一次评测报告。

设计要点
--------
- **不在这里跑评测。** 评测会跑完整的推荐与检索链路，放在 Streamlit 页面里
  会让每次交互都阻塞数秒。页面只读 `config.eval_report_path()`。
- **不猜数字。** 报告缺失、损坏、格式过期时只给提示与生成命令；显示的是
  报告里的原值，不由页面推算或补全。
- **口径与数字同屏。** 每个自动指标旁边带定义与分母；人工指标明确标
  「尚未测量」，不合成总分。
"""

from __future__ import annotations

import streamlit as st

from src import config
from src.auth import require_admin
from src.ui import components, state
from src.ui.theme import esc

from eval.report import load_report

#: 报告缺失或过期时给用户复制的命令。只读页面不代为执行。
GENERATE_COMMAND = "python -m eval.runner --output-dir data/evaluation"


def _render_missing(loaded) -> None:
    components.show_notice(loaded.error, "warn")
    components.empty_state(
        "生成一份评测报告后刷新本页，就能看到指标、分类结果与失败明细。",
        icon_name="file",
    )
    st.code(GENERATE_COMMAND, language="bash")
    components.caption(
        "报告只会写入 data/evaluation/；本页不会在后台运行评测，也不会改动任何数据。"
    )


def _render_overview(report: dict) -> None:
    summary = report["summary"]
    dataset = report["dataset"]
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    duration = summary.get("duration_ms", 0)
    generated = str(report.get("generated_at", "")).replace("T", " ")[:19]

    components.stat_row(
        [
            ("check", f"{passed}/{total}", "用例通过"),
            ("alert", str(failed), "失败"),
            ("clock", f"{duration / 1000:.1f}s", "总耗时"),
            ("file", generated or "未记录", "生成时间"),
        ]
    )
    components.caption(
        f"评测集：{dataset.get('name') or '未记录'}　·　"
        f"版本 {dataset.get('version') or '未记录'}　·　"
        f"更新于 {dataset.get('updated_at') or '未记录'}"
    )


def _render_metrics(report: dict) -> None:
    components.section_title("自动指标", len(report.get("metrics", [])))
    metrics = report.get("metrics", [])
    if not metrics:
        components.show_notice("报告里没有自动指标。", "warn")
        return
    rows = [
        {
            "指标": metric.get("label", ""),
            "定义与分母": metric.get("definition", ""),
            "实测值": metric.get("display", "不适用"),
        }
        for metric in metrics
    ]
    st.dataframe(rows, width="stretch", hide_index=True)
    components.caption(
        "每个指标的分母不同，不能相加成一个总分；报告也不提供综合得分。"
    )


def _render_categories(report: dict) -> None:
    components.section_title("分类通过情况", len(report.get("categories", [])))
    categories = report.get("categories", [])
    if not categories:
        components.show_notice("报告里没有分类结果。", "warn")
        return
    rows = [
        {
            "场景类别": item.get("category", ""),
            "通过": item.get("passed", 0),
            "总数": item.get("total", 0),
            "失败": item.get("failed", 0),
        }
        for item in categories
    ]
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_failures(report: dict) -> None:
    failed = [item for item in report.get("outcomes", []) if not item.get("passed")]
    components.section_title("失败明细", len(failed))
    if not failed:
        components.show_notice("本次没有失败项。", "ok")
        return

    components.caption("每条失败项列出未通过的检查；通过项不在这里重复。")
    for outcome in failed:
        with st.expander(
            f"{outcome.get('id', '')} · {outcome.get('category', '')}",
            expanded=len(failed) == 1,
        ):
            if outcome.get("error"):
                components.show_notice(outcome["error"], "stop")
            for check in outcome.get("checks", []):
                mark = "✅" if check.get("ok") else "❌"
                st.markdown(
                    f"{mark} **{esc(check.get('name', ''))}**："
                    f"{esc(check.get('detail', ''))}"
                )


def _render_manual(report: dict) -> None:
    components.section_title("需人工复核", len(report.get("manual_metrics", [])))
    manual = report.get("manual_metrics", [])
    if manual:
        rows = [
            {
                "指标": item.get("name", ""),
                "定义": item.get("definition", ""),
                "状态": item.get("status", "尚未测量"),
            }
            for item in manual
        ]
        st.dataframe(rows, width="stretch", hide_index=True)

    reviews = [
        (outcome.get("id", ""), row)
        for outcome in report.get("outcomes", [])
        for row in outcome.get("review", [])
    ]
    if reviews:
        with st.expander("人工复核材料：首选商品与推荐理由", expanded=False):
            st.dataframe(
                [{"用例": case_id, "首选商品与推荐理由": row} for case_id, row in reviews],
                width="stretch",
                hide_index=True,
            )
    components.caption(
        "这两项要人读，脚本给不出判定；报告只列材料，不把它们折进自动指标。"
    )


def _render_meta(report: dict) -> None:
    retrieval = report.get("retrieval") or {}
    components.section_title("报告信息")
    components.caption(
        f"检索模式：{retrieval.get('label') or '未记录'}"
        + (f"（{retrieval['detail']}）" if retrieval.get("detail") else "")
        + f"　·　生成时间：{str(report.get('generated_at', '')).replace('T', ' ')[:19]}"
    )
    components.caption(
        "本页只读报告，不会执行评测。数据或用例变化后，请重新运行上面的命令生成新报告。"
    )


def render(catalog=None) -> None:
    """页面入口。`catalog` 用不上，签名与其它页面保持一致。"""
    require_admin(state.current_user())
    components.page_header(
        "效果评测",
        "读取最近一次评测报告，查看自动指标、分类结果与失败项。",
        kicker="质量测量",
    )

    loaded = load_report(config.eval_report_path())
    if not loaded.ok:
        _render_missing(loaded)
        return

    report = loaded.report
    components.show_notice(
        "这是自评：评测集由本项目自行构造并标注，结论只在所声明口径下成立，"
        "不是第三方基准。",
        "info",
    )
    if loaded.stale_reasons:
        components.show_notice(
            f"报告可能已过期：{'；'.join(loaded.stale_reasons)}。"
            f"报告生成于 {str(report.get('generated_at', '')).replace('T', ' ')[:19]}，"
            "请重新运行评测命令后再据此判断。",
            "warn",
        )

    _render_overview(report)
    _render_metrics(report)
    _render_categories(report)
    _render_failures(report)
    _render_manual(report)
    _render_meta(report)
