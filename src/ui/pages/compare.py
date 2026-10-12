"""商品比较页：多商品横向对比。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import config
from src.comparison import MISSING_TEXT, compare
from src.data_loader import Catalog
from src.demand_parser import Demand
from src.errors import ZhigouError, to_user_message
from src.scoring import score_all
from src.ui import components, state
from src.ui.theme import bullet_list

_PICK_KEY = "zg_compare_pick"
_MIRROR_NS = "compare_pick"
_PICK_DEFAULTS = {_PICK_KEY: []}

#: 表格里长文本的截断长度。
#: 5 件商品同屏时每列只有 ~230px，优缺点的完整文本有 60 字以上，
#: 不截断的话单元格会被切得只剩开头几个字，还不如主动截断加省略号。
#: 完整内容在下面的「优缺点对照」里平铺展示，不用逐个点开。
_PROSE_LIMIT = 30
_USECASE_LIMIT = 18

#: 需要截断的行
_PROSE_ROWS = {"优点", "缺点"}
_USECASE_ROWS = {"适用场景"}


def _label(product) -> str:
    return f"{product.name or product.id}（{product.price_label}）"


def _shorten(text: str, limit: int) -> str:
    """超长就截断加省略号。占位文案与短文本原样保留。"""
    if text == MISSING_TEXT or len(text) <= limit:
        return text
    return text[:limit] + "…"


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


def _render_picker(catalog: Catalog) -> list:
    """商品选择区，返回选中的商品。"""
    by_label = {_label(p): p.id for p in catalog.products}

    col1, col2 = st.columns([3, 1])
    with col1:
        chosen = st.multiselect(
            "选择要比较的商品",
            options=list(by_label),
            key=_PICK_KEY,
            max_selections=config.MAX_COMPARE_COUNT,
            placeholder=f"至少选 {config.MIN_COMPARE_COUNT} 件，最多 {config.MAX_COMPARE_COUNT} 件",
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
    return [catalog.get(by_label[label]) for label in chosen]


def _shorten_prose_cells(records: list[dict]) -> None:
    """就地截断表格里的长文本单元格。"""
    for record in records:
        label = record["比较维度"]
        if label in _PROSE_ROWS:
            limit = _PROSE_LIMIT
        elif label in _USECASE_ROWS:
            limit = _USECASE_LIMIT
        else:
            continue
        for key in list(record):
            if key != "比较维度":
                record[key] = _shorten(record[key], limit)


def render(catalog: Catalog) -> None:
    _apply_pending_pick()

    components.page_header(
        "商品比较",
        f"选 {config.MIN_COMPARE_COUNT} 到 {config.MAX_COMPARE_COUNT} 件商品横向对比，"
        "价格、核心参数、适用场景、优缺点和预算匹配度放在同一张表里看。",
    )

    demand = state.get(state.KEY_DEMAND) or Demand()
    products = _render_picker(catalog)

    if len(products) < config.MIN_COMPARE_COUNT:
        st.write("")
        components.empty_state(
            f"还需要选择 {config.MIN_COMPARE_COUNT - len(products)} 件商品。"
            f"少于 {config.MIN_COMPARE_COUNT} 件无法进行横向比较。",
            icon_name="compare",
        )
        return

    try:
        table = compare(products, demand)
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    scores = score_all(products, demand)
    budget_row = next(row for row in table.rows if row.label == "预算匹配")
    budgets = {
        product.id: budget_row.values[table.products.index(product)]
        for product in products
    }

    # --- 商品概览 ---------------------------------------------------------
    components.section_title("参与比较的商品", len(products))
    st.markdown(
        components.compare_overview(products, budgets=budgets, scores=scores),
        unsafe_allow_html=True,
    )

    # --- 比较表 -----------------------------------------------------------
    components.section_title("横向比较")

    records = table.to_records()
    _shorten_prose_cells(records)

    # 匹配度作为额外一行。comparison 模块只负责商品数据本身，
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
        height=min(800, 70 + 34 * len(records)),
    )
    if len(products) >= config.MAX_COMPARE_COUNT:
        components.caption(
            f"同时比较 {len(products)} 件时表格较宽，单元格里的优缺点只显示开头，"
            "完整内容在下面的「优缺点对照」里。表格内可以左右滚动。"
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

    # --- 优缺点（平铺，不用逐个点开）--------------------------------------
    components.section_title("优缺点对照")
    components.caption("上面那张表用来横向比参数，这里竖着看每件的取舍。")
    st.markdown(components.pros_cons_grid(products), unsafe_allow_html=True)

    st.write("")
    components.caption(
        "比较结果同样基于演示数据，价格不是实时价格，参数不是厂商实测值。"
    )
