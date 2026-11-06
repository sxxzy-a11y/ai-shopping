"""向量库测试：增量索引、过期判定、余弦检索。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.knowledge.chunking import split_corpus
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

    hits = store.search([1.0, 0.0, 0.1], model="new-model", dim=3, min_score=0.0)
    assert hits == []


def test_search_limits_results(store):
    slices = split_corpus(_docs())
    service = FakeEmbedding()
    store.build_index(slices, service=service)

    hits = store.search(
        [1.0, 1.0, 0.1], model=service.model, dim=service.dim, limit=1, min_score=0.0
    )
    assert len(hits) == 1


# --------------------------------------------------------------------------
# 边界输入、损坏数据与缓存
# --------------------------------------------------------------------------


def test_search_rejects_invalid_query_vectors(store):
    """异常输入返回空结果，不抛异常——检索不能让整页问答挂掉。"""
    store.build_index(split_corpus(_docs()), service=FakeEmbedding())
    kwargs = {"model": "stub", "dim": 3, "min_score": 0.0}

    for bad in (
        [],
        [0.0, 0.0, 0.0],
        [float("nan"), 0.0, 0.1],
        [float("inf"), 0.0, 0.1],
        [[1.0, 0.0, 0.1]],
    ):
        assert store.search(bad, **kwargs) == [], f"不该接受查询向量 {bad!r}"

    assert store.search([1.0, 0.0, 0.1], limit=0, **kwargs) == []
    assert store.search([1.0, 0.0, 0.1], limit=-1, **kwargs) == []


def test_search_skips_corrupt_embedding_rows(tmp_path, caplog):
    """一条坏数据不该把整条语义检索打回关键词模式。"""
    from src.database import connect

    path = tmp_path / "v.db"
    store = VectorStore(path=path)
    service = FakeEmbedding()
    slices = split_corpus(_docs())
    store.build_index(slices, service=service)

    with connect(path) as connection:
        connection.execute(
            "UPDATE knowledge_vectors SET embedding = ? WHERE slice_id = ?",
            ("{ not json", slices[0].slice_id),
        )
        connection.commit()

    with caplog.at_level("WARNING", logger="zhigou.knowledge.vector"):
        hits = store.search(
            [1.0, 0.0, 0.1], model=service.model, dim=service.dim, min_score=0.0
        )

    assert hits, "其余完好的切片仍应可检索"
    assert all(hit.slice.slice_id != slices[0].slice_id for hit in hits)
    assert "损坏的向量行" in caplog.text, "跳过坏行要留可排查的日志"


def test_rebuilt_index_is_visible_to_search(store):
    """缓存不能让刚重建的索引读到旧矩阵。"""
    service = FakeEmbedding()
    docs = _docs()
    store.build_index(split_corpus(docs), service=service)
    assert store.search(
        [0.0, 1.0, 0.1], model=service.model, dim=service.dim, min_score=0.0
    )

    # 只留笔记本，重建后「拍照」查询不该再命中手机指南
    store.build_index(split_corpus(docs[:1]), service=service)
    hits = store.search(
        [0.0, 1.0, 0.1], model=service.model, dim=service.dim, min_score=0.0
    )

    assert all(hit.slice.title != "手机指南" for hit in hits), "读到了重建前的旧矩阵"


def test_matrix_is_reused_across_instances(tmp_path, monkeypatch):
    """界面层每次新建 VectorStore，缓存必须跨实例生效，否则优化等于没做。"""
    path = tmp_path / "v.db"
    store = VectorStore(path=path)
    service = FakeEmbedding()
    store.build_index(split_corpus(_docs()), service=service)
    # 先跑一次建立缓存；之后才打桩，验证的是「后续检索不再全表读」
    store.search([1.0, 0.0, 0.1], model=service.model, dim=service.dim, min_score=0.0)

    calls: list[int] = []
    original_rows = VectorStore._rows

    def spy(self):
        calls.append(1)
        return original_rows(self)

    monkeypatch.setattr(VectorStore, "_rows", spy)
    for _ in range(2):
        VectorStore(path=path).search(
            [1.0, 0.0, 0.1], model=service.model, dim=service.dim, min_score=0.0
        )

    assert not calls, "两次检索都应命中矩阵缓存，不该再全表读 + 逐行解析"
