"""智能分析页：需求输入 → 筛选排序 → 评分与推荐结果。"""

from __future__ import annotations

import streamlit as st

from src import config
from src.data_loader import Catalog
from src.demand_parser import (
    AVAILABLE_CORE_NEEDS,
    AVAILABLE_USE_CASES,
    Demand,
    detect_unsupported_category,
    follow_up_questions,
    merge_demand,
    parse_budget_value,
    parse_demand,
    unsupported_category_message,
)
from src.errors import EmptyDemand, ZhigouError, to_user_message
from src.recommender import recommend
from src.ui import components, state

#: 首页「快速开始」与输入框占位符共用的示例句。
EXAMPLE_DEMAND = (
    "我是一名大学生，预算 3000 元，想买一台主要用于 Python 编程、"
    "日常学习和偶尔玩游戏的笔记本电脑。我比较看重性能和性价比，"
    "不希望电脑太重。"
)

_NO_CATEGORY = "（不指定，在全部类别中检索）"

#: 分析页输入控件绑定的 session_state 键。重置与预填都走这里，
#: 避免在两个地方各写一份键名、改一处漏一处。
_INPUT_KEYS = (
    "zg_input_text",
    "zg_input_budget",
    "zg_input_use_cases",
    "zg_input_core_needs",
    "zg_input_brands",
)
_CATEGORY_KEY = "zg_input_category"


def _apply_pending_inputs() -> None:
    """在控件创建**之前**处理预填与重置请求。

    必须在 `_render_inputs()` 之前调用。Streamlit 不允许在控件实例化后
    修改它绑定的 session_state 键，所以「清空条件」「快速开始」这类操作
    都不能就地改值，只能记请求、下一轮在这里消费。
    """
    if st.session_state.pop(state.KEY_RESET, False):
        for key in _INPUT_KEYS:
            st.session_state.pop(key, None)
        st.session_state[_CATEGORY_KEY] = _NO_CATEGORY

    prefill = st.session_state.pop(state.KEY_PREFILL, None)
    if prefill:
        st.session_state["zg_input_text"] = prefill.get("text", "")
        st.session_state[_CATEGORY_KEY] = prefill.get("category", _NO_CATEGORY)
        for key in _INPUT_KEYS[1:]:
            st.session_state[key] = [] if key != "zg_input_budget" else ""


# --------------------------------------------------------------------------
# 输入区
# --------------------------------------------------------------------------


def _category_options(catalog: Catalog) -> dict[str, str]:
    """返回 {界面显示名: 类别键} 的映射。"""
    mapping = {_NO_CATEGORY: ""}
    for key in catalog.present_categories():
        mapping[config.category_label(key)] = key
    return mapping


def _input_signature(
    raw_text: str,
    category: str,
    budget_raw: str,
    use_cases: list[str],
    core_needs: list[str],
    brands: list[str],
) -> str:
    """把当前输入揉成一个指纹，用来判断「条件改过但还没重新分析」。"""
    return repr(
        (
            raw_text.strip(),
            category,
            budget_raw.strip(),
            tuple(use_cases),
            tuple(core_needs),
            tuple(brands),
        )
    )


def _render_inputs(catalog: Catalog) -> None:
    components.section_title("描述你的购买需求")

    st.text_area(
        "用一句话说清楚你要买什么、预算多少、主要用来做什么",
        key="zg_input_text",
        height=118,
        placeholder=f"例如：{EXAMPLE_DEMAND}",
        help="尽量写清预算和用途；没提到的信息可以留空，系统会在下方补充询问。",
    )

    st.caption("也可以直接用下面的选项填写，选项的取值会覆盖上面的文字描述。")

    options = _category_options(catalog)
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("商品类别", options=list(options), key="zg_input_category")
    with col2:
        st.text_input(
            "预算（元）",
            key="zg_input_budget",
            placeholder="例如 3000，留空表示暂不限定",
            help="只接受数字。留空表示不限预算，结果会标注「未设定预算」。",
        )

    col3, col4 = st.columns(2)
    with col3:
        st.multiselect(
            "主要用途",
            options=list(AVAILABLE_USE_CASES),
            key="zg_input_use_cases",
            placeholder="可多选，留空表示不限定",
            help="选中的用途会与商品数据里的适用场景做匹配。",
        )
    with col4:
        st.multiselect(
            "比较看重",
            options=list(AVAILABLE_CORE_NEEDS),
            key="zg_input_core_needs",
            placeholder="可多选，留空表示不限定",
            help="这些会作为「核心需求」参与匹配度评分。",
        )

    brands = catalog.brands()
    if brands:
        st.multiselect(
            "品牌偏好（可留空）",
            options=brands,
            key="zg_input_brands",
            placeholder="不限品牌",
            help="选了品牌就只在该品牌内筛选；没有命中的话会给出放宽建议。",
        )


