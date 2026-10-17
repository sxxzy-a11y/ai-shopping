"""知识文档切片。

为什么这样切：知识文档本身就是按 `## 小节` 写的，按语义边界切比定长滑窗
可解释得多——「这篇切片讲的是整机重量」比「第 3 个 500 字窗口」更像人话。
单段仍然超长时按空行继续切，避免一个切片塞进整篇文档。

切片 ID 稳定为 `doc_id#序号`：语料不变时重复生成不会产生重复向量，
内容变化时序号可能不同——由内容哈希负责识别「需要重建」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.knowledge.corpus import Document

#: 单片正文的上限（字符）。超过则按段落继续切。
MAX_SLICE_CHARS = 500

#: Markdown 二级及以下标题作为小节边界。
_HEADING = re.compile(r"^##\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Slice:
    """一条可向量化的知识切片。"""

    slice_id: str
    doc_id: str
    title: str
    heading: str
    content: str
    doc_type: str
    source: str
    updated_at: str
    product_id: str = ""

    @property
    def embedding_text(self) -> str:
        """送去向量化的文本：标题 + 小节名 + 正文。

        标题前缀不是装饰：切片脱离文档后往往只剩半句话，
        带上「哪篇文档、哪一节」能显著改善语义匹配。
        """
        parts = [self.title]
        if self.heading:
            parts.append(self.heading)
        parts.append(self.content)
        return "\n".join(parts)


def _split_long(text: str, limit: int) -> list[str]:
    """把超长小节按空行切到上限内。"""
    if len(text) <= limit:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    buffer: list[str] = []
    size = 0

    for paragraph in paragraphs:
        # 单段本身就超限：硬切
        while len(paragraph) > limit:
            pieces.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        if size + len(paragraph) + 2 > limit and buffer:
            pieces.append("\n\n".join(buffer))
            buffer, size = [], 0
        buffer.append(paragraph)
        size += len(paragraph) + 2

    if buffer:
        pieces.append("\n\n".join(buffer))
    return pieces or [text[:limit]]


def split_document(document: Document, *, limit: int = MAX_SLICE_CHARS) -> list[Slice]:
    """把一篇文档切成切片。"""
    body = document.body.strip()
    if not body:
        return []

    # 按二级标题切小节；第一段（第一个标题之前）单独成节
    matches = list(_HEADING.finditer(body))
    sections: list[tuple[str, str]] = []
    if not matches:
        sections.append(("", body))
    else:
        head = body[: matches[0].start()].strip()
        if head:
            sections.append(("", head))
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            sections.append((match.group(1).strip(), body[start:end].strip()))

    slices: list[Slice] = []
    counter = 0
    for heading, text in sections:
        if not text:
            continue
        for piece in _split_long(text, limit):
            counter += 1
            slices.append(
                Slice(
                    slice_id=f"{document.doc_id}#{counter}",
                    doc_id=document.doc_id,
                    title=document.title,
                    heading=heading,
                    content=piece,
                    doc_type=document.doc_type,
                    source=document.source,
                    updated_at=document.updated_at,
                    product_id=document.product_id,
                )
            )
    return slices


def split_corpus(documents: list[Document], *, limit: int = MAX_SLICE_CHARS) -> list[Slice]:
    """把整个语料切成切片，保持文档顺序。"""
    slices: list[Slice] = []
    for document in documents:
        slices.extend(split_document(document, limit=limit))
    return slices
