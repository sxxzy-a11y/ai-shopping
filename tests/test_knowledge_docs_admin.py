"""知识文档增删的后端测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import config
from src.knowledge import admin as knowledge_docs
from src.knowledge.corpus import load_documents


def _write(path: Path, title: str, doc_type: str, *, category: str = "", body: str = "正文") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"title: {title}\n"
        f"type: {doc_type}\n"
        f"category: {category}\n"
        "source: 测试\n"
        "updated_at: 2026-10-18\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_create_document_writes_front_matter_and_is_loadable(tmp_path: Path):
    target = knowledge_docs.create_document(
        title="耳机音质选购指南",
        doc_type="service",
        body="## 音质\n\n先看编码格式。",
        knowledge_dir=tmp_path,
    )

    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "title: 耳机音质选购指南" in text
    assert "type: service" in text

    documents = load_documents(tmp_path)
    created = next(d for d in documents if d.title == "耳机音质选购指南")
    assert created.body.startswith("## 音质")
    assert created.source_path == str(target)


def test_category_document_requires_a_known_category(tmp_path: Path):
    with pytest.raises(knowledge_docs.KnowledgeDocError):
        knowledge_docs.create_document(
            title="某指南", doc_type="category", body="正文", knowledge_dir=tmp_path
        )
    with pytest.raises(knowledge_docs.KnowledgeDocError):
        knowledge_docs.create_document(
            title="某指南",
            doc_type="category",
            category="tablet",  # 未登记
            body="正文",
            knowledge_dir=tmp_path,
        )


def test_second_guide_for_the_same_category_is_rejected(tmp_path: Path):
    _write(tmp_path / "category" / "laptop.md", "笔记本指南", "category", category="laptop")

    with pytest.raises(knowledge_docs.KnowledgeDocError) as excinfo:
        knowledge_docs.create_document(
            title="另一份笔记本指南",
            doc_type="category",
            category="laptop",
            body="正文",
            knowledge_dir=tmp_path,
        )
    assert "已有选购指南" in str(excinfo.value)


def test_duplicate_titles_get_unique_files(tmp_path: Path):
    first = knowledge_docs.create_document(
        title="常见问题", doc_type="service", body="一", knowledge_dir=tmp_path
    )
    second = knowledge_docs.create_document(
        title="常见问题", doc_type="service", body="二", knowledge_dir=tmp_path
    )

    assert first != second
    assert first.name == "常见问题.md"
    assert second.name == "常见问题-2.md"


def test_delete_document_removes_the_file(tmp_path: Path):
    path = knowledge_docs.create_document(
        title="待删资料", doc_type="service", body="正文", knowledge_dir=tmp_path
    )
    document = next(d for d in load_documents(tmp_path) if d.title == "待删资料")

    removed = knowledge_docs.delete_document(document.doc_id, knowledge_dir=tmp_path)

    assert removed == path
    assert not path.exists()
    assert all(d.title != "待删资料" for d in load_documents(tmp_path))


def test_product_documents_cannot_be_deleted(tmp_path: Path):
    with pytest.raises(knowledge_docs.KnowledgeDocError) as excinfo:
        knowledge_docs.delete_document("product:LP001", knowledge_dir=tmp_path)
    assert "商品级" in str(excinfo.value) or "找不到" in str(excinfo.value)


def test_delete_missing_document_raises(tmp_path: Path):
    with pytest.raises(knowledge_docs.KnowledgeDocError):
        knowledge_docs.delete_document("service:missing", knowledge_dir=tmp_path)
