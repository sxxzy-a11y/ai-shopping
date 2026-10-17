"""知识库管理页（仅管理员）。

三块：商品知识库（文档与索引状态）、商品知识切片（切片表）、Embedding 检索。
语料仍是 `data/knowledge/` 下的 Markdown 文件 + 商品字段合成——这里不做
文档编辑器，只让「切片 → 向量化 → 检索」这条链路可见、可操作、可验证。
"""

from __future__ import annotations

import streamlit as st

from src import config
from src.auth import require_admin
from src.errors import ZhigouError, to_user_message
from src.knowledge import admin as knowledge_docs
from src.knowledge import chunking, embeddings
from src.knowledge.retrieval import retrieve
from src.ui import components, state
from src.ui.theme import facts

_KEY_QUERY = "zg_kb_debug_query"
_KEY_RESULT = "zg_kb_debug_result"
_KEY_DOC = "zg_kb_doc_pick"
_KEY_SLICE_DOC = "zg_kb_slice_doc"
_KEY_SLICE_TYPE = "zg_kb_slice_type"
_KEY_SLICE_STATUS = "zg_kb_slice_status"
_KEY_SLICE_PICK = "zg_kb_slice_pick"
_KEY_FLASH = "zg_kb_docs_flash"
_KEY_NEW_TYPE = "zg_kb_new_type"
_KEY_NEW_CATEGORY = "zg_kb_new_category"
_KEY_DELETE = "zg_kb_delete_doc"
_KEY_CONFIRM = "zg_kb_delete_confirm"

_ALL = "全部"


def _documents():
    return list(state.get_knowledge_index().documents)


def _slices() -> list[chunking.Slice]:
    """当前语料的切片（与检索索引同源）。"""
    return chunking.split_corpus(_documents())


def _vector_rows(service: embeddings.EmbeddingService) -> dict[tuple[str, str], dict]:
    return {
        (row["doc_id"], row["slice_id"]): row
        for row in state.get_vector_store().slice_rows(limit=10_000)
    }


def _slice_status(
    slice_: chunking.Slice, rows: dict[tuple[str, str], dict], service: embeddings.EmbeddingService
) -> str:
    row = rows.get((slice_.doc_id, slice_.slice_id))
    if row is None:
        return "未生成"
    if (
        row["content_hash"] != _content_hash(slice_)
        or row["model"] != service.model
        or int(row["dim"]) != service.dim
    ):
        return "过期"
    return "可用"


def _content_hash(slice_: chunking.Slice) -> str:
    from src.knowledge.vector_store import content_hash

    return content_hash(slice_)


# --------------------------------------------------------------------------
# 商品知识库
# --------------------------------------------------------------------------


def _render_overview(service: embeddings.EmbeddingService) -> None:
    slices = _slices()
    stats = state.get_vector_store().stats(
        slices, model=service.model, dim=service.dim
    )
    components.stat_row(
        [
            ("book", str(len({s.doc_id for s in slices})), "篇资料"),
            ("layers", str(stats.total_slices), "个切片"),
            ("check", str(stats.ready), "已向量化"),
            ("alert", str(stats.generation_needed), "待生成"),
        ]
    )
    st.markdown(
        facts(
            [
                ("向量模型", f"{service.model} · {service.dim} 维"),
                ("最近索引", stats.last_indexed_at or "尚未生成"),
                ("Embedding 服务", "已配置" if service.configured else "未配置"),
            ]
        ),
        unsafe_allow_html=True,
    )


def _render_index_action(service: embeddings.EmbeddingService) -> None:
    """生成向量。放在商品知识库页顶部，像平台的「生成全部切片」动作。"""
    if not service.configured:
        components.show_notice(
            "尚未配置向量化服务。在 `.env` 里填写 "
            f"`{config.EMBEDDING_API_KEY_ENV}`、`{config.EMBEDDING_BASE_URL_ENV}`、"
            f"`{config.EMBEDDING_MODEL_ENV}`、`{config.EMBEDDING_DIM_ENV}`，"
            "保存后重启应用即可。未配置时问答会自动使用关键词检索。",
            "info",
        )
        return

    slices = _slices()
    stats = state.get_vector_store().stats(
        slices, model=service.model, dim=service.dim
    )
    components.caption(
        f"当前 {stats.total_slices} 个切片，待生成 {stats.generation_needed} 个。"
        "已是最新的切片会被跳过，不重复调用向量服务。"
    )
    if st.button("生成全部向量", type="primary", disabled=not slices):
        progress = st.progress(0.0, text="正在向量化…")
        try:
            result = state.get_vector_store().build_index(slices, service=service)
        except ZhigouError as exc:
            progress.empty()
            components.show_notice(f"生成失败：{to_user_message(exc)}", "stop")
            return
        except Exception:  # noqa: BLE001 —— 页面不该崩
            progress.empty()
            components.show_notice("生成失败：出现未预期错误，请查看日志。", "stop")
            return
        progress.progress(1.0, text="完成")
        components.show_notice(
            f"已生成 {result.embedded} 个，跳过 {result.skipped} 个，"
            f"清理 {result.removed} 条陈旧记录。",
            "ok",
        )
        st.rerun()


