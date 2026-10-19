"""AI 问答页：问一个选购问题，系统检索知识库并组织成回答。

形态是**一问一答**：AI 恒开。回答优先由模型依据检索到的片段组织；
检索片段**不在界面上展示**。知识库没有直接资料时，回退到 AI 通用知识，
界面必须明确标注「通用知识」并提示价格/参数去智能分析核实。

失败与未配置都不静默：未配密钥时明确说明怎么配，调用失败时说明原因。
**任何情况下都不展示未通过校验的半成品。**
"""

from __future__ import annotations

import streamlit as st

from src import ai_enhance, ai_service, config
from src.data_loader import Catalog
from src.errors import ZhigouError, to_user_message
from src.knowledge.search import search_knowledge
from src.ui import components, state

_INPUT_KEY = "zg_knowledge_query"
_RESULT_KEY = "zg_knowledge_results"
_PRICE_KEY = "zg_knowledge_price_query"

#: 待执行的问题。示例按钮点击后写这里、`st.rerun()`，
#: 由本轮渲染**在输入控件实例化之前**消费。
#:
#: 为什么要绕这一下：Streamlit 不允许在控件实例化之后修改它绑定的
#: session_state 键。点了示例按钮时输入框早已渲染完，直接写 `_INPUT_KEY`
#: 会被拒绝——而且是静默不生效，看起来像按钮没反应。
#: `home.py` 的「预填 + 自动执行」用的就是这个手法。
_PENDING_KEY = "zg_knowledge_pending"

#: 作答文本、失败说明与「未配置密钥」标记。都**只存内存**，不进历史报告。
_ANSWER_KEY = "zg_knowledge_answer"
_AI_NOTE_KEY = "zg_knowledge_notes"
_MODE_KEY = "zg_knowledge_mode"
_SOURCE_KEY = "zg_knowledge_source"
_NEED_KEY_KEY = "zg_knowledge_need_key"
_DISABLED_KEY = "zg_knowledge_disabled"

#: 模型在“只依据片段”模式下也可能给出这类拒答；命中后改用通用知识补答。
_REFUSAL_MARKERS = (
    "暂时无法回答",
    "无法回答",
    "暂时答不了",
    "没有足够",
    "资料不足",
    "无法给出",
)

EXAMPLE_QUESTIONS: tuple[str, ...] = (
    "笔记本多重适合带出门",
    "编程用什么电脑",
    "手机拍照档位怎么看",
    "电池容量大续航就好吗",
)


def _has_price_intent(text: str) -> bool:
    """问题里是否在追问价格。

    价格类问题**不走问答**——检索按文本相关性找资料，不理解数值约束。
    原型实测时问「2000 元以内买什么手机」，它会返回一款远超预算的商品。
    """
    return any(term in text for term in config.KNOWLEDGE_PRICE_INTENT_TERMS)


def _ai_ready() -> bool:
    """本页恒走 AI：全局开关（个人设置）开启且密钥已配置才算就绪。

    全局开关关闭时与未配置密钥是两种不同的事——前者去设置打开即可，
    后者要先配密钥，提示文案必须区分。
    """
    return state.ai_enhanced_active()


def _render_globally_disabled() -> None:
    components.show_notice(
        "AI 增强已在「个人设置」中关闭，本页没有可用的本地形态。"
        "到「个人设置」打开「AI 增强模式」即可恢复问答。",
        "warn",
    )
    if st.button("去个人设置", type="primary"):
        state.request_page("个人设置")
        st.rerun()


def _clear_results() -> None:
    for key in (
        _ANSWER_KEY,
        _AI_NOTE_KEY,
        _NEED_KEY_KEY,
        _DISABLED_KEY,
        _RESULT_KEY,
        _PRICE_KEY,
        _MODE_KEY,
        _SOURCE_KEY,
    ):
        st.session_state.pop(key, None)