def _current_signature() -> str:
    return _input_signature(
        st.session_state.get("zg_input_text", ""),
        st.session_state.get(_CATEGORY_KEY, _NO_CATEGORY),
        st.session_state.get("zg_input_budget", ""),
        st.session_state.get("zg_input_use_cases", []),
        st.session_state.get("zg_input_core_needs", []),
        st.session_state.get("zg_input_brands", []),
    )


# --------------------------------------------------------------------------
# 分析
# --------------------------------------------------------------------------


def _run_analysis(catalog: Catalog) -> None:
    """点「开始分析」时执行一次。所有失败都转成中文文案存进会话状态。"""
    state.clear_analysis()

    raw_text = st.session_state.get("zg_input_text", "")
    category_label = st.session_state.get("zg_input_category", _NO_CATEGORY)
    category = _category_options(catalog).get(category_label, "")
    budget_raw = st.session_state.get("zg_input_budget", "")
    use_cases = list(st.session_state.get("zg_input_use_cases", []))
    core_needs = list(st.session_state.get("zg_input_core_needs", []))
    brands = list(st.session_state.get("zg_input_brands", []))

    # 文字和结构化控件都没填 → 直接拒绝，连解析都不必
    if (
        not raw_text.strip()
        and not category
        and not str(budget_raw).strip()
        and not use_cases
        and not core_needs
    ):
        state.put(state.KEY_ERROR, to_user_message(EmptyDemand()))
        return

    # 用户说的是数据里没有的类别（平板、相机…）→ 明确说不支持，
    # 而不是当成「没提类别」然后跨类别乱推荐
    term = detect_unsupported_category(raw_text)
    if term:
        state.put(state.KEY_ERROR, unsupported_category_message(term))
        return

    try:
        parsed = parse_demand(raw_text, known_brands=catalog.brands()) if raw_text.strip() else Demand()
        budget = parse_budget_value(budget_raw)
        structured = Demand(
            category=category,
            budget=budget,
            use_cases=use_cases,
            core_needs=core_needs,
            brand_preferences=brands,
        )
        demand = merge_demand(structured, parsed) if raw_text.strip() else structured
    except ZhigouError as exc:
        state.put(state.KEY_ERROR, to_user_message(exc))
        return

    # 关键字段缺失 → 定向追问，不进入筛选
    questions = follow_up_questions(demand)
    if questions:
        state.put(state.KEY_DEMAND, demand)
        state.put(state.KEY_FOLLOWUPS, questions)
        return

    result = recommend(catalog, demand)
    state.put(state.KEY_DEMAND, demand)
    state.put(state.KEY_RESULT, result)
    state.put(state.KEY_SIGNATURE, _current_signature())


# --------------------------------------------------------------------------
# 结果渲染
# --------------------------------------------------------------------------


