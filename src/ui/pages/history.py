"""历史记录页。

本页在阶段四补齐（SQLite 持久化 + 消费决策报告）。当前只展示
**本次会话内**做过的分析，并明确说明持久化还没接上——
不做一个看起来能用、实际不保存任何东西的假页面。
"""

from __future__ import annotations

import streamlit as st

from src.data_loader import Catalog
from src.ui import components, state
from src.ui.theme import bullet_list, facts


def render(catalog: Catalog) -> None:
    components.page_header(
        "历史记录",
        "回顾过去的分析，重新打开当时的结论。",
    )

    components.show_notice(
        "历史记录的持久化（SQLite）与消费决策报告在阶段四实现，尚未接入。"
        "下面是本次会话内做过的分析，刷新页面后会丢失。",
        "warn",
    )

    demand = state.get(state.KEY_DEMAND)
    result = state.get(state.KEY_RESULT)

    if demand is None or result is None:
        components.empty_state(
            "本次会话还没有分析记录。到「智能分析」页做一次分析后，这里会显示摘要。"
        )
        return

    components.section_title("本次会话的分析")

    pairs = [
        ("需求摘要", demand.summary_line()),
        ("候选商品", f"{result.candidate_count} 件"),
        ("预算内", f"{len(result.within_budget)} 件"),
        ("超出预算", f"{len(result.over_budget)} 件"),
    ]
    if result.best is not None:
        pairs.append(("首选推荐", f"{result.best.product.name}（{result.best.score.total:.0f} 分）"))

    st.markdown(facts(pairs), unsafe_allow_html=True)

    if result.relaxations:
        components.section_title("当时给出的放宽建议")
        st.markdown(bullet_list(result.relaxations), unsafe_allow_html=True)

    components.section_title("阶段四将要补上的能力")
    st.markdown(
        bullet_list(
            [
                "把每次分析写入 SQLite：需求摘要、推荐结果、分析时间",
                "从历史列表重新打开一份报告，还原当时的结论（而不是按当前数据重算）",
                "收藏感兴趣的商品，重启应用后仍然存在",
                "导出报告为 Markdown 或 CSV",
                "数据库损坏时给出中文提示，且不影响继续做新分析",
            ]
        ),
        unsafe_allow_html=True,
    )
