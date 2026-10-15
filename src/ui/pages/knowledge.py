"""知识问答页：问选购问题，系统把资料找出来给你看。

这一版是**本地演示模式**的表现形态：直接展示资料原文片段与来源，
**不生成任何答复文本**。没有模型可用的前提下，任何「回答」都只是对片段的
机械拼接——那不如把原文给你，自己读。没把握就不替你写答案。

AI 增强模式下的作答在 `ai_enhance` 里（下一组任务接入），
但无论哪种模式，**来源都会一并展示**，让答案可核对。
"""

from __future__ import annotations

import streamlit as st

from src import ai_enhance, ai_service, config
from src.data_loader import Catalog
from src.errors import ZhigouError, to_user_message
from src.knowledge.search import Passage, search_knowledge
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

#: AI 模式下的作答文本与降级说明。两者都**只存内存**，不进历史报告。
_ANSWER_KEY = "zg_knowledge_answer"
_AI_NOTE_KEY = "zg_knowledge_notes"

EXAMPLE_QUESTIONS: tuple[str, ...] = (
    "主动降噪和被动降噪有什么区别",
    "通勤戴的耳机怎么选",
    "笔记本多重适合带出门",
    "婴儿车怎么挑",
)


def _has_price_intent(text: str) -> bool:
    """问题里是否在追问价格。

    价格类问题**不给检索答案**——检索按文本相关性找资料，不理解数值约束。
    原型实测时问「500 元以内降噪耳机」，它会返回一款 2499 元的商品。
    """
    return any(term in text for term in config.KNOWLEDGE_PRICE_INTENT_TERMS)


