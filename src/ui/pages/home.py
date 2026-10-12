"""首页：产品定位、需求输入入口、快速开始与数据集概览。"""

from __future__ import annotations

import streamlit as st

from src import config
from src.data_loader import Catalog
from src.ui import components, state
from src.ui.pages.analysis import EXAMPLE_DEMAND
from src.ui.theme import bullet_list

#: 快速开始示例：(标题, 一句话说明, 需求原文, 类别显示名)。
#: 第四项必须与 `config.category_label()` 的输出完全一致，
#: 因为它是分析页类别下拉框的选项文本。
_QUICK_STARTS: list[tuple[str, str, str, str]] = [
    (
        "大学生买笔记本",
        "预算有限、要写代码、不想太重",
        EXAMPLE_DEMAND,
        "笔记本电脑",
    ),
    (
        "通勤降噪耳机",
        "地铁和自习室用，要挡住环境噪音",
        "想买一副通勤和自习用的耳机，预算 1000 元以内，"
        "最看重降噪和续航，音质一般就行。",
        "耳机",
    ),
    (
        "宿舍用静音键盘",
        "怕吵到室友，但想要机械手感",
        "预算 500 元以内买一把机械键盘，主要用于编程和打字，"
        "宿舍用，必须静音，不吵到室友。",
        "键盘",
    ),
    (
        "给学生党的手机",
        "续航要撑一天，拍照别太差",
        "预算 2500 元买一部手机，主要日常使用和拍照，"
        "最看重续航，希望一天不用充电。",
        "手机",
    ),
]

#: 产品能力说明卡：(图标, 标题, 说明)
_CAPABILITIES: list[tuple[str, str, str]] = [
    ("file", "需求理解", "把口语化描述拆成预算、用途、核心需求与可妥协项"),
    ("filter", "智能筛选", "按你的条件过滤候选，超预算的商品单独标注而不是藏起来"),
    ("scale", "多维评分", "预算匹配、需求匹配、性能适配、性价比、便携性加权打分"),
    ("check", "决策建议", "每个分数都给出加分项与扣分项，结论可追溯到具体数据"),
]


def _go_to_analysis(payload: dict[str, str]) -> None:
    """把请求交给分析页，由它在控件创建之前消费。

    这里只记请求，不直接写分析页控件的键——那些控件属于另一个页面，
    直接写会埋下顺序依赖（Streamlit 不允许控件实例化后改它的键）。
    """
    st.session_state[state.KEY_PREFILL] = payload
    state.clear_analysis()
    state.request_page("智能分析")
    st.rerun()


def render(catalog: Catalog) -> None:
    components.page_header(
        "智购参谋",
        "基于 AI 的消费决策助手 —— 帮你在预算内买到真正适合自己的商品，"
        "并且告诉你这个结论是怎么得出来的。",
        right=components.runtime_chip(),
    )

    # --- 需求输入 ---------------------------------------------------------
    with st.container(border=False):
        st.text_area(
            "描述你的购买需求",
            key="zg_home_input",
            height=104,
            placeholder=f"例如：{EXAMPLE_DEMAND}",
            label_visibility="collapsed",
        )

    col_action, col_hint = st.columns([1, 4])
    with col_action:
        if st.button("开始分析", type="primary", use_container_width=True):
            text = st.session_state.get("zg_home_input", "").strip()
            if text:
                _go_to_analysis({"text": text, "category": "（不指定，在全部类别中检索）"})
            else:
                state.clear_analysis()
                state.request_page("智能分析")
                st.rerun()
    with col_hint:
        st.markdown(
            '<div class="zg-caption" style="padding-top:9px">'
            "没有头绪也可以直接点一个下面的示例，或者到「智能分析」页用选项填写。</div>",
            unsafe_allow_html=True,
        )

    # --- 统计 -------------------------------------------------------------
    st.write("")
    components.stat_row(
        [
            ("tag", f"{len(catalog)}", "件演示商品"),
            ("grid", f"{len(catalog.present_categories())}", "个商品类别"),
            ("bookmark", f"{len(catalog.brands())}", "个品牌"),
            ("scale", f"{len(config.DIMENSION_LABELS)}", "项评分维度"),
        ]
    )

    # --- 产品能力 ---------------------------------------------------------
    components.section_title("它能做什么")
    components.feature_row(_CAPABILITIES)

    # --- 快速开始 ---------------------------------------------------------
    components.section_title("快速开始")
    components.caption("点下面的示例直接体验，需求会自动填进分析页。")

    columns = st.columns(len(_QUICK_STARTS), gap="small")
    for column, (title, blurb, text, category) in zip(
        columns, _QUICK_STARTS, strict=True
    ):
        with column:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.markdown(
                    f'<div class="zg-caption" style="min-height:44px">{blurb}</div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    "用这个示例",
                    key=f"quick_{title}",
                    use_container_width=True,
                ):
                    _go_to_analysis({"text": text, "category": category})

    # --- 边界说明 ---------------------------------------------------------
    components.section_title("它不做什么")
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown(
            bullet_list(
                [
                    "不接入真实电商平台，不提供实时价格、库存或销量",
                    "不伪造用户评价、销量或市场口碑",
                    "不做支付、下单、购物车等交易环节",
                ],
                tone="con",
            ),
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            bullet_list(
                [
                    "全部商品均为演示数据，不能作为真实购买依据",
                    "「系统匹配评分」衡量的是与你需求的匹配程度，"
                    "不是用户评分、销量排名或市场口碑",
                ],
                tone="con",
            ),
            unsafe_allow_html=True,
        )

    # --- 数据集 -----------------------------------------------------------
    components.section_title("当前商品数据集")
    components.facts_block(
        [
            ("数据集", catalog.dataset_name or "未命名"),
            ("商品数量", f"{len(catalog)} 件"),
            (
                "覆盖类别",
                "、".join(config.category_label(c) for c in catalog.present_categories()),
            ),
            ("数据更新", catalog.dataset_updated_at or "未标注"),
        ]
    )

    if catalog.disclaimer:
        st.write("")
        components.show_notice(catalog.disclaimer, "warn")

    if catalog.issues:
        with st.expander(f"数据加载过程中有 {len(catalog.issues)} 条说明"):
            st.markdown(bullet_list(catalog.issues), unsafe_allow_html=True)
