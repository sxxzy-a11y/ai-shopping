"""智能分析页：需求输入 → 筛选排序 → 评分与推荐结果。"""

from __future__ import annotations

import streamlit as st

from src import ai_enhance, ai_service, config, database, report_service, settings
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

#: 各输入控件的初始值。镜像与恢复都以它为基准。
_INPUT_DEFAULTS: dict[str, object] = {
    "zg_input_text": "",
    "zg_input_budget": "",
    "zg_input_use_cases": [],
    "zg_input_core_needs": [],
    "zg_input_brands": [],
    _CATEGORY_KEY: _NO_CATEGORY,
}

#: 镜像命名空间，与其它页面区分开
_MIRROR_NS = "analysis_inputs"


def _prepare_inputs() -> None:
    """在控件创建**之前**把输入状态准备好。

    必须在 `_render_inputs()` 之前调用，做两件事：

    1. 处理「预填」与「清空」请求。Streamlit 不允许在控件实例化后改它绑定的
       session_state 键，所以这两类操作只能记请求、下一轮在这里消费。
    2. 键不存在时从镜像恢复。切页会触发侧栏按钮里的 `st.rerun()`，那次运行
       在渲染完侧栏后就中断了，正文控件没被「看到」，Streamlit 会清掉它们的
       session 状态——不恢复的话，用户写了一半的需求切页回来就没了。
    """
    acted = False

    if st.session_state.pop(state.KEY_RESET, False):
        for key in _INPUT_KEYS:
            st.session_state.pop(key, None)
        st.session_state[_CATEGORY_KEY] = _NO_CATEGORY
        acted = True

    prefill = st.session_state.pop(state.KEY_PREFILL, None)
    if prefill:
        st.session_state["zg_input_text"] = prefill.get("text", "")
        st.session_state[_CATEGORY_KEY] = prefill.get("category", _NO_CATEGORY)
        for key, default in _INPUT_DEFAULTS.items():
            if key not in ("zg_input_text", _CATEGORY_KEY):
                st.session_state[key] = default
        acted = True

    # 清空/预填是用户明确的意图，不能被镜像里的旧值盖回去
    if not acted:
        state.restore_widgets(_MIRROR_NS, _INPUT_DEFAULTS)


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


def _render_ai_controls() -> None:
    """AI 增强开关。

    spec 要求「调用外部 AI API 前，界面 SHALL 说明将要发送的数据范围，
    并由用户确认」。所以这里默认**关闭**，打开时才展示数据共享说明，
    且每次分析都会把说明再列一遍。
    """
    service = ai_service.get_service()
    if not service.configured:
        st.markdown(
            f'<div class="zg-caption" style="margin-bottom:10px">'
            f"当前为本地演示模式：未配置模型密钥，全部由本地规则完成，不联网。"
            f"配置 {config.LLM_API_KEY_ENV} 后可使用 AI 增强。</div>",
            unsafe_allow_html=True,
        )
        return

    st.toggle(
        "启用 AI 增强（会把你输入的内容与候选商品数据发送给模型服务）",
        key="zg_ai_enabled",
        help="关闭时全部由本地规则完成，不发起任何网络请求。",
    )

    if st.session_state.get("zg_ai_enabled"):
        st.markdown(
            f'<div class="zg-caption">当前模型：{service.model}　·　'
            f"端点：{service.describe()['base_url']}</div>",
            unsafe_allow_html=True,
        )
        notice = ai_enhance.data_sharing_notice(
            state.get(state.KEY_DEMAND) or Demand(),
            0,
        )
        st.markdown(
            f'<div class="zg-notice zg-notice-warn">'
            f'<span>{esc_multi(notice)}</span></div>',
            unsafe_allow_html=True,
        )
    st.write("")


def esc_multi(text: str) -> str:
    """把多行文本转成 HTML（换行变 <br>），逐段转义。"""
    from src.ui.theme import esc

    return "<br>".join(esc(line) if line else "&nbsp;" for line in text.splitlines())


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

    ai_notes: list[str] = []
    ai_enabled = bool(st.session_state.get("zg_ai_enabled")) and ai_service.get_service().configured

    try:
        if raw_text.strip():
            parsed = _parse_text(raw_text, catalog, ai_enabled, ai_notes)
        else:
            parsed = Demand()
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

    # AI 解读：失败只丢掉解读，规则算出的推荐结果照常保留
    explanation: dict | None = None
    if ai_enabled and result.within_budget:
        try:
            explanation = ai_enhance.explain_recommendations(
                applied, result.within_budget[:3], service=ai_service.get_service()
            )
        except ZhigouError as exc:
            ai_notes.append(to_user_message(exc))
    state.put("zg_ai_explanation", explanation)
    state.put("zg_ai_notes", ai_notes)

    signature = _input_signature()
    state.put(state.KEY_DEMAND, applied)
    state.put(state.KEY_RESULT, result)
    state.put(state.KEY_SIGNATURE, signature)
    state.put("zg_prefs_applied", contributed)

    # 生成报告并落库。报告在这一刻固化，之后商品数据怎么变都不影响它。
    report = report_service.build_report(catalog, applied, result)
    state.put(state.KEY_REPORT, report)
    _persist(report, signature)


