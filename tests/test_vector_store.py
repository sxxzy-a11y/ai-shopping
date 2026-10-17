"""向量库测试：增量索引、过期判定、余弦检索。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.knowledge.chunking import Slice, split_corpus
from src.knowledge.corpus import Document, TYPE_CATEGORY
from src.knowledge.vector_store import VectorStore


class FakeEmbedding:
    """按关键词给确定性向量，便于断言排序。"""

    def __init__(self, model: str = "stub", dim: int = 3) -> None:
        self.model = model
        self.dim = dim
        self.configured = True
        self.calls: list[list[str]] = []

    def embed(self, texts):
        texts = list(texts)
        self.calls.append(texts)
        vectors = []
        for text in texts:
            vectors.append(
                [
                    1.0 if "重量" in text else 0.0,
                    1.0 if "拍照" in text else 0.0,
                    0.1,
                ]
            )
        return vectors


def _docs() -> list[Document]:
    return [
        Document(
            doc_id="category:laptop",
            title="笔记本指南",
            body="## 重量\n\n整机 1.4kg 适合带出门。",
            doc_type=TYPE_CATEGORY,
            source="本项目整理",
            updated_at="2026-10-17",
        ),
        Document(
            doc_id="category:phone",
            title="手机指南",
            body="## 拍照\n\n拍照档位比像素更重要。",
            doc_type=TYPE_CATEGORY,
            source="本项目整理",
            updated_at="2026-10-17",
        ),
    ]


@pytest.fixture
def store(tmp_path):
    return VectorStore(path=tmp_path / "vectors.db")


def test_build_index_marks_everything_ready(store):
    slices = split_corpus(_docs())
    service = FakeEmbedding()

    result = store.build_index(slices, service=service)

    assert result.embedded == len(slices)
    assert result.skipped == 0
    stats = store.stats(slices, model=service.model, dim=service.dim)
    assert stats.ready == len(slices)
    assert stats.generation_needed == 0


def test_second_build_skips_unchanged_slices(store):
    slices = split_corpus(_docs())
    service = FakeEmbedding()
    store.build_index(slices, service=service)
    calls_before = len(service.calls)

    result = store.build_index(slices, service=service)

    assert result.embedded == 0
    assert result.skipped == len(slices)
    assert len(service.calls) == calls_before, "未变化的切片不应再次调用向量服务"


def test_changed_content_rebuilds_only_that_document(store):
    docs = _docs()
    service = FakeEmbedding()
    store.build_index(split_corpus(docs), service=service)

    changed = [
        docs[0],
        replace(docs[1], body="## 拍照\n\n夜景算法同样关键。"),
    ]
    slices = split_corpus(changed)
    result = store.build_index(slices, service=service)

    assert result.embedded == 1, "只有被修改的文档需要重建"
    stats = store.stats(slices, model=service.model, dim=service.dim)
    assert stats.ready == len(slices)


def test_model_change_marks_all_stale(store):
    slices = split_corpus(_docs())
    store.build_index(slices, service=FakeEmbedding(model="old-model"))

    stats = store.stats(slices, model="new-model", dim=3)

    assert stats.ready == 0
    assert stats.stale == len(slices)


def test_removed_documents_are_cleaned(store):
    service = FakeEmbedding()
    store.build_index(split_corpus(_docs()), service=service)

    remaining = split_corpus(_docs()[1:])
    result = store.build_index(remaining, service=service)

    assert result.removed >= 1
    stats = store.stats(remaining, model=service.model, dim=service.dim)
    assert stats.ready == len(remaining)


def test_search_orders_by_cosine(store):
    slices = split_corpus(_docs())
    service = FakeEmbedding()
    store.build_index(slices, service=service)

    laptop_hits = store.search(
        [1.0, 0.0, 0.1], model=service.model, dim=service.dim, min_score=0.0
    )
    phone_hits = store.search(
        [0.0, 1.0, 0.1], model=service.model, dim=service.dim, min_score=0.0
    )

    assert laptop_hits and "笔记本指南" == laptop_hits[0].slice.title
    assert phone_hits and "手机指南" == phone_hits[0].slice.title


def test_search_applies_threshold(store):
    slices = split_corpus(_docs())
    service = FakeEmbedding()
    store.build_index(slices, service=service)

    # 与两条切片都近乎正交的查询向量——最高分也低于阈值
    hits = store.search(
        [0.0, 0.0, 1.0], model=service.model, dim=service.dim, min_score=0.5
    )
    assert hits == []


def test_search_ignores_vectors_from_another_model(store):
    slices = split_corpus(_docs())
    store.build_index(slices, service=FakeEmbedding(model="old-model"))

    hits = store.search(
        [1.0, 0.0, 0.1], model="new-model", dim=3, min_score=0.0
    )
    assert hits == []


def test_search_limits_results(store):
    slices = split_corpus(_docs())
    service = FakeEmbedding()
    store.build_index(slices, service=service)

    hits = store.search(
        [1.0, 1.0, 0.1], model=service.model, dim=service.dim, limit=1, min_score=0.0
    )
    assert len(hits) == 1
