"""智能分析页：需求输入 → 筛选排序 → 评分与推荐结果。"""

from __future__ import annotations

import streamlit as st

from src import config, settings
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
from src.ui.theme import bullet_list, facts

#: 首页「快速开始」与输入框占位符共用的示例句。
EXAMPLE_DEMAND = (
    "我是一名大学生，预算 3000 元，想买一台主要用于 Python 编程、"
    "日常学习和偶尔玩游戏的笔记本电脑。我比较看重性能和性价比，"
    "不希望电脑太重。"
)

_NO_CATEGORY = "（不指定，在全部类别中检索）"

#: 输入控件绑定的 session_state 键。重置与预填都走这里，
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
        st.session_state["zg_input_budget"] = ""
        st.session_state["zg_input_use_cases"] = []
        st.session_state["zg_input_core_needs"] = []
        st.session_state["zg_input_brands"] = []


def _category_options(catalog: Catalog) -> dict[str, str]:
    """返回 {界面显示名: 类别键} 的映射。"""
    mapping = {_NO_CATEGORY: ""}
    for key in catalog.present_categories():
        mapping[config.category_label(key)] = key
    return mapping


def _input_signature() -> str:
    """把当前输入揉成一个指纹，用来判断「条件改过但还没重新分析」。"""
    return repr(
        (
            st.session_state.get("zg_input_text", "").strip(),
            st.session_state.get(_CATEGORY_KEY, _NO_CATEGORY),
            st.session_state.get("zg_input_budget", "").strip(),
            tuple(st.session_state.get("zg_input_use_cases", [])),
            tuple(st.session_state.get("zg_input_core_needs", [])),
            tuple(st.session_state.get("zg_input_brands", [])),
        )
    )


# --------------------------------------------------------------------------
# 输入区
# --------------------------------------------------------------------------


def _render_inputs(catalog: Catalog) -> None:
    components.section_title("描述你的购买需求")

    st.text_area(
        "用一句话说清楚你要买什么、预算多少、主要用来做什么",
        key="zg_input_text",
        height=112,
        placeholder=f"例如：{EXAMPLE_DEMAND}",
        help="尽量写清预算和用途；没提到的信息可以留空，系统会在下方补充询问。",
    )

    st.caption("也可以直接用下面的选项填写。选项填了的内容会覆盖上面的文字描述。")

    options = _category_options(catalog)
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("商品类别", options=list(options), key=_CATEGORY_KEY)
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


# --------------------------------------------------------------------------
# 分析
# --------------------------------------------------------------------------


def _run_analysis(catalog: Catalog) -> None:
    """点「开始分析」时执行一次。所有失败都转成中文文案存进会话状态。"""
    state.clear_analysis()

    raw_text = st.session_state.get("zg_input_text", "")
    category = _category_options(catalog).get(
        st.session_state.get(_CATEGORY_KEY, _NO_CATEGORY), ""
    )
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
        parsed = (
            parse_demand(raw_text, known_brands=catalog.brands())
            if raw_text.strip()
            else Demand()
        )
        structured = Demand(
            category=category,
            budget=parse_budget_value(budget_raw),
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

    # 个人设置里的偏好作为默认值并入（不覆盖本次手填的内容）
    prefs = settings.load_preferences()
    applied = settings.apply_preferences(prefs, demand)

    # 提示只在偏好**确实改变了什么**的时候给。
    # 不能只看 auto_apply 开关——它默认就是 True，那样每个人每次都会看到
    # 「已自动带上偏好」，哪怕他一项都没设过，等于在说假话。
    contributed = bool(
        set(applied.core_needs) - set(demand.core_needs)
        or (not demand.brand_preferences and applied.brand_preferences)
        or (prefs.auto_apply and not prefs.show_over_budget)
    )

    result = recommend(catalog, applied)
    if not prefs.show_over_budget:
        result.over_budget = []

    state.put(state.KEY_DEMAND, applied)
    state.put(state.KEY_RESULT, result)
    state.put(state.KEY_SIGNATURE, _input_signature())
    state.put("zg_prefs_applied", contributed)


# --------------------------------------------------------------------------
# 结果渲染
# --------------------------------------------------------------------------


def _summary_pairs(demand: Demand) -> list[tuple[str, str]]:
    return [
        ("商品类别", demand.category_label or "未指定"),
        ("预算", demand.budget_label),
        ("使用场景", "、".join(demand.use_cases) or "未提供"),
        ("核心需求", "、".join(demand.core_needs) or "未提供"),
        ("品牌偏好", "、".join(demand.brand_preferences) or "未限定"),
        ("硬性限制", "、".join(demand.hard_constraints) or "无"),
        ("可妥协项", "、".join(demand.compromises) or "未说明"),
    ]


def _render_left_column(demand: Demand, result) -> None:
    components.section_title("需求摘要")
    st.markdown(
        f'<div class="zg-card is-flat">{facts(_summary_pairs(demand))}</div>',
        unsafe_allow_html=True,
    )

    # 预算匹配度：候选中落在预算内的比例。真实可算，不是编的指标。
    if result.candidate_count:
        ratio = len(result.within_budget) / result.candidate_count * 100
        if len(result.within_budget) == 0:
            desc = "当前条件下没有商品落在预算内"
        elif ratio >= 50:
            desc = "推荐商品多数在预算范围内"
        else:
            desc = "预算偏紧，多数候选超出预算"
        st.write("")
        st.markdown(
            f'<div class="zg-card is-flat">{components.score_ring(ratio, "预算匹配度", desc)}</div>',
            unsafe_allow_html=True,
        )

    st.write("")
    components.section_title("筛选情况")
    st.markdown(
        f'<div class="zg-card is-flat">{facts([
            ("候选商品", f"{result.candidate_count} 件"),
            ("预算内", f"{len(result.within_budget)} 件"),
            ("超出预算", f"{len(result.over_budget)} 件"),
            ("排序依据", config.SCORE_DISPLAY_NAME),
        ])}</div>',
        unsafe_allow_html=True,
    )
    components.caption("排序看的是需求匹配度，不是价格高低。")

    if demand.raw_text:
        with st.expander("原始输入"):
            st.write(demand.raw_text)