def _remember_general_answer(query: str) -> None:
    """知识库不足时的通用知识补答；失败仍按原逻辑如实说明。"""
    try:
        st.session_state[_ANSWER_KEY] = ai_enhance.answer_from_general_knowledge(
            query, service=ai_service.get_service()
        )
        st.session_state[_SOURCE_KEY] = "general"
    except ZhigouError as exc:
        st.session_state[_AI_NOTE_KEY] = (
            f"这次没能生成回答：{to_user_message(exc)}可以稍后重试，"
            "或到「智能分析」页按条件筛选商品。"
        )
    except Exception:  # noqa: BLE001 —— 任何意外都不该让页面崩掉
        st.session_state[_AI_NOTE_KEY] = (
            "这次没能生成回答，请稍后重试，或到「智能分析」页按条件筛选商品。"
        )


def _run_query(query: str) -> None:
    """执行一次提问：检索 → 组织回答。只把结果写进会话状态，不做渲染。"""
    _clear_results()

    if _has_price_intent(query):
        st.session_state[_PRICE_KEY] = query
        return

    from src import settings as _settings

    if not _settings.load_preferences(state.current_user()).ai_enhanced:
        # 全局开关关闭——去设置打开即可。
        st.session_state[_DISABLED_KEY] = True
        return
    if not _ai_ready():
        # 开关开着但没配密钥：如实说明怎么配，不静默降级。
        st.session_state[_NEED_KEY_KEY] = True
        return

    result = state.retrieve_knowledge(query)
    passages = result.passages
    st.session_state[_RESULT_KEY] = passages
    st.session_state[_MODE_KEY] = (result.mode_label, result.note)

    # 知识库没有直接资料：用 AI 通用知识补答，界面会明确标注。
    if not passages:
        _remember_general_answer(query)
        return

    try:
        answer = ai_enhance.answer_from_knowledge(
            query, passages, service=ai_service.get_service()
        )
        # 极少情况下模型仍会拒答；这时也补一次通用知识回答。
        if any(marker in answer for marker in _REFUSAL_MARKERS):
            _remember_general_answer(query)
            return
        st.session_state[_ANSWER_KEY] = answer
        st.session_state[_SOURCE_KEY] = "knowledge"
    except ZhigouError as exc:
        st.session_state[_AI_NOTE_KEY] = (
            f"这次没能生成回答：{to_user_message(exc)}可以稍后重试，"
            "或到「智能分析」页按条件筛选商品。"
        )
    except Exception:  # noqa: BLE001 —— 任何意外都不该让页面崩掉
        st.session_state[_AI_NOTE_KEY] = (
            "这次没能生成回答，请稍后重试，或到「智能分析」页按条件筛选商品。"
        )


def _render_answer() -> None:
    answer = st.session_state.get(_ANSWER_KEY)
    if not answer:
        return
    if st.session_state.get(_SOURCE_KEY) == "general":
        components.show_notice(
            "知识库没有检索到直接依据。以下为 AI 通用知识建议，"
            "不是本项目知识库或商品数据；具体价格、库存和参数请到"
            "「智能分析」按条件筛选核实。",
            "warn",
        )
    with st.container(border=True):
        st.markdown(str(answer))


def _render_empty() -> None:
    components.show_notice(
        "这次暂时没有生成回答。可以换个说法再试，或者到「智能分析」页"
        "按条件筛选商品。",
        "warn",
    )


def _render_need_key() -> None:
    """未配置密钥时的可行动提示——告诉用户怎么配，而不是报错。"""
    components.show_notice(
        "「AI 问答」需要配置模型密钥后才能使用——回答优先依据知识库，"
        "资料未覆盖时由模型用通用知识补充；没有密钥时不会有可用形态。",
        "warn",
    )
    st.markdown(
        "**怎么配置：** 在项目根目录的 `.env` 文件里填 `ZHIGOU_LLM_API_KEY`"
        "（以及可选的 `ZHIGOU_LLM_BASE_URL` / `ZHIGOU_LLM_MODEL`），"
        "保存后重启应用即可生效。",
        unsafe_allow_html=False,
    )
    components.caption(
        "不配置密钥时，「智能分析」「商品比较」等页面仍然完全可用——"
        "它们走本地规则，不需要联网。"
    )
    if st.button("去智能分析按条件筛选", type="primary"):
        from src.ui.pages.home import go_to_analysis

        go_to_analysis(str(st.session_state.get(_INPUT_KEY, "")))


def _render_ai_failure(note: str) -> None:
    components.show_notice(note, "warn")


