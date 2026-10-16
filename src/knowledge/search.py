"""知识检索的对外入口。

上层（页面、AI 层、将来的 Agent 工具）只依赖本模块的 `search_knowledge`
与 `Passage`。**接口稳定是刻意的**（design.md D9）：将来若要换成向量检索，
替换实现即可，调用方一行不用改。

两条边界写在这里，而不是散在页面里：

- **低于阈值就是「检索不到」。** 返回弱相关结果充当答案，比说找不到更糟。
- **价格与库存不走检索。** 它们必须查结构化商品数据——检索是按文本相关性
  找资料，不理解数值约束（原型实测：问「500 元以内」会返回 2499 元的商品）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from src import config
from src.knowledge.corpus import Document
from src.knowledge.index import BM25Index
from src.knowledge.tokenize import token_set

logger = logging.getLogger("zhigou.knowledge")

#: 段落分隔：空行。文档正文按此切段，用于抽取相关片段。
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")

#: 片段的最大字数。整篇资料上千字，直接铺满屏没人看。
#:
#: 600 而不是更小：片段如今**不再直接展示**，它只是 AI 作答的依据——
#: 依据给得太少，模型只能回答「资料没覆盖」（实测问「笔记本多重适合带出门」时，
#: 只给到「性能与重量的矛盾」那一段，重量分档数字被切掉了）。
EXCERPT_MAX_CHARS = 600

#: 返回片段时最多带上几段。第一段是命中的，后面的是上下文补充。
EXCERPT_MAX_PARAGRAPHS = 3


@dataclass(frozen=True)
class Passage:
    """一条检索结果。界面与 AI 层都直接用它，不需要再回查文档。"""

    doc_id: str
    title: str
    excerpt: str
    doc_type: str
    type_label: str
    source: str
    updated_at: str
    score: float
    product_id: str = ""

    @property
    def citation(self) -> str:
        """引用说明，展示在结果下方。"""
        parts = [self.title, self.type_label]
        if self.source:
            parts.append(self.source)
        if self.updated_at:
            parts.append(f"更新于 {self.updated_at}")
        return " · ".join(parts)


#: 段落开头的 Markdown 标题标记，形如 `## 降噪要看什么`。
_HEADING = re.compile(r"^#{1,6}\s*(.+)$", re.MULTILINE)


def _demote_headings(text: str) -> str:
    """把片段里的 Markdown 标题降级成粗体行。

    片段是嵌在卡片里展示的，而卡片自己已经有标题了。原样保留 `##`
    会让小节标题渲染得和页面标题一样大，一条结果看上去像一篇文章。
    降成粗体既保住了「这是个小标题」的信息，又不喧宾夺主。
    """
    return _HEADING.sub(lambda m: f"**{m.group(1).strip()}**", text)


def _paragraphs(body: str) -> list[str]:
    return [p.strip() for p in _PARAGRAPH_SPLIT.split(body) if p.strip()]


def extract_excerpt(body: str, query: str, *, max_chars: int = EXCERPT_MAX_CHARS) -> str:
    """从正文里抽出与查询最相关的一段。

    整篇资料上千字，全展示等于没展示。做法是把正文按空行切段，
    按与查询的字面重合度排序，取最相关的开头几段拼回来。

    一段都命中不了时（比如查询与正文只在标题上重合）返回正文开头——
    总比返回空字符串好。
    """
    paragraphs = _paragraphs(body)
    if not paragraphs:
        return ""
    if len(paragraphs) == 1:
        return paragraphs[0][:max_chars]

    query_terms = token_set(query)
    ranked = sorted(
        enumerate(paragraphs),
        key=lambda pair: (
            -len(token_set(pair[1]) & query_terms),
            pair[0],  # 同分时保持原文顺序
        ),
    )

    # 按与查询的重合度取前几段，**不再要求与命中段相邻**。
    # 片段只作为 AI 作答的依据（不在界面展示），覆盖关键信息比行文连贯更重要：
    # 实测只给「命中段 + 相邻段」时，问「笔记本多重适合带出门」拿不到重量分档数字，
    # 模型只能回答「资料没覆盖」。同分时保持原文顺序（已在 ranked 的排序键里）。
    chosen = [position for position, _ in ranked[:EXCERPT_MAX_PARAGRAPHS]]

    ordered = sorted(chosen)
    text = "\n\n".join(paragraphs[i] for i in ordered)
    text = _demote_headings(text)
    return text[:max_chars].rstrip() + ("…" if len(text) > max_chars else "")


def _to_passage(document: Document, score: float, query: str) -> Passage:
    return Passage(
        doc_id=document.doc_id,
        title=document.title,
        excerpt=extract_excerpt(document.body, query),
        doc_type=document.doc_type,
        type_label=document.type_label,
        source=document.source,
        updated_at=document.updated_at,
        score=score,
        product_id=document.product_id,
    )


def search_knowledge(
    query: str,
    *,
    index: BM25Index,
    limit: int | None = None,
    min_score: float | None = None,
) -> list[Passage]:
    """检索知识语料。

    Args:
        query: 用户问题原文。
        index: 已建好的检索索引（由界面层缓存，避免每次重建）。
        limit: 最多返回几条，默认取 `config.KNOWLEDGE_MAX_RESULTS`。
        min_score: 相关度下限，默认取 `config.KNOWLEDGE_MIN_SCORE`。

    Returns:
        按相关度降序的结果。**最高分低于阈值时返回空列表**——
        调用方据此提示「没有找到相关资料」，而不是把弱相关结果端上去。
    """
    limit = config.KNOWLEDGE_MAX_RESULTS if limit is None else limit
    threshold = config.KNOWLEDGE_MIN_SCORE if min_score is None else min_score

    if not query.strip():
        return []

    hits = index.search(query, limit=limit)
    if not hits:
        return []

    best = hits[0].score
    if best < threshold:
        logger.info(
            "查询「%s」最高相关度 %.2f 低于阈值 %.2f，判定为检索不到",
            query,
            best,
            threshold,
        )
        return []

    # 相对截断：只保留与第一名同一量级的命中。绝对阈值管「有没有」，
    # 这一步管「准不准」——否则一串 1.x–2.x 的弱命中会一起被喂给模型。
    cutoff = max(threshold, best * config.KNOWLEDGE_RELATIVE_CUT)
    kept = [hit for hit in hits if hit.score >= cutoff]
    if len(kept) < len(hits):
        logger.info(
            "查询「%s」相对截断丢弃 %d 条弱命中（阈值 %.2f）",
            query,
            len(hits) - len(kept),
            cutoff,
        )

    return [_to_passage(hit.document, hit.score, query) for hit in kept]
