"""商品比较页：多商品横向对比。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import config
from src.comparison import compare
from src.data_loader import Catalog
from src.demand_parser import Demand
from src.errors import ZhigouError, to_user_message
from src.scoring import score_all
from src.ui import components, state
from src.ui.theme import bullet_list

_PICK_KEY = "zg_compare_pick"
_MIRROR_NS = "compare_pick"
_PICK_DEFAULTS = {_PICK_KEY: []}


def _label(product) -> str:
    return f"{product.name or product.id}（{product.price_label}）"


def _apply_pending_pick() -> None:
    """在商品多选框创建**之前**消费填充请求。

    和导航、预填是同一个道理：控件一旦实例化，就再也不能改它绑定的键。
    所以按钮只记请求，真正的赋值挪到这里。
    """
    requested = st.session_state.pop(state.KEY_COMPARE_PREFILL, None)
    if requested is not None:
        st.session_state[_PICK_KEY] = requested
        return
    # 切页会清掉控件状态，这里恢复用户之前选好的商品
    state.restore_widgets(_MIRROR_NS, _PICK_DEFAULTS)


def _request_fill_from_analysis() -> None:
    """用上一次分析的推荐结果填充选择框，省得手动一件件挑。"""
    result = state.get(state.KEY_RESULT)
    if result is None:
        return
    picks = result.all_items()[: config.MAX_COMPARE_COUNT]
    st.session_state[state.KEY_COMPARE_PREFILL] = [_label(item.product) for item in picks]
    st.rerun()


def render(catalog: Catalog) -> None:
    _apply_pending_pick()

    components.page_header(
        "商品比较",
        f"选 {config.MIN_COMPARE_COUNT} 到 {config.MAX_COMPARE_COUNT} 件商品横向对比，"
        "价格、核心参数、适用场景、优缺点和预算匹配度放在同一张表里看。",
    )

    demand = state.get(state.KEY_DEMAND) or Demand()
    by_label = {_label(p): p.id for p in catalog.products}

    col1, col2 = st.columns([3, 1])
    with col1:
        chosen = st.multiselect(
            "选择要比较的商品",
            options=list(by_label),
            key=_PICK_KEY,
            max_selections=config.MAX_COMPARE_COUNT,
            placeholder=f"至少选 {config.MIN_COMPARE_COUNT} 件",
        )
    with col2:
        st.write("")
        st.write("")
        if state.get(state.KEY_RESULT) is not None:
            if st.button("用上次分析的推荐", use_container_width=True):
                _request_fill_from_analysis()
        else:
            st.markdown(
                '<div class="zg-caption">先在「智能分析」页做一次分析，'
                "这里就能一键填入推荐结果。</div>",
                unsafe_allow_html=True,
            )

    state.snapshot_widgets(_MIRROR_NS, _PICK_DEFAULTS)

    if len(chosen) < config.MIN_COMPARE_COUNT:
        st.write("")
        components.empty_state(
            f"还需要选择 {config.MIN_COMPARE_COUNT - len(chosen)} 件商品。"
            f"少于 {config.MIN_COMPARE_COUNT} 件无法进行横向比较。",
            icon_name="compare",
        )
        return

    products = [catalog.get(by_label[label]) for label in chosen]

    try:
        table = compare(products, demand)
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    # --- 商品概览 ---------------------------------------------------------
    components.section_title("参与比较的商品", len(products))
    columns = st.columns(len(products), gap="small")
    scores = score_all(products, demand)
    for column, product in zip(columns, products, strict=True):
        with column:
            budget_row = next(
                row for row in table.rows if row.label == "预算匹配"
            )
            budget_label = budget_row.values[table.products.index(product)]
            score = scores[product.id]
            st.markdown(
                components.product_mini(product, budget_label=budget_label)
                + f'<div style="margin:-4px 0 0 2px">'
                f'<div class="zg-price">{score.total:.0f}'
                f'<small>/100</small></div>'
                f'<div style="margin:3px 0">{components.stars(score.total)}</div>'
                f'<div class="zg-score-name">{config.SCORE_DISPLAY_NAME}</div></div>',
                unsafe_allow_html=True,
            )

    # --- 比较表 -----------------------------------------------------------
    components.section_title("横向比较")

    records = table.to_records()
    # 把匹配度作为额外一行加进表里。comparison 模块只负责商品数据本身，
    # 评分是另一条链路，不该混进业务数据结构里。
    records.append(
        {
            "比较维度": config.SCORE_DISPLAY_NAME,
            **{p.name: f"{scores[p.id].total:.0f} / 100" for p in products},
        }
    )

    frame = pd.DataFrame(records).set_index("比较维度")
    st.dataframe(
        frame,
        use_container_width=True,
        height=min(780, 70 + 36 * len(records)),
    )

    # --- 差异与完整度 -----------------------------------------------------
    st.write("")
    col3, col4 = st.columns(2, gap="large")
    with col3:
        components.section_title("存在差异的维度")
        varying = [row.label for row in table.rows if row.varies]
        st.markdown(
            f'<div class="zg-card is-flat">{bullet_list(varying)}</div>',
            unsafe_allow_html=True,
        )
    with col4:
        components.section_title("数据完整度")
        if table.missing_cells:
            components.show_notice(
                f"表中有 {table.missing_cells} 个单元格缺少数据，已标注为「信息缺失」，"
                "没有用其他商品的取值填充。",
                "warn",
            )
        else:
            components.show_notice("所选商品的数据字段完整。", "ok")

    # --- 优缺点 -----------------------------------------------------------
    components.section_title("逐个看优缺点")
    for product in products:
        with st.expander(f"{product.name} 的优点与不足"):
            left, right = st.columns(2)
            with left:
                st.markdown('<div class="zg-caption">优点</div>', unsafe_allow_html=True)
                st.markdown(bullet_list(product.pros), unsafe_allow_html=True)
            with right:
                st.markdown('<div class="zg-caption">缺点</div>', unsafe_allow_html=True)
                st.markdown(bullet_list(product.cons, tone="con"), unsafe_allow_html=True)

    state.snapshot_widgets(_MIRROR_NS, _PICK_DEFAULTS)

    st.write("")
    components.caption(
        "比较结果同样基于演示数据，价格不是实时价格，参数不是厂商实测值。"
    )