def _render_demand_summary(demand: Demand) -> None:
    components.section_title("需求摘要")
    pairs = [
        ("商品类别", demand.category_label or "未指定"),
        ("预算", demand.budget_label),
        ("使用场景", "、".join(demand.use_cases) or "未提供"),
        ("核心需求", "、".join(demand.core_needs) or "未提供"),
        ("品牌偏好", "、".join(demand.brand_preferences) or "未限定"),
        ("硬性限制", "、".join(demand.hard_constraints) or "无"),
        ("可妥协项", "、".join(demand.compromises) or "未说明"),
    ]
    st.markdown(components.facts(pairs), unsafe_allow_html=True)

    if demand.raw_text:
        with st.expander("原始输入"):
            st.write(demand.raw_text)


def _render_recommendations(result) -> None:
    components.section_title(f"预算内推荐（{len(result.within_budget)} 件）")

    if not result.within_budget:
        components.show_notice(
            "在你给出的条件下没有任何预算内的商品。下面列出了超出预算的候选，"
            "以及具体可以放宽哪一项。",
            "warn",
        )
    else:
        for index, item in enumerate(result.within_budget):
            components.render_product_card(
                item.product,
                item.score,
                item.budget_label,
                rank=index + 1,
                highlight=index == 0,
                expanded=index == 0,
            )

    if result.over_budget:
        components.section_title(f"超出预算的候选（{len(result.over_budget)} 件）")
        components.caption(
            "以下商品超出你设定的预算，已逐条标出超出金额。它们不计入上面的推荐排序，"
            "仅供你判断「加多少钱能买到什么」。"
        )
        for item in result.over_budget:
            components.render_product_card(
                item.product, item.score, item.budget_label
            )

    if result.relaxations:
        components.section_title("放宽条件的建议")
        st.markdown(
            components.bullet_list(result.relaxations), unsafe_allow_html=True
        )


def _render_results() -> None:
    error = state.get(state.KEY_ERROR)
    if error:
        components.show_notice(error, "stop")
        return

    followups = state.get(state.KEY_FOLLOWUPS)
    if followups:
        components.section_title("还需要一点信息")
        components.caption("已经提供的信息不会再问一遍，只补缺口。")
        st.markdown(components.bullet_list(followups), unsafe_allow_html=True)
        return

    demand = state.get(state.KEY_DEMAND)
    result = state.get(state.KEY_RESULT)
    if demand is None or result is None:
        components.empty_state(
            "还没有分析结果。填好上面的需求，点「开始分析」即可看到推荐与评分。"
        )
        return

    if state.get(state.KEY_SIGNATURE) != _current_signature():
        components.show_notice(
            "你已经修改了输入条件。当前显示的是上一次分析的结果，"
            "点「开始分析」按新条件重新计算。",
            "warn",
        )

    _render_demand_summary(demand)

    components.section_title("筛选与匹配情况")
    pairs = [
        ("候选商品", f"{result.candidate_count} 件"),
        ("预算内", f"{len(result.within_budget)} 件"),
        ("超出预算", f"{len(result.over_budget)} 件"),
        ("排序依据", f"{config.SCORE_DISPLAY_NAME}（不是按价格排序）"),
    ]
    st.markdown(components.facts(pairs), unsafe_allow_html=True)

    if result.notes:
        st.write("")
        components.render_notes(result.notes)

    _render_recommendations(result)


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def render(catalog: Catalog) -> None:
    # 必须在任何输入控件创建之前执行
    _apply_pending_inputs()

    components.page_header(
        "智能分析",
        "描述你的购买需求，系统会筛选候选商品、按需求匹配度打分排序，"
        "并把评分怎么算出来的逐项摊开给你看。",
    )

    _render_inputs(catalog)

    st.write("")
    left, right = st.columns([1, 4])
    with left:
        clicked = st.button("开始分析", type="primary", use_container_width=True)
    with right:
        if st.button("清空条件", use_container_width=False):
            # 只记请求——此刻输入控件都已创建，就地清空会抛异常
            st.session_state[state.KEY_RESET] = True
            state.clear_analysis()
            st.rerun()

    if clicked:
        # 处理中给个明确反馈，避免用户以为点了没反应而反复点击
        with st.spinner("正在解析需求、筛选商品并计算匹配度…"):
            _run_analysis(catalog)

    st.write("")
    _render_results()
