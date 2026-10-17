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
_CATEGORY_KEY = "zg_compare_category"
#: 上一次渲染时选中的类别（普通会话键）。用于识别「用户换了类别」，
#: 换类别时清掉上一个类别的已选商品——它们已经不在候选里了。
_LAST_CATEGORY_KEY = "zg_compare_last_category"
_MIRROR_NS = "compare_pick"
_PICK_DEFAULTS = {_PICK_KEY: [], _CATEGORY_KEY: ""}

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
        st.session_state[_CATEGORY_KEY] = requested["category"]
        st.session_state[_PICK_KEY] = list(requested["labels"])
        # 预填自带类别：同步「上次类别」，否则下面的换类别检测会把刚填好的
        # 选择当成上一个类别的残留清掉。
        st.session_state[_LAST_CATEGORY_KEY] = requested["category"]
        return
    # 切页会清掉控件状态，这里恢复用户之前选好的类别与商品
    state.restore_widgets(_MIRROR_NS, _PICK_DEFAULTS)


def _request_fill_from_analysis() -> None:
    """用上一次分析的推荐结果填充选择框，省得手动一件件挑。

    分析未指定类别时，推荐结果可能跨类别（例如「3000 元买什么」）。
    比较只允许同类，所以这里**只取首选所在的类别**，保证预填进来的
    是一组可比较商品。
    """
    result = state.get(state.KEY_RESULT)
    if result is None:
        return
    items = result.all_items()
    if not items:
        return
    leading_category = items[0].product.category
    same_category = [item for item in items if item.product.category == leading_category]
    picks = same_category[: config.MAX_COMPARE_COUNT]
    st.session_state[state.KEY_COMPARE_PREFILL] = {
        "category": leading_category,
        "labels": [_label(item.product) for item in picks],
    }
    st.rerun()


def _render_picker(catalog: Catalog) -> list:
    """选择区：先选商品类别，再在该类别里选商品。

    比较只在同类之间有意义的，所以这里**用「类别 → 商品」两步选择**
    从结构上保证同类：候选里根本不会出现其他类别的商品。

    不用「选中第一件后自动收窄候选」的做法：Streamlit 的多选框在
    选项列表变化时会丢弃已选值，收窄会把用户刚选的那件也清掉。

    返回选中的商品列表。
    """
    categories = catalog.present_categories()
    label_by_category = {config.category_label(key): key for key in categories}

    # 类别选择。镜像里恢复出来的类别可能已不在数据集中（数据换了），清掉走默认。
    if st.session_state.get(_CATEGORY_KEY) not in label_by_category:
        st.session_state.pop(_CATEGORY_KEY, None)

    col_category, col_items, col_action = st.columns([1.4, 2.6, 1.1])
    with col_category:
        st.write("")
        category_label = st.selectbox(
            "商品类别", options=list(label_by_category), key=_CATEGORY_KEY
        )
    category = label_by_category[category_label]

    # 换类别时清掉上一个类别的已选商品（此刻多选框还没创建，可以安全写它的键）
    previous_category = st.session_state.get(_LAST_CATEGORY_KEY)
    if previous_category is not None and previous_category != category:
        st.session_state[_PICK_KEY] = []
    st.session_state[_LAST_CATEGORY_KEY] = category

    options = {_label(p): p.id for p in catalog.by_category(category)}

    with col_items:
        st.write("")
        chosen = st.multiselect(
            "选择要比较的商品",
            options=list(options),
            key=_PICK_KEY,
            max_selections=config.MAX_COMPARE_COUNT,
            placeholder=(
                f"在本类别内至少选 {config.MIN_COMPARE_COUNT} 件、"
                f"最多 {config.MAX_COMPARE_COUNT} 件"
            ),
        )
    with col_action:
        st.write("")
        st.write("")
        if state.get(state.KEY_RESULT) is not None:
            if st.button("用上次分析的推荐", width="stretch"):
                _request_fill_from_analysis()
        else:
            st.markdown(
                '<div class="zg-caption">先在「智能分析」页做一次分析，'
                "这里就能一键填入推荐结果。</div>",
                unsafe_allow_html=True,
            )

    state.snapshot_widgets(_MIRROR_NS, _PICK_DEFAULTS)
    # 防御：万一某个标签在当前候选里不存在（例如数据文件在两次运行之间换了），
    # 丢掉那一项而不是整页报错。
    return [catalog.get(options[label]) for label in chosen if label in options]


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
        f"在同一类别内选 {config.MIN_COMPARE_COUNT} 到 {config.MAX_COMPARE_COUNT} 件商品"
        "横向对比，价格、核心参数、适用场景、优缺点和预算匹配度放在同一张表里看。"
        "先选商品类别，再从该类别的商品里挑。",
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
        width="stretch",
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

        # 字段缺失之外的另一类问题：字段都在，但互相打架。
        for product in products:
            issues = product.data_issues
            if not issues:
                continue
            detail = "；".join(issue.reason for issue in issues)
            components.show_notice(
                f"「{product.name or product.id}」{components.DATA_ISSUE_LABEL}：{detail}",
                "warn",
            )

    # --- 优缺点（平铺，不用逐个点开）--------------------------------------
    components.section_title("优缺点对照")
    components.caption("上面那张表用来横向比参数，这里竖着看每件的取舍。")
    st.markdown(components.pros_cons_grid(products), unsafe_allow_html=True)

    st.write("")
    components.caption(
        "比较同样基于上述数据口径：价格是采集时的参考价、不是实时价格，"
        "参数经简化、未逐条核验，也不是厂商实测值。"
    )
