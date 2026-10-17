"""切片规则测试：标题分段、超长切分、稳定 ID。"""

from __future__ import annotations

from src.knowledge.chunking import MAX_SLICE_CHARS, split_corpus, split_document
from src.knowledge.corpus import Document, TYPE_CATEGORY


def _doc(body: str, *, title: str = "笔记本电脑选购指南") -> Document:
    return Document(
        doc_id="category:laptop",
        title=title,
        body=body,
        doc_type=TYPE_CATEGORY,
        source="本项目整理",
        updated_at="2026-10-17",
    )


def test_splits_by_second_level_headings():
    body = "开头说明。\n\n## 重量\n\n整机 1.4kg。\n\n## 续航\n\n标称 10 小时。"
    slices = split_document(_doc(body))

    headings = [s.heading for s in slices]
    assert headings == ["", "重量", "续航"]
    assert slices[1].content == "整机 1.4kg。"


def test_long_section_is_split_by_paragraphs():
    paragraph = "这是一段很长的说明。" * 20  # 200 字
    body = "## 参数\n\n" + "\n\n".join([paragraph] * 4)
    slices = split_document(_doc(body))

    assert len(slices) > 1
    assert all(len(s.content) <= MAX_SLICE_CHARS for s in slices)
    # 标题只出现一次：后续切片是同一小节的延续
    assert all(s.heading == "参数" for s in slices)


def test_slice_ids_are_stable_and_sequential():
    body = "## 甲\n\n内容一。\n\n## 乙\n\n内容二。"
    first = split_document(_doc(body))
    second = split_document(_doc(body))

    assert [s.slice_id for s in first] == [s.slice_id for s in second]
    assert first[0].slice_id == "category:laptop#1"
    assert first[1].slice_id == "category:laptop#2"


def test_embedding_text_carries_title_and_heading():
    slices = split_document(_doc("## 重量\n\n整机 1.4kg。"))
    text = slices[0].embedding_text

    assert "笔记本电脑选购指南" in text
    assert "重量" in text
    assert "整机 1.4kg" in text


def test_empty_body_produces_no_slices():
    assert split_document(_doc("   ")) == []


def test_corpus_order_is_preserved():
    docs = [_doc("## A\n\n内容。", title="文档一"), _doc("## B\n\n内容。", title="文档二")]
    slices = split_corpus(docs)

    assert [s.title for s in slices] == ["文档一", "文档二"]