def _render_right_column(result) -> None:
    total = len(result.within_budget)

    if total:
        components.section_title("为你推荐", total)
        components.caption(
            "按需求匹配度排序，第 1 名为当前条件下的首选。"
            "展开任意一条可以看到评分是怎么算出来的。"
        )
        for index, item in enumerate(result.within_budget):
            components.render_product_row(
                item.product,
                item.score,
                item.budget_label,
                rank=index + 1,
                highlight=index == 0,
                expanded=index == 0,
            )
    else:
        components.section_title("预算内的推荐", 0)
        components.empty_state(
            "在你给出的条件下没有任何预算内的商品。"
            "右侧下方列出了超出预算的候选，以及具体可以放宽哪一项。",
            icon_name="alert",
        )

    if result.notes:
        st.write("")
        components.render_notes(result.notes)

    if result.over_budget:
        components.section_title("超出预算的候选", len(result.over_budget))
        components.caption(
            "以下商品超出你设定的预算，已逐条标出超出金额。"
            "它们不在上面的排序里，只用来判断「加多少钱能买到什么」。"
        )
        for item in result.over_budget:
            components.render_product_row(
                item.product, item.score, item.budget_label
            )

    if result.relaxations:
        components.section_title("放宽条件的建议")
        st.markdown(
            f'<div class="zg-card is-flat">{bullet_list(result.relaxations)}</div>',
            unsafe_allow_html=True,
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
        st.markdown(
            f'<div class="zg-card is-flat">{bullet_list(followups)}</div>',
            unsafe_allow_html=True,
        )
        return

    demand = state.get(state.KEY_DEMAND)
    result = state.get(state.KEY_RESULT)
    if demand is None or result is None:
        components.empty_state(
            "还没有分析结果。填好上面的需求，点「开始分析」即可看到推荐与评分。",
            icon_name="analysis",
        )
        return

    if state.get(state.KEY_SIGNATURE) != _input_signature():
        components.show_notice(
            "你已经修改了输入条件。当前显示的是上一次分析的结果，"
            "点「开始分析」按新条件重新计算。",
            "warn",
        )

    if state.get("zg_prefs_applied"):
        components.show_notice(
            "本次分析已自动带上「个人设置」里的偏好。偏好只补空缺，"
            "你这次手填的内容优先。",
            "info",
        )

    left, right = st.columns([2, 3], gap="large")
    with left:
        _render_left_column(demand, result)
    with right:
        _render_right_column(result)


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
    left, mid, right = st.columns([1, 1, 4])
    with left:
        clicked = st.button("开始分析", type="primary", use_container_width=True)
    with mid:
        if st.button("清空条件", use_container_width=True):
            # 只记请求——此刻输入控件都已创建，就地清空会抛异常
            st.session_state[state.KEY_RESET] = True
            state.clear_analysis()
            st.rerun()
    with right:
        if state.get(state.KEY_RESULT) is not None:
            st.markdown(
                '<div class="zg-caption" style="padding-top:9px">'
                "改完条件记得重新点一次「开始分析」。</div>",
                unsafe_allow_html=True,
            )

    if clicked:
        # 处理中给个明确反馈，避免用户以为点了没反应而反复点击
        with st.spinner("正在解析需求、筛选商品并计算匹配度…"):
            _run_analysis(catalog)

    st.write("")
    _render_results()
