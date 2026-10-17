"""检索调度测试：向量优先、关键词回退、失败降级。"""

from __future__ import annotations

import pytest

from src.errors import UpstreamUnavailable
from src.knowledge import retrieval
from src.knowledge.chunking import split_corpus
from src.knowledge.corpus import Document, TYPE_CATEGORY
from src.knowledge.index import BM25Index
from src.knowledge.vector_store import VectorStore


class FakeEmbedding:
    configured = True
    model = "stub"
    dim = 3

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def embed(self, texts):
        if self.fail:
            raise UpstreamUnavailable("向量服务挂了")
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


def _index() -> BM25Index:
    return BM25Index(_docs())


def test_uses_vector_when_configured_and_indexed(tmp_path):
    service = FakeEmbedding()
    store = VectorStore(path=tmp_path / "v.db")
    slices = split_corpus(_docs())
    store.build_index(slices, service=service)

    result = retrieval.retrieve("重量", index=_index(), store=store, service=service)

    assert result.mode == "vector"
    assert result.passages
    assert "笔记本指南" == result.passages[0].title


def test_falls_back_to_keyword_when_unconfigured(monkeypatch):
    from src import config

    # 小语料下 BM25 分数天然低，测试里放开绝对阈值，专测「走向关键词」这条路径
    monkeypatch.setattr(config, "KNOWLEDGE_MIN_SCORE", 0.0)
    service = FakeEmbedding()
    service.configured = False

    result = retrieval.retrieve("重量", index=_index(), store=None, service=service)

    assert result.mode == "keyword"
    assert result.passages
    assert result.note == ""


def test_falls_back_when_vector_service_fails(tmp_path, monkeypatch):
    from src import config

    monkeypatch.setattr(config, "KNOWLEDGE_MIN_SCORE", 0.0)
    good = FakeEmbedding()
    store = VectorStore(path=tmp_path / "v.db")
    store.build_index(split_corpus(_docs()), service=good)

    result = retrieval.retrieve(
        "重量", index=_index(), store=store, service=FakeEmbedding(fail=True)
    )

    assert result.mode == "keyword"
    assert result.passages, "回退后仍应有关键词结果"
    assert "回退" in result.note


def test_empty_vector_result_does_not_fall_back(tmp_path, monkeypatch):
    """语义上不相关就是没有资料——不能悄悄改成字面匹配。"""
    from src import config

    # 关键词侧把阈值放开：如果实现错误地回退了，这里就会拿到结果
    monkeypatch.setattr(config, "KNOWLEDGE_MIN_SCORE", 0.0)
    monkeypatch.setattr(config, "KNOWLEDGE_MIN_COSINE", 0.9)

    service = FakeEmbedding()
    store = VectorStore(path=tmp_path / "v.db")
    store.build_index(split_corpus(_docs()), service=service)

    result = retrieval.retrieve("天气", index=_index(), store=store, service=service)

    assert result.mode == "vector"
    assert result.passages == []