def _parse_text(raw_text: str, catalog: Catalog, ai_enabled: bool, notes: list[str]) -> Demand:
    """解析需求：优先 AI，失败回退规则。

    回退不是「静默降级」——失败原因会记进 notes 并在界面上说出来，
    让用户知道这次结果是谁算的。

    解析器用**单独的会话键**记录，而不是塞进 `Demand.source`：
    需求经过 `merge_demand` 之后 source 会变成 "merged"（这是准确的，
    它确实被合并过），拿它判断「是不是 AI 解析的」会失准。
    """
    if not ai_enabled:
        state.put("zg_parse_engine", "rule")
        return parse_demand(raw_text, known_brands=catalog.brands())

    try:
        parsed = ai_enhance.parse_demand_with_ai(
            raw_text, service=ai_service.get_service(), known_brands=catalog.brands()
        )
    except ZhigouError as exc:
        notes.append(to_user_message(exc) + "（本次需求解析已改用本地规则）")
        state.put("zg_parse_engine", "rule")
        return parse_demand(raw_text, known_brands=catalog.brands())

    state.put("zg_parse_engine", "ai")
    return parsed


def _persist(report, signature: str) -> None:
    """把报告写进历史记录，带会话级去重。

    去重依据是「条件指纹」：同一组条件重复点「开始分析」只落一条记录。
    写入失败**不中断**当前页面——结果还在内存里，用户这次分析没有白做。
    """
    if st.session_state.get(state.KEY_SAVED_SIGNATURE) == signature:
        return

    try:
        database.save_analysis(report)
    except ZhigouError as exc:
        state.put("zg_save_error", to_user_message(exc))
        return

    st.session_state[state.KEY_SAVED_SIGNATURE] = signature
    state.put("zg_save_error", None)


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


def _favorite_actions(product) -> None:
    """商品行展开区里的收藏按钮。"""
    try:
        favorited = database.is_favorite(product.id)
    except ZhigouError:
        favorited = False

    label = "取消收藏" if favorited else "收藏这件商品"
    if st.button(label, key=f"fav_{product.id}", use_container_width=False):
        try:
            database.remove_favorite(product.id) if favorited else database.add_favorite(product.id)
        except ZhigouError as exc:
            state.put("zg_fav_error", to_user_message(exc))
        else:
            state.put("zg_fav_error", None)
        st.rerun()


def _render_right_column(result) -> None:
    total = len(result.within_budget)
    explanation = state.get("zg_ai_explanation") or {}
    per_product = explanation.get("per_product") or {}

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
                extra_actions=lambda p=item.product: _favorite_actions(p),
                ai_note=per_product.get(item.product.id, ""),
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
                item.product,
                item.score,
                item.budget_label,
                extra_actions=lambda p=item.product: _favorite_actions(p),
            )

    if result.relaxations:
        components.section_title("放宽条件的建议")
        st.markdown(
            f'<div class="zg-card is-flat">{bullet_list(result.relaxations)}</div>',
            unsafe_allow_html=True,
        )


def _render_export(report) -> None:
    """导出按钮。导出内容与界面一致，且保留演示数据来源标注。"""
    col_md, col_csv, _spacer = st.columns([1, 1, 3])
    with col_md:
        st.download_button(
            "导出 Markdown",
            data=report_service.markdown_bytes(report),
            file_name=report_service.suggested_filename(report, "md"),
            mime="text/markdown",
            key="zg_export_md",
            use_container_width=True,
        )
    with col_csv:
        st.download_button(
            "导出 CSV",
            data=report_service.csv_bytes(report),
            file_name=report_service.suggested_filename(report, "csv"),
            mime="text/csv",
            key="zg_export_csv",
            use_container_width=True,
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

    for note in state.get("zg_ai_notes") or []:
        components.show_notice(note, "warn")

    engine = state.get("zg_parse_engine")
    if engine == "ai":
        components.show_notice("本次需求由 AI 解析，推荐排序仍由本地规则计算。", "info")
    elif engine == "rule" and st.session_state.get("zg_ai_enabled"):
        components.show_notice("本次需求由本地规则解析。", "info")

    explanation = state.get("zg_ai_explanation")
    if explanation and explanation.get("overview"):
        components.show_notice(f"AI 总述：{explanation['overview']}", "info")

    if state.get("zg_prefs_applied"):
        components.show_notice(
            "本次分析已自动带上「个人设置」里的偏好。偏好只补空缺，"
            "你这次手填的内容优先。",
            "info",
        )

    save_error = state.get("zg_save_error")
    if save_error:
        components.show_notice(save_error, "warn")

    fav_error = state.get("zg_fav_error")
    if fav_error:
        components.show_notice(fav_error, "warn")

    report = state.get(state.KEY_REPORT)
    if report is not None:
        st.write("")
        _render_export(report)

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
    _prepare_inputs()

    # 首页点「开始分析」跳过来时带的自动执行标记。取值必须在控件创建之前，
    # 但**执行**要等到输入区渲染完（_run_analysis 要读控件的当前值）。
    autorun = st.session_state.pop("zg_autorun", False)

    components.page_header(
        "智能分析",
        "描述你的购买需求，系统会筛选候选商品、按需求匹配度打分排序，"
        "并把评分怎么算出来的逐项摊开给你看。",
    )

    _render_ai_controls()
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

    if clicked or autorun:
        # 处理中给个明确反馈，避免用户以为点了没反应而反复点击
        with st.spinner("正在解析需求、筛选商品并计算匹配度…"):
            _run_analysis(catalog)

    # 控件都已渲染完，此刻的值就是用户当前所见，记进镜像备下次切页恢复
    state.snapshot_widgets(_MIRROR_NS, _INPUT_DEFAULTS)

    st.write("")
    _render_results()