def _render_documents(service: embeddings.EmbeddingService) -> None:
    import pandas as pd

    components.section_title("商品知识库")
    components.caption(
        "每篇资料都会被切成若干个检索切片；品类级与服务级来自手写文档，"
        "商品级由商品字段自动合成。"
    )

    documents = _documents()
    slices = _slices()
    counts: dict[str, int] = {}
    for slice_ in slices:
        counts[slice_.doc_id] = counts.get(slice_.doc_id, 0) + 1

    rows = _vector_rows(service)
    ready_by_doc: dict[str, int] = {}
    for slice_ in slices:
        if _slice_status(slice_, rows, service) == "可用":
            ready_by_doc[slice_.doc_id] = ready_by_doc.get(slice_.doc_id, 0) + 1

    frame = pd.DataFrame(
        [
            {
                "资料标题": document.title,
                "知识类型": {
                    "category": "品类级",
                    "service": "服务级",
                    "product": "商品级",
                }.get(document.doc_type, document.doc_type),
                "切片数": counts.get(document.doc_id, 0),
                "已向量化": ready_by_doc.get(document.doc_id, 0),
                "来源": document.source or "—",
                "更新时间": document.updated_at or "—",
                "状态": "可用",
            }
            for document in documents
        ]
    )
    st.dataframe(frame, width="stretch", hide_index=True)

    _render_flash()

    if documents:
        pick = st.selectbox(
            "查看资料内容",
            options=[document.title for document in documents],
            key=_KEY_DOC,
        )
        document = next(d for d in documents if d.title == pick)
        with st.expander(f"{document.title} · 正文", expanded=False):
            st.markdown(document.body)

    _render_new_document()
    _render_delete_document(documents)


# --------------------------------------------------------------------------
# 商品知识切片
# --------------------------------------------------------------------------


def _render_slices(service: embeddings.EmbeddingService) -> None:
    import pandas as pd

    slices = _slices()
    rows = _vector_rows(service)
    components.section_title("商品知识切片")
    components.caption(
        f"按标题分段、超长按段落续切；单个切片上限 {chunking.MAX_SLICE_CHARS} 字。"
        "状态为「过期」表示正文或模型变过，需要重新生成向量。"
    )

    doc_titles = sorted({s.title for s in slices})
    col_doc, col_type, col_status = st.columns([2, 1, 1])
    with col_doc:
        doc_filter = st.selectbox("资料", options=[_ALL, *doc_titles], key=_KEY_SLICE_DOC)
    with col_type:
        type_filter = st.selectbox(
            "知识类型",
            options=[_ALL, "品类级", "服务级", "商品级"],
            key=_KEY_SLICE_TYPE,
        )
    with col_status:
        status_filter = st.selectbox(
            "状态", options=[_ALL, "可用", "过期", "未生成"], key=_KEY_SLICE_STATUS
        )

    type_labels = {"category": "品类级", "service": "服务级", "product": "商品级"}
    filtered = []
    for slice_ in slices:
        label = type_labels.get(slice_.doc_type, slice_.doc_type)
        status = _slice_status(slice_, rows, service)
        if doc_filter != _ALL and slice_.title != doc_filter:
            continue
        if type_filter != _ALL and label != type_filter:
            continue
        if status_filter != _ALL and status != status_filter:
            continue
        filtered.append((slice_, label, status))

    if not filtered:
        components.empty_state("没有符合筛选条件的切片。")
        return

    frame = pd.DataFrame(
        [
            {
                "资料": slice_.title,
                "知识类型": label,
                "片段序号": index,
                "片段标题": slice_.heading or "（正文开头）",
                "字符数": len(slice_.content),
                "状态": status,
            }
            for index, (slice_, label, status) in enumerate(filtered, start=1)
        ]
    )
    st.dataframe(frame, width="stretch", hide_index=True)

    options = {
        f"{slice_.title} · {slice_.heading or '正文开头'} · #{index}": slice_
        for index, (slice_, _label, _status) in enumerate(filtered, start=1)
    }
    pick = st.selectbox("查看切片内容", options=list(options), key=_KEY_SLICE_PICK)
    chosen = options[pick]
    with st.expander("切片正文", expanded=True):
        st.markdown(chosen.content)


# --------------------------------------------------------------------------
# Embedding 检索
# --------------------------------------------------------------------------


