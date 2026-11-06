"""知识检索的统一入口。

优先语义检索（向量），不可用时回退关键词（BM25）。
两种方式返回同一种 `Passage`，调用方（AI 问答、Agent 工具、管理页调试台）
不需要区分实现；`RetrievalResult.mode` 只用于**如实告诉用户**目前走的是哪条路。

回退原则：
- 未配置 Embedding 服务 → 关键词
- 语义检索抛领域异常 → 关键词，并带上降级说明
- 语义检索成功但低于阈值 → 视为「没有相关资料」，**不**回退
  （回退会把「语义上确实不相关」变成「字面碰巧命中」，违背检索意图）

边界处理：
- 空白 / 超长查询 → 入口直接拒绝，不发起外部调用，`note` 说明原因；
- 向量化服务返回空 → 按领域异常降级，不伪装成「没有资料」；
- 损坏的向量行 → 在 `VectorStore._matrix` 逐行跳过并记 warning，
  不让单条坏数据把整条语义检索打回关键词模式。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src import config
from src.errors import UpstreamResponseError, ZhigouError, to_user_message
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
    """检索知识库：向量优先，失败回退关键词。

    空白与超长查询在入口直接拒绝，不发起外部调用；拒绝时 `mode` 记为
    `keyword` 只是沿用现有枚举（实际没有执行任何检索），原因放在 `note` 里。
    """
    query = (query or "").strip()
    if not query:
        logger.debug("检索查询为空，直接返回空结果")
        return RetrievalResult(passages=[], mode="keyword", note="请输入要查询的问题。")
    if len(query) > config.KNOWLEDGE_MAX_QUERY_CHARS:
        logger.warning("检索查询过长（%d 字符），已拒绝", len(query))
        return RetrievalResult(
            passages=[],
            mode="keyword",
            note=f"问题过长（超过 {config.KNOWLEDGE_MAX_QUERY_CHARS} 字），请精简后再试。",
        )

    limit = limit or config.KNOWLEDGE_MAX_RESULTS
    service = service or embeddings.get_service()

    if service.configured:
        try:
            store = store or VectorStore()
            vectors = service.embed([query])
            if not vectors:
                # 空响应不是「没有资料」，是服务返回了不完整结果：
                # 按领域异常走回退，并在提示里说清原因，别让用户以为查无此物。
                raise UpstreamResponseError("向量化服务没有返回查询向量。")
            hits = store.search(
                vectors[0],
                model=service.model,
                dim=service.dim,
                limit=limit,
            )
            passages = [_to_passage(hit, query) for hit in hits]
            logger.debug("语义检索完成：命中 %d 条", len(passages))
            return RetrievalResult(
                passages=passages,
                mode="vector",
                note="" if passages else "本次为语义检索，未找到足够相关的资料。",
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
        logger.debug(
            "未提供关键词索引，返回空结果（降级说明：%s）", fallback_note or "无"
        )
        return RetrievalResult(passages=[], mode="keyword", note=fallback_note)
    passages = search_knowledge(query, index=index, limit=limit)
    logger.debug("关键词检索完成：命中 %d 条", len(passages))
    return RetrievalResult(passages=passages, mode="keyword", note=fallback_note)
