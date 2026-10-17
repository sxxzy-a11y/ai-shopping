"""Embedding 调用的传输层。

与 `ai_service` 同样的边界：只管发请求、拿向量、把失败翻译成领域异常。
OpenAI 兼容的 `/embeddings` 协议（DashScope、SiliconFlow、OpenAI 等均支持）。

设计要点：
- **DeepSeek 没有 embeddings 接口**，所以不能复用对话模型密钥——独立配置。
- 批量请求：多数服务单次上限 10~25 条，这里按 10 条一批。
- 维度校验：返回维度必须与配置一致，否则整批拒绝——向量混用是静默错误，
  检索分数会失真但不会报错，比直接失败更糟。
- 密钥只从环境变量读，日志与异常一律脱敏。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

from src import config
from src.ai_service import redact
from src.errors import (
    AINotConfigured,
    UpstreamAuthError,
    UpstreamResponseError,
    UpstreamTimeout,
    UpstreamUnavailable,
)

logger = logging.getLogger("zhigou.embedding")

#: 单次请求的最大文本条数。多数兼容服务上限为 10–25，取保守值。
BATCH_SIZE = 10


class EmbeddingService:
    """OpenAI 兼容 `/embeddings` 的调用封装。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dim: int | None = None,
        timeout_s: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else config.embedding_api_key()
        self._base_url = (base_url or config.embedding_base_url()).rstrip("/")
        self._model = model or config.embedding_model()
        self._dim = dim if dim is not None else config.embedding_dim()
        self._timeout_s = timeout_s or config.embedding_timeout_s()
        self._client = client

    # -- 查询属性 --------------------------------------------------------

    @property
    def configured(self) -> bool:
        """是否配置了可用密钥。没有密钥就没有任何请求可发。"""
        return bool(self._api_key)

    @property
    def model(self) -> str:
        return self._model

    @property
    def dim(self) -> int:
        return self._dim

    def describe(self) -> dict[str, str]:
        """给界面看的配置摘要，**不含密钥明文**。"""
        key = self._api_key or ""
        hint = f"{key[:3]}****{key[-4:]}" if len(key) > 8 else ("已配置" if key else "未配置")
        return {"base_url": self._base_url, "model": self._model, "dim": str(self._dim), "key_hint": hint}

    # -- 调用 ------------------------------------------------------------

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """把一批文本变成向量。

        Raises:
            AINotConfigured: 未配置密钥。
            UpstreamTimeout / UpstreamAuthError / UpstreamUnavailable /
            UpstreamResponseError: 网络、鉴权、服务不可用、响应非法或维度不符。
        """
        if not self.configured:
            raise AINotConfigured(f"未配置 {config.EMBEDDING_API_KEY_ENV}，无法进行向量化。")

        cleaned = [t for t in texts]
        if not cleaned:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(cleaned), BATCH_SIZE):
            batch = cleaned[start : start + BATCH_SIZE]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, batch: Sequence[str]) -> list[list[float]]:
        payload = {"model": self._model, "input": list(batch)}
        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        client = self._client or httpx.Client(timeout=self._timeout_s)
        owns_client = self._client is None
        try:
            response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise UpstreamTimeout("向量化服务响应超时，请稍后重试。") from exc
        except httpx.HTTPError as exc:
            logger.warning("向量化请求失败：%s", redact(str(exc)))
            raise UpstreamUnavailable("向量化服务暂时不可用，请检查网络后重试。") from exc
        finally:
            if owns_client:
                client.close()

        if response.status_code in (401, 403):
            raise UpstreamAuthError("向量化服务鉴权失败，请检查 Embedding 密钥是否有效。")
        if response.status_code >= 500:
            raise UpstreamUnavailable("向量化服务暂时不可用，请稍后重试。")
        if response.status_code != 200:
            raise UpstreamResponseError(
                f"向量化服务返回了异常状态（HTTP {response.status_code}）。"
            )

        try:
            body = response.json()
            data = body["data"]
            ordered = sorted(data, key=lambda item: item.get("index", 0))
            vectors = [list(map(float, item["embedding"])) for item in ordered]
        except (ValueError, KeyError, TypeError) as exc:
            raise UpstreamResponseError("向量化服务返回的内容无法解析。") from exc

        if len(vectors) != len(batch):
            raise UpstreamResponseError(
                f"向量化服务返回条数不符：请求 {len(batch)} 条，返回 {len(vectors)} 条。"
            )
        for vector in vectors:
            if len(vector) != self._dim:
                raise UpstreamResponseError(
                    f"向量维度不符：配置为 {self._dim} 维，服务返回 {len(vector)} 维。"
                    "请检查 ZHIGOU_EMBEDDING_MODEL 与 ZHIGOU_EMBEDDING_DIM 是否匹配。"
                )
        return vectors


_service: EmbeddingService | None = None


def get_service() -> EmbeddingService:
    """进程内单例。测试通过 monkeypatch 替换本函数。"""
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service


def reset_service() -> None:
    """清掉单例（测试与切换配置时使用）。"""
    global _service
    _service = None
