"""知识检索的统一入口。

优先语义检索（向量），不可用时回退关键词（BM25）。
两种方式返回同一种 `Passage`，调用方（AI 问答、Agent 工具、管理页调试台）
不需要区分实现；`RetrievalResult.mode` 只用于**如实告诉用户**目前走的是哪条路。

回退原则：
- 未配置 Embedding 服务 → 关键词
- 语义检索抛领域异常 → 关键词，并带上降级说明
- 语义检索成功但低于阈值 → 视为「没有相关资料」，**不**回退
  （回退会把「语义上确实不相关」变成「字面碰巧命中」，违背检索意图）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src import config
from src.errors import ZhigouError, to_user_message
from src.knowledge import embeddings
from src.knowledge.corpus import TYPE_CATEGORY, TYPE_PRODUCT, TYPE_SERVICE
from src.knowledge.index import BM25Index
from src.knowledge.search import EXCERPT_MAX_CHARS, Passage, search_knowledge
from src.knowledge.vector_store import VectorStore

logger = logging.getLogger("zhigou.knowledge.retrieval")

_TYPE_LABELS = {
    TYPE_CATEGORY: "品类级",
    TYPE_SERVICE: "服务级",
    TYPE_PRODUCT: "商品级",
}


@dataclass(frozen=True)
class RetrievalResult:
    """一次检索的结果与所用方式。"""

    passages: list[Passage]
    mode: str  # "vector" | "keyword"
    note: str = ""

    @property
    def mode_label(self) -> str:
        return "语义检索" if self.mode == "vector" else "关键词检索"


def _to_passage(scored, query: str) -> Passage:
    slice_ = scored.slice
    content = slice_.content
    excerpt = content[:EXCERPT_MAX_CHARS].rstrip()
    if len(content) > len(excerpt):
        excerpt += "…"
    return Passage(
        doc_id=slice_.doc_id,
        title=slice_.title,
        excerpt=excerpt,
        doc_type=slice_.doc_type,
        type_label=_TYPE_LABELS.get(slice_.doc_type, slice_.doc_type),
        source=slice_.source,
        updated_at=slice_.updated_at,
        score=scored.score,
        product_id=slice_.product_id,
    )


def retrieve(
    query: str,
    *,
    index: BM25Index | None = None,
    store: VectorStore | None = None,
    service: embeddings.EmbeddingService | None = None,
    limit: int | None = None,
) -> RetrievalResult:
    """检索知识库：向量优先，失败回退关键词。"""
    limit = limit or config.KNOWLEDGE_MAX_RESULTS
    service = service or embeddings.get_service()

    if service.configured:
        try:
            store = store or VectorStore()
            query_vector = service.embed([query])[0]
            hits = store.search(
                query_vector,
                model=service.model,
                dim=service.dim,
                limit=limit,
            )
            return RetrievalResult(
                passages=[_to_passage(hit, query) for hit in hits],
                mode="vector",
            )
        except ZhigouError as exc:
            logger.warning("语义检索失败，回退关键词：%s", to_user_message(exc))
            fallback_note = (
                f"语义检索暂时不可用，本次已回退关键词检索：{to_user_message(exc)}"
            )
        except Exception:  # noqa: BLE001 —— 任何意外都不该让问答不可用
            logger.exception("语义检索出现未预期错误，回退关键词")
            fallback_note = "语义检索出现异常，本次已回退关键词检索。"
    else:
        fallback_note = ""

    if index is None:
        return RetrievalResult(passages=[], mode="keyword", note=fallback_note)
    passages = search_knowledge(query, index=index, limit=limit)
    return RetrievalResult(passages=passages, mode="keyword", note=fallback_note)
