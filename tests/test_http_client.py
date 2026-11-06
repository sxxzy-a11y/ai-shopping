"""共享 HTTP 客户端与重试策略。

重试只覆盖「可能自愈」的失败：超时、连接错误、429/5xx。
鉴权失败与请求格式错误不重试——那类问题再试一次也是一样的结果。
"""

from __future__ import annotations

import httpx
import pytest

from src import http_client

URL = "https://example.invalid/v1/chat/completions"


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_retries_retryable_status_then_succeeds():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"ok": True})

    response = http_client.post_with_retry(
        URL, json={}, headers={}, timeout_s=1.0, client=_client(handler)
    )

    assert response.status_code == 200
    assert len(calls) == 3, "503 应重试到成功"


def test_does_not_retry_client_errors():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, text="bad key")

    response = http_client.post_with_retry(
        URL, json={}, headers={}, timeout_s=1.0, client=_client(handler)
    )

    assert response.status_code == 401
    assert len(calls) == 1, "鉴权失败重试没有意义"


def test_returns_last_response_when_retries_exhausted():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, text="boom")

    response = http_client.post_with_retry(
        URL, json={}, headers={}, timeout_s=1.0, client=_client(handler)
    )

    assert response.status_code == 500
    assert len(calls) == http_client._MAX_ATTEMPTS


def test_raises_after_transport_failures():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(httpx.ConnectError):
        http_client.post_with_retry(
            URL, json={}, headers={}, timeout_s=1.0, client=_client(handler)
        )

    assert len(calls) == http_client._MAX_ATTEMPTS


def test_shared_client_is_reused_and_recreated_after_close():
    first = http_client.get_client()
    try:
        assert http_client.get_client() is first, "共享客户端应在进程内复用"
    finally:
        http_client.close_client()

    second = http_client.get_client()
    try:
        assert second is not first, "关闭后应重新创建，而不是返回已关闭的对象"
    finally:
        http_client.close_client()
