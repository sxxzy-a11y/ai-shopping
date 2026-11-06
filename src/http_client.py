"""进程内共享的 httpx 客户端与重试策略。

为什么共享：对话模型与向量化原本各自 `httpx.Client(...)`，每次请求都要
重新建 TCP/TLS 连接。演示环境的网络往往比算力慢，握手成本可能高于传输
本身；一个带连接池的客户端能把这部分省掉。

为什么超时按请求传：客户端上的 timeout 是「首次创建者」的配置，之后改环境
变量不生效。所以客户端只设连接超时，读超时由调用方每次传给 `post()`。

为什么单独成模块：`ai_service` 与 `embeddings` 都要用，放在任一处都会让另
一处反向依赖。这里只依赖标准库与 httpx，没有项目内依赖。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger("zhigou.http")

#: 连接池上限。演示场景并发很低，取一个够用又不夸张的值。
_MAX_CONNECTIONS = 16
_MAX_KEEPALIVE = 8
_CONNECT_TIMEOUT_S = 10.0
_DEFAULT_TIMEOUT_S = 60.0

#: 一次调用最多尝试次数（含首次）。只对「可能自愈」的失败重试。
_MAX_ATTEMPTS = 3
#: 指数退避基数（秒）。第 n 次重试前等待 base * 3^(n-1)。
_RETRY_BASE_S = 0.3
#: 这些状态码通常是上游抖动或限流，值得再试一次。
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

_CLIENT: httpx.Client | None = None
_LOCK = threading.Lock()


def get_client() -> httpx.Client:
    """取进程内共享客户端（懒加载）。httpx 的连接池本身线程安全。"""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    with _LOCK:
        if _CLIENT is None:
            _CLIENT = httpx.Client(
                limits=httpx.Limits(
                    max_connections=_MAX_CONNECTIONS,
                    max_keepalive_connections=_MAX_KEEPALIVE,
                ),
                timeout=httpx.Timeout(_DEFAULT_TIMEOUT_S, connect=_CONNECT_TIMEOUT_S),
            )
    return _CLIENT


def close_client() -> None:
    """关闭共享客户端。测试与进程退出时用；关闭后再取会重新创建。"""
    global _CLIENT
    with _LOCK:
        if _CLIENT is not None:
            _CLIENT.close()
            _CLIENT = None


def _is_retryable_status(status: int) -> bool:
    return status in _RETRYABLE_STATUS


def _sleep(seconds: float) -> None:
    """退避等待。抽成函数是为了测试能替换掉——被测的是「有没有重试」，
    不是「等了几秒」，让测试真睡 1.2 秒只会拖慢套件。"""
    time.sleep(seconds)


def post_with_retry(
    url: str,
    *,
    json: dict[str, Any],
    headers: dict[str, str],
    timeout_s: float,
    client: httpx.Client | None = None,
) -> httpx.Response:
    """发一个 POST，对超时 / 连接失败 / 可重试状态码做有限次退避重试。

    只重试「可能自愈」的失败：鉴权失败、请求格式错误这类 4xx 立刻返回，
    重试没有意义。重试耗尽后仍把最后一次的响应或异常交给调用方处理，
    由上层决定如何降级——这里不吞异常。

    Args:
        timeout_s: 单次尝试的读超时。总耗时上限约为 `timeout_s * _MAX_ATTEMPTS`
            再加上退避时间。
    """
    target = client or get_client()
    last_error: httpx.HTTPError | None = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = target.post(url, json=json, headers=headers, timeout=timeout_s)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt >= _MAX_ATTEMPTS:
                raise
            logger.warning(
                "请求失败（第 %d/%d 次），准备重试：%s",
                attempt,
                _MAX_ATTEMPTS,
                type(exc).__name__,
            )
            _sleep(_RETRY_BASE_S * (3 ** (attempt - 1)))
            continue

        if _is_retryable_status(response.status_code) and attempt < _MAX_ATTEMPTS:
            logger.warning(
                "上游返回 %d（第 %d/%d 次），准备重试",
                response.status_code,
                attempt,
                _MAX_ATTEMPTS,
            )
            _sleep(_RETRY_BASE_S * (3 ** (attempt - 1)))
            continue

        if attempt > 1:
            logger.info("第 %d 次尝试成功（HTTP %d）", attempt, response.status_code)
        return response

    # 理论不可达：循环里要么 return，要么 raise。留作防御。
    if last_error is not None:
        raise last_error
    raise httpx.HTTPError("请求未产生响应")
