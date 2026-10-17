"""Embedding 客户端测试：批量、维度、错误翻译与脱敏。"""

from __future__ import annotations

import httpx
import pytest

from src.errors import (
    AINotConfigured,
    UpstreamAuthError,
    UpstreamResponseError,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from src.knowledge.embeddings import BATCH_SIZE, EmbeddingService


def _service(handler, *, dim: int = 3, model: str = "stub-embed") -> EmbeddingService:
    return EmbeddingService(
        api_key="sk-test-0123456789abcdef",
        base_url="https://example.invalid/v1",
        model=model,
        dim=dim,
        timeout_s=5,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _ok(vectors: list[list[float]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": [
                {"index": index, "embedding": vector}
                for index, vector in enumerate(vectors)
            ]
        },
    )


def test_embed_returns_vectors_in_order():
    seen: list[dict] = []

    def handler(request):
        import json

        body = json.loads(request.content)
        seen.append(body)
        return _ok([[1.0, 0.0, 0.0] for _ in body["input"]])

    vectors = _service(handler).embed(["甲", "乙"])
    assert vectors == [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    assert seen[0]["model"] == "stub-embed"
    assert seen[0]["input"] == ["甲", "乙"]


def test_embed_splits_into_batches():
    batches: list[int] = []

    def handler(request):
        import json

        body = json.loads(request.content)
        batches.append(len(body["input"]))
        return _ok([[0.1, 0.2, 0.3] for _ in body["input"]])

    texts = [f"文本 {index}" for index in range(BATCH_SIZE * 2 + 3)]
    vectors = _service(handler).embed(texts)
    assert len(vectors) == len(texts)
    assert batches == [BATCH_SIZE, BATCH_SIZE, 3]


def test_unconfigured_service_raises_without_network():
    service = EmbeddingService(api_key="", base_url="https://example.invalid/v1")

    def handler(request):  # pragma: no cover —— 不该被调用
        raise AssertionError("未配置密钥时不应发请求")

    service = EmbeddingService(
        api_key="",
        base_url="https://example.invalid/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(AINotConfigured):
        service.embed(["x"])


def test_dimension_mismatch_is_rejected():
    service = _service(lambda request: _ok([[0.1, 0.2]]), dim=3)
    with pytest.raises(UpstreamResponseError) as excinfo:
        service.embed(["x"])
    assert "维度" in str(excinfo.value)


def test_auth_error_is_translated():
    service = _service(lambda request: httpx.Response(401, text="bad key"))
    with pytest.raises(UpstreamAuthError):
        service.embed(["x"])


def test_timeout_is_translated():
    def handler(request):
        raise httpx.TimeoutException("slow")

    service = _service(handler)
    with pytest.raises(UpstreamTimeout):
        service.embed(["x"])


def test_server_error_is_translated():
    service = _service(lambda request: httpx.Response(503, text="down"))
    with pytest.raises(UpstreamUnavailable):
        service.embed(["x"])


def test_malformed_body_is_rejected():
    service = _service(lambda request: httpx.Response(200, json={"nope": 1}))
    with pytest.raises(UpstreamResponseError):
        service.embed(["x"])


def test_describe_never_leaks_the_full_key():
    service = _service(lambda request: _ok([[0, 0, 0]]))
    described = service.describe()
    assert "sk-test-0123456789abcdef" not in described["key_hint"]
    assert described["model"] == "stub-embed"
    assert described["dim"] == "3"