def _render_results(passages: list[Passage]) -> None:
    """展示检索结果。

    AI 模式多一段组织好的回答；本地模式**只有原文**——没有模型可用时，
    任何「回答」都只是对片段的机械拼接，那不如把原文交给你自己读。
    两种模式都会把所依据的片段列在下面，方便核对。
    """
    answer = st.session_state.get(_ANSWER_KEY)
    if answer:
        with st.container(border=True):
            st.markdown(
                '<div class="zg-card-title">基于资料的回答</div>',
                unsafe_allow_html=True,
            )
            st.markdown(str(answer))
            components.caption("这段回答由模型依据下面的资料组织，请以资料原文为准。")

    components.section_title("找到的资料", len(passages))
    components.caption(
        "下面是知识库原文，不是系统替你写的结论。出处与更新时间标在每条下方。"
    )

    for index, passage in enumerate(passages, start=1):
        with st.container(border=True):
            st.markdown(
                f'<div class="zg-card-title">{index}. {_safe(passage.title)}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(passage.excerpt)
            st.markdown(
                f'<div class="zg-caption">来源：{_safe(passage.citation)}</div>',
                unsafe_allow_html=True,
            )


def _safe(value: object) -> str:
    """转义要插进 HTML 的文本。语料是手写文件，仍按不可信内容处理。"""
    from src.ui.theme import esc

    return esc(value)


def _render_empty() -> None:
    """检索不到时的说明。**不展示任何来源**——没有资料就没有可引用的来源。"""
    components.show_notice(
        "知识库里没有找到与这个问题相关的资料。"
        "系统不会在没有依据的情况下作答——换个说法再试，或者到「智能分析」页"
        "按条件筛选商品。",
        "warn",
    )


def _render_price_guidance(query: str) -> None:
    """价格类问题的引导，替代检索结果。"""
    components.show_notice(
        "这个问题涉及价格或预算，不适合用资料检索回答——"
        "资料是按文字相关性找的，不理解价格范围，很容易给出与预算不符的商品。",
        "warn",
    )
    components.caption("价格和参数请走商品筛选，那边按结构化数据计算，结论准确。")
    if st.button("带着这个问题去筛选商品", type="primary"):
        from src.ui.pages.home import go_to_analysis

        go_to_analysis(query)


def _ai_enabled() -> bool:
    """AI 增强是否真的可用：开关打开**且**配好了密钥。

    与分析页共用同一个开关键，用户在任一处打开都会带过来。
    """
    if not st.session_state.get("zg_ai_enabled"):
        return False
    return ai_service.get_service().configured


def _run_query(query: str) -> None:
    """执行一次提问，把结果（或价格引导）写进会话状态。"""
    st.session_state.pop(_ANSWER_KEY, None)
    st.session_state.pop(_AI_NOTE_KEY, None)

    if _has_price_intent(query):
        st.session_state[_PRICE_KEY] = query
        st.session_state.pop(_RESULT_KEY, None)
        return

    st.session_state.pop(_PRICE_KEY, None)
    passages = search_knowledge(query, index=state.get_knowledge_index())
    st.session_state[_RESULT_KEY] = passages

    # AI 增强：只多做一件事——把片段组织成一段回答。
    # 失败**不影响**片段展示，那是本地模式本来就有的形态。
    if not (passages and _ai_enabled()):
        return
    try:
        st.session_state[_ANSWER_KEY] = ai_enhance.answer_from_knowledge(
            query, passages, service=ai_service.get_service()
        )
    except ZhigouError as exc:
        st.session_state[_AI_NOTE_KEY] = (
            f"AI 作答未能完成，已降级为直接展示资料原文：{to_user_message(exc)}"
        )
    except Exception:  # noqa: BLE001 —— 任何意外都不该让问答不可用
        st.session_state[_AI_NOTE_KEY] = "AI 作答未能完成，已降级为直接展示资料原文。"


def render(catalog: Catalog) -> None:
    # 先消费上一轮留下的请求。**必须在任何输入控件实例化之前**——
    # 否则会撞上 Streamlit 的那条限制（见 `_PENDING_KEY` 的说明）。
    pending = st.session_state.pop(_PENDING_KEY, None)
    if pending is not None:
        st.session_state[_INPUT_KEY] = pending
        _run_query(str(pending))

    components.page_header(
        "知识问答",
        "问商品知识类的问题，系统从知识库里找资料并标出出处。"
        "价格与参数请用「智能分析」按条件筛选。",
        right=components.runtime_chip(),
    )

    # 与分析页共用同一个开关键，用户在哪一处打开都会带过来。
    if config.is_ai_configured():
        st.toggle(
            "启用 AI 增强（会把你的问题与检索到的资料片段发送给模型服务）",
            key="zg_ai_enabled",
            help="关闭时只展示资料原文，不发起任何网络请求。",
        )

    with st.container(border=True):
        st.markdown(
            '<div class="zg-card-title">问一个选购问题</div>'
            '<div class="zg-card-sub" style="margin-bottom:10px">'
            "比如「主动降噪和被动降噪有什么区别」「通勤耳机怎么选」。"
            "系统会展示知识库里的原文与来源。"
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
            asked = st.button("查找资料", type="primary", use_container_width=True)
        with columns[1]:
            st.markdown(
                '<div class="zg-caption" style="padding-top:9px">'
                "系统只展示知识库里的原文，不会替你编答案。</div>",
                unsafe_allow_html=True,
            )

    if asked:
        query = str(st.session_state.get(_INPUT_KEY, "")).strip()
        if not query:
            st.session_state.pop(_RESULT_KEY, None)
            st.session_state.pop(_PRICE_KEY, None)
            components.show_notice("请先输入一个问题。", "warn")
            return
        _run_query(query)

    st.write("")

    price_query = st.session_state.get(_PRICE_KEY)
    if price_query:
        _render_price_guidance(str(price_query))
        return

    if _RESULT_KEY not in st.session_state:
        components.section_title("示例问题")
        components.caption("点一下就能试：")
        columns = st.columns(len(EXAMPLE_QUESTIONS))
        for column, question in zip(columns, EXAMPLE_QUESTIONS):
            with column:
                if st.button(question, use_container_width=True):
                    # 只记请求，不在本轮直接改输入框的键——它已经实例化了。
                    st.session_state[_PENDING_KEY] = question
                    st.rerun()
        return

    note = st.session_state.get(_AI_NOTE_KEY)
    if note:
        components.show_notice(str(note), "warn")

    passages = st.session_state.get(_RESULT_KEY) or []
    if passages:
        _render_results(list(passages))
    else:
        _render_empty()

    st.write("")
    components.caption(
        "知识库内容由本项目整理，不是厂商资料；商品数据为演示数据，价格不是实时价格。"
    )
