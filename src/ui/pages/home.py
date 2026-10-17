"""首页：产品定位、需求输入入口与数据集概览。"""

from __future__ import annotations

import streamlit as st

from src import config
from src.data_loader import Catalog
from src.ui import components, state
from src.ui.pages.analysis import EXAMPLE_DEMAND
from src.ui.theme import bullet_list

#: 产品能力说明卡：(图标, 标题, 说明)
_CAPABILITIES: list[tuple[str, str, str]] = [
    ("file", "需求理解", "把口语化描述拆成预算、用途、核心需求与可妥协项"),
    ("filter", "智能筛选", "按你的条件过滤候选，超预算的商品单独标注而不是藏起来"),
    ("scale", "多维评分", "预算匹配、需求匹配、性能适配、性价比、便携性加权打分"),
    ("check", "决策建议", "每个分数都给出加分项与扣分项，结论可追溯到具体数据"),
]


def go_to_analysis(raw_text: str) -> None:
    """把需求交给分析页并**直接跑出结果**。

    公开给 AI 问答页复用：那边的「涉及价格的问题请走筛选」引导，
    要的就是同一个动作——带着问题原文跳到分析页去筛选。

    只记请求、不直接写分析页控件的键——那些控件属于另一个页面，
    直接写会埋下顺序依赖（Streamlit 不允许控件实例化后改它的键）。
    同时置一个「自动执行」标记，由分析页在渲染完输入区之后消费。
    """
    st.session_state[state.KEY_PREFILL] = {
        "text": raw_text,
        "category": analysis_no_category(),
    }
    st.session_state["zg_autorun"] = True
    state.clear_analysis()
    state.request_page("智能分析")
    st.rerun()


def analysis_no_category() -> str:
    """与分析页「不指定类别」选项一致的文本。"""
    from src.ui.pages.analysis import _NO_CATEGORY

    return _NO_CATEGORY


def render(catalog: Catalog) -> None:
    components.page_header(
        "智购参谋",
        "基于 AI 的消费决策助手 —— 帮你在预算内买到真正适合自己的商品，"
        "并且告诉你这个结论是怎么得出来的。",
        right=components.runtime_chip(),
    )

    # --- 需求输入（做成一张卡，让首屏有一个明确的操作焦点）--------------
    with st.container(border=True):
        st.markdown(
            '<div class="zg-card-title">描述你的购买需求</div>'
            '<div class="zg-card-sub" style="margin-bottom:10px">'
            "说清楚要买什么、预算多少、主要用来做什么就够了。"
            "没说到的信息，系统会在下一步追问，不会替你猜。"
            "</div>",
            unsafe_allow_html=True,
        )
        st.text_area(
            "描述你的购买需求",
            key="zg_home_input",
            height=110,
            placeholder=f"例如：{EXAMPLE_DEMAND}",
            label_visibility="collapsed",
        )

        col_action, col_hint = st.columns([1, 3])
        with col_action:
            if st.button("开始分析", type="primary", width="stretch"):
                text = st.session_state.get("zg_home_input", "").strip()
                if text:
                    go_to_analysis(text)
                else:
                    # 没填内容就直接跳过去，那边会给出「请先描述需求」的提示
                    state.clear_analysis()
                    state.request_page("智能分析")
                    st.rerun()
        with col_hint:
            st.markdown(
                '<div class="zg-caption" style="padding-top:9px">'
                "也可以到「智能分析」页用下拉选项逐项填写。</div>",
                unsafe_allow_html=True,
            )

    # --- 产品能力 ---------------------------------------------------------
    components.section_title("它能做什么")
    components.feature_row(_CAPABILITIES)

    # --- 数据概览 ---------------------------------------------------------
    st.write("")
    components.stat_row(
        [
            ("tag", f"{len(catalog)}", "件商品"),
            ("grid", f"{len(catalog.present_categories())}", "个商品类别"),
            ("bookmark", f"{len(catalog.brands())}", "个品牌"),
            ("scale", f"{len(config.DIMENSION_LABELS)}", "项评分维度"),
        ]
    )

    if catalog.issues:
        with st.expander(f"数据加载过程中有 {len(catalog.issues)} 条说明"):
            st.markdown(bullet_list(catalog.issues), unsafe_allow_html=True)
