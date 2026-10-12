"""首页：产品介绍、快速开始与数据概览。"""

from __future__ import annotations

import streamlit as st

from src import config
from src.data_loader import Catalog
from src.ui import components, state
from src.ui.pages.analysis import EXAMPLE_DEMAND
from src.ui.theme import bullet_list, esc, facts

#: 快速开始按钮：点一下就把示例填进分析页。
#: 第四个元素必须与 `config.category_label()` 的输出完全一致，
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
        "主要在地铁和自习室用，要能挡住环境噪音",
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
]


def _apply_quick_start(text: str, category_label: str) -> None:
    """把示例填进分析页的输入控件，并跳转过去。

    这里**只记请求，不直接写控件的键**——那些控件属于分析页，
    在此刻的首页渲染里虽然还没创建，但直接写会埋下顺序依赖。
    统一交给分析页在创建控件之前消费（见 `analysis._apply_pending_inputs`）。
    """
    st.session_state[state.KEY_PREFILL] = {
        "text": text,
        "category": category_label,
    }
    state.clear_analysis()
    state.request_page("智能分析")
    st.rerun()


def render(catalog: Catalog) -> None:
    mode, mode_detail = state.current_mode()

    components.page_header(
        "智购参谋",
        "基于大模型的智能消费决策助手 —— 帮你把「想买什么」变成"
        "「在预算内买哪一件更合适」，并且告诉你这个结论是怎么得出来的。",
    )

    st.markdown(
        f'<div>{components.runtime_badge()}</div>',
        unsafe_allow_html=True,
    )

    # --- 定位说明 ---------------------------------------------------------
    components.section_title("它解决什么问题")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="zg-caption">它做什么</div>', unsafe_allow_html=True)
        st.markdown(
            bullet_list(
                [
                    "听懂你的自然语言需求：预算、用途、看重什么、能妥协什么",
                    "在候选商品里筛选，按「和你需求的匹配程度」排序，而不是按价格或广告位",
                    "至少三件商品的横向比较，价格、参数、优缺点、预算匹配一目了然",
                    "每个推荐都给出评分构成、加分项、扣分项，结论可以追溯到具体数据",
                    "调整预算或偏好后立即重算，并保存分析记录供你回头对比",
                ]
            ),
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown('<div class="zg-caption">它不做什么</div>', unsafe_allow_html=True)
        st.markdown(
            bullet_list(
                [
                    "不接入真实电商平台，不提供实时价格、库存或销量",
                    "不伪造用户评价、销量或市场口碑",
                    "展示的评分是「系统匹配评分」，衡量的是商品与你需求的匹配度，"
                    "不是市场口碑排名",
                    "当前全部商品均为演示数据，不能作为真实购买依据",
                ],
                tone="con",
            ),
            unsafe_allow_html=True,
        )

    # --- 快速开始 ---------------------------------------------------------
    components.section_title("快速开始")
    components.caption("点下面的示例直接体验，或到「智能分析」页自己描述需求。")

    columns = st.columns(len(_QUICK_STARTS))
    for column, (title, blurb, text, category) in zip(columns, _QUICK_STARTS, strict=True):
        with column:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.markdown(
                    f'<div class="zg-caption">{esc(blurb)}</div>',
                    unsafe_allow_html=True,
                )
                if st.button("用这个示例", key=f"quick_{title}", use_container_width=True):
                    _apply_quick_start(text, category)

    # --- 数据概览 ---------------------------------------------------------
    components.section_title("当前商品数据集")
    pairs = [
        ("数据集", catalog.dataset_name or "未命名"),
        ("商品数量", f"{len(catalog)} 件"),
        ("覆盖类别", "、".join(config.category_label(c) for c in catalog.present_categories())),
        ("品牌数量", f"{len(catalog.brands())} 个"),
        ("数据更新", catalog.dataset_updated_at or "未标注"),
        ("运行模式", f"{mode}（{mode_detail}）"),
    ]
    st.markdown(facts(pairs), unsafe_allow_html=True)

    if catalog.disclaimer:
        st.write("")
        components.show_notice(catalog.disclaimer, "warn")

    if catalog.issues:
        with st.expander(f"数据加载过程中有 {len(catalog.issues)} 条说明"):
            st.markdown(bullet_list(catalog.issues), unsafe_allow_html=True)