def _render_debug(service: embeddings.EmbeddingService) -> None:
    components.section_title("检索调试")
    components.caption(
        "输入一个问题，看检索层实际会命中哪些切片、分数是多少。"
        "这就是 AI 问答作答时依据的内容。"
    )
    st.text_input("调试问题", key=_KEY_QUERY, placeholder="例如：华为怎么样")
    if st.button("检索", type="primary"):
        query = str(st.session_state.get(_KEY_QUERY, "")).strip()
        if not query:
            components.show_notice("请先输入一个问题。", "warn")
            return
        result = retrieve(query, index=state.get_knowledge_index())
        st.session_state[_KEY_RESULT] = result

    result = st.session_state.get(_KEY_RESULT)
    if result is None:
        return

    components.caption(f"检索方式：{result.mode_label}")
    if result.note:
        components.show_notice(result.note, "warn")
    if not result.passages:
        components.show_notice("没有命中任何切片（低于相似度阈值）。", "warn")
        return

    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "标题": passage.title,
                "片段": passage.excerpt[:80] + ("…" if len(passage.excerpt) > 80 else ""),
                "类型": passage.type_label,
                "分数": round(passage.score, 3),
                "来源": passage.source,
                "更新于": passage.updated_at,
            }
            for passage in result.passages
        ]
    )
    st.dataframe(frame, width="stretch", hide_index=True)


def render(catalog=None) -> None:
    """知识库管理页。"""
    require_admin(state.current_user())

    components.page_header(
        "知识库管理",
        "管理知识文档与检索切片，生成向量索引，调试检索效果。",
    )

    service = embeddings.get_service()
    tab_docs, tab_slices, tab_debug = st.tabs(
        ["商品知识库", "商品知识切片", "Embedding 检索"]
    )
    with tab_docs:
        _render_overview(service)
        st.divider()
        _render_index_action(service)
        st.divider()
        _render_documents(service)
    with tab_slices:
        _render_slices(service)
    with tab_debug:
        _render_debug(service)

    st.write("")
    components.caption(
        "向量化会把切片正文发送给所配置的 Embedding 服务；不会发送账号、历史或收藏。"
    )

# --------------------------------------------------------------------------
# 新增 / 删除资料
# --------------------------------------------------------------------------


def _flash(message: str, tone: str) -> None:
    st.session_state[_KEY_FLASH] = (message, tone)


def _render_flash() -> None:
    pending = st.session_state.pop(_KEY_FLASH, None)
    if pending:
        components.show_notice(pending[0], pending[1])


def _render_new_document() -> None:
    with st.expander("＋ 新增资料", expanded=False):
        components.caption(
            "新增的资料写入 `data/knowledge/custom/`，关键词检索立即生效；"
            "语义检索需要在「商品知识库」重新生成向量。"
        )
        with st.form("zg_kb_new_doc"):
            title = st.text_input("标题", key="zg_kb_new_title")
            doc_type = st.selectbox(
                "知识类型",
                options=["service", "category"],
                format_func=lambda value: {"service": "服务级", "category": "品类级"}[value],
                key=_KEY_NEW_TYPE,
            )
            category = st.selectbox(
                "商品分类（品类级必填）",
                options=["", *config.CATEGORY_LABELS],
                format_func=lambda value: config.category_label(value) if value else "（服务级资料无需选择）",
                key=_KEY_NEW_CATEGORY,
            )
            source = st.text_input(
                "来源说明", value="本项目整理（非厂商资料）", key="zg_kb_new_source"
            )
            body = st.text_area("正文（Markdown）", height=200, key="zg_kb_new_body")
            submitted = st.form_submit_button("新增资料", type="primary")

        if not submitted:
            return

        try:
            path = knowledge_docs.create_document(
                title=title,
                doc_type=doc_type,
                category=category,
                source=source,
                body=body,
            )
        except ZhigouError as exc:
            _flash(f"新增失败：{to_user_message(exc)}", "stop")
        else:
            _flash(
                f"已新增资料「{title.strip()}」（{path.name}）。"
                "重新生成向量后，语义检索将使用这份资料。",
                "ok",
            )
        st.rerun()


def _render_delete_document(documents) -> None:
    deletable = [document for document in documents if document.source_path]
    if not deletable:
        return

    with st.expander("删除资料", expanded=False):
        components.caption(
            "只能删除文件型资料（品类级 / 服务级）。商品级资料由商品数据自动生成，"
            "请到「商品维护」中编辑商品。"
        )
        options = {f"{document.title} · {document.doc_id}": document for document in deletable}
        pick = st.selectbox("选择要删除的资料", options=list(options), key=_KEY_DELETE)
        confirmed = st.checkbox(
            "我确认删除这份资料（不可撤销）", key=_KEY_CONFIRM
        )
        if st.button("删除资料", disabled=not confirmed):
            try:
                knowledge_docs.delete_document(options[pick].doc_id)
            except ZhigouError as exc:
                _flash(f"删除失败：{to_user_message(exc)}", "stop")
            else:
                _flash(
                    f"已删除资料「{options[pick].title}」。"
                    "关键词索引已更新；语义检索将在重新生成向量后同步。",
                    "ok",
                )
            st.rerun()