def _render_price_guidance(query: str) -> None:
    """价格类问题的引导，替代作答。"""
    components.show_notice(
        "这个问题涉及价格或预算，不适合用问答回答——"
        "问答依据的是资料文本，不理解价格范围，很容易给出与预算不符的商品。",
        "warn",
    )
    components.caption("价格和参数请走商品筛选，那边按结构化数据计算，结论准确。")
    if st.button("带着这个问题去筛选商品", type="primary"):
        from src.ui.pages.home import go_to_analysis

        go_to_analysis(query)


def _render_examples() -> None:
    components.section_title("示例问题")
    components.caption("点一下就能试：")
    columns = st.columns(len(EXAMPLE_QUESTIONS))
    for column, question in zip(columns, EXAMPLE_QUESTIONS):
        with column:
            if st.button(question, width="stretch"):
                # 只记请求，不在本轮直接改输入框的键——它已经实例化了。
                st.session_state[_PENDING_KEY] = question
                st.rerun()


def render(catalog: Catalog) -> None:
    # 先消费上一轮留下的请求。**必须在任何输入控件实例化之前**——
    # 否则会撞上 Streamlit 的那条限制（见 `_PENDING_KEY` 的说明）。
    pending = st.session_state.pop(_PENDING_KEY, None)
    if pending is not None:
        st.session_state[_INPUT_KEY] = pending
        _run_query(str(pending))

    components.page_header(
        "AI 问答",
        "问一个商品选购问题，系统优先检索知识库；没有直接资料时由 AI 用通用知识补充，"
        "并明确标注。价格与参数请用「智能分析」按条件筛选。",
        right=components.runtime_chip(),
    )

    with st.container(border=True):
        st.markdown(
            '<div class="zg-card-title">问一个选购问题</div>'
            '<div class="zg-card-sub" style="margin-bottom:10px">'
            "比如「笔记本多重适合带出门」「手机拍照怎么看」。"
            "回答优先依据知识库；资料未覆盖时由 AI 用通用知识补充。"
            "</div>",
            unsafe_allow_html=True,
        )
        st.text_area(
            "问一个选购问题",
            key=_INPUT_KEY,
            height=90,
            placeholder=f"例如：{EXAMPLE_QUESTIONS[0]}",
            label_visibility="collapsed",
        )

        columns = st.columns([1, 3])
        with columns[0]:
            asked = st.button("提问", type="primary", width="stretch")
        with columns[1]:
            st.markdown(
                '<div class="zg-caption" style="padding-top:9px">'
                "回答优先依据知识库；资料未覆盖时会标注为 AI 通用知识。</div>",
                unsafe_allow_html=True,
            )

    if asked:
        query = str(st.session_state.get(_INPUT_KEY, "")).strip()
        if not query:
            _clear_results()
            components.show_notice("请先输入一个问题。", "warn")
            return
        _run_query(query)

    st.write("")

    price_query = st.session_state.get(_PRICE_KEY)
    if price_query:
        _render_price_guidance(str(price_query))
        return

    if st.session_state.get(_NEED_KEY_KEY):
        _render_need_key()
        return

    if st.session_state.get(_DISABLED_KEY):
        _render_globally_disabled()
        return

    if _RESULT_KEY not in st.session_state:
        _render_examples()
        return

    note = st.session_state.get(_AI_NOTE_KEY)
    if note:
        _render_ai_failure(str(note))
        return

    if st.session_state.get(_ANSWER_KEY):
        _render_answer()
    else:
        _render_empty()

    if st.session_state.get(_SOURCE_KEY) == "general":
        components.caption("本次使用：AI 通用知识（非实时联网，未引用知识库）。")
    else:
        mode = st.session_state.get(_MODE_KEY)
        if mode:
            label, note = mode
            if note:
                components.show_notice(str(note), "warn")
            components.caption(
                f"本次使用：{label}（{'向量检索' if label == '语义检索' else 'BM25 关键词检索'}）。"
            )

    st.write("")
    components.caption(
        "知识库内容由本项目整理，不是厂商资料；AI 通用知识不能替代商品数据。"
        "价格不是实时价格、参数未逐条核验。"
    )
