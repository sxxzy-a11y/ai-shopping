"""大模型调用的传输层。

职责边界
--------
本模块只管「把请求发出去、把响应拿回来、把失败翻译成领域异常」。
提示词怎么写、结果怎么映射回 `Demand`，在 `src/ai_enhance.py`。

设计要点（design.md D5）
-----------------------
- 用已装的 `httpx` 直连 OpenAI 兼容接口，不引入官方 SDK：
  零新增依赖，且兼容任意兼容端点（DeepSeek、自建代理等）。
- 密钥只从环境变量读，**任何情况下都不写进日志、异常信息或返回值**。
- 所有失败都翻译成具名领域异常，界面统一转中文提示并降级到本地规则模式。

关于推理模型
------------
DeepSeek 的 `deepseek-flash` / `deepseek-v4-pro` 是**推理模型**：推理过程
（`reasoning_content`）也计入 `max_tokens`。上限给小了会出现正文为空、
`finish_reason=length` 的情况——这不是「模型没回答」，而是「额度被推理吃光了」，
必须当成失败处理并降级，绝不能把空字符串当成有效结果往下传。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx

from src import config
from src.errors import (
    AINotConfigured,
    UpstreamAuthError,
    UpstreamResponseError,
    UpstreamTimeout,
    UpstreamUnavailable,
)

logger = logging.getLogger("zhigou.ai")

#: 密钥在日志里的替代文本。
_REDACTED = "sk-****"


def redact(text: str) -> str:
    """把文本里的密钥抹掉。

    日志和异常信息都要过这一道。宁可多抹一点，也不能让密钥漏进日志文件。
    """
    key = config.llm_api_key()
    if key and key in text:
        text = text.replace(key, _REDACTED)
    # 兜底：任何形如 sk-xxx 的长串都抹掉，覆盖「换了个 key 但没更新环境变量」的情况
    return re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}", _REDACTED, text)


@dataclass(frozen=True)
class LLMResponse:
    """一次模型调用的结果。"""

    content: str
    model: str
    total_tokens: int = 0
    reasoning_tokens: int = 0
    #: 是否因为 token 用尽被截断。为真时 content 不可信。
    truncated: bool = False


class AIService:
    """OpenAI 兼容接口的调用封装。

    可以注入 `httpx.Client`（测试用 `httpx.MockTransport`），
    这样降级路径不需要真实密钥就能覆盖。
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        max_tokens: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else config.llm_api_key()
        self._base_url = (base_url or config.llm_base_url()).rstrip("/")
        self._model = model or config.llm_model()
        self._timeout = timeout_s if timeout_s is not None else config.llm_timeout_s()
        self._max_tokens = max_tokens or config.llm_max_tokens()
        self._client = client

    # --- 状态 -------------------------------------------------------------

    @property
    def configured(self) -> bool:
        """是否配置了密钥。为假时调用方应直接走本地模式，不要发请求。"""
        return bool(self._api_key)

    @property
    def model(self) -> str:
        return self._model

    def describe(self) -> dict[str, object]:
        """给界面看的配置摘要，**不含密钥**。"""
        return {
            "configured": self.configured,
            "model": self._model,
            "base_url": self._base_url,
            "timeout_s": self._timeout,
            "max_tokens": self._max_tokens,
            "key_hint": _REDACTED if self.configured else "未配置",
        }

    # --- 调用 -------------------------------------------------------------

    def _build_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(timeout=self._timeout)

    def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """发一次对话补全请求。

        Raises:
            AINotConfigured: 没配密钥。**在发请求之前**就抛出。
            UpstreamTimeout / UpstreamAuthError / UpstreamUnavailable /
            UpstreamResponseError: 上游各种失败。
        """
        if not self.configured:
            raise AINotConfigured(
                f"未配置大模型 API 密钥（环境变量 {config.LLM_API_KEY_ENV}），"
                f"已使用本地规则模式。"
            )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens or self._max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        client = self._build_client()
        owned = self._client is None
        try:
            response = client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise UpstreamTimeout(
                f"AI 服务响应超时（超过 {self._timeout:.0f} 秒未返回），"
                f"已切换到本地规则模式完成本次分析。",
                detail=redact(f"{type(exc).__name__}: {exc}"),
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(
                "AI 服务暂时不可用，已切换到本地规则模式完成本次分析。",
                detail=redact(f"{type(exc).__name__}: {exc}"),
            ) from exc
        finally:
            if owned:
                client.close()

        return self._parse_response(response)

    # --- 响应解析 ---------------------------------------------------------

    def _parse_response(self, response: httpx.Response) -> LLMResponse:
        status = response.status_code

        if status in (401, 403):
            raise UpstreamAuthError(
                "AI 服务鉴权失败，密钥可能无效或已过期，已切换到本地规则模式。",
                detail=f"HTTP {status}",
            )
        if status == 429:
            raise UpstreamUnavailable(
                "AI 服务当前限流，已切换到本地规则模式完成本次分析。",
                detail="HTTP 429",
            )
        if status >= 500:
            raise UpstreamUnavailable(
                "AI 服务暂时不可用，已切换到本地规则模式完成本次分析。",
                detail=f"HTTP {status}",
            )
        if status >= 400:
            # 4xx 的响应体可能回显请求内容，一律脱敏后再记
            raise UpstreamUnavailable(
                "AI 服务拒绝了本次请求，已切换到本地规则模式完成本次分析。",
                detail=redact(f"HTTP {status}: {response.text[:200]}"),
            )

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise UpstreamResponseError(
                "AI 返回的内容无法解析，已回退到本地规则模式。",
                detail=f"{type(exc).__name__}: {response.text[:120]}",
            ) from exc

        if isinstance(body, dict) and body.get("error"):
            message = str(body["error"])[:200]
            raise UpstreamUnavailable(
                "AI 服务返回了错误，已切换到本地规则模式完成本次分析。",
                detail=redact(message),
            )

        try:
            choice = body["choices"][0]
            message = choice["message"]
            content = message.get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamResponseError(
                "AI 返回的结构不符合预期，已回退到本地规则模式。",
                detail=f"{type(exc).__name__}: {str(body)[:120]}",
            ) from exc

        finish_reason = choice.get("finish_reason")
        usage = body.get("usage") or {}
        reasoning_tokens = int(
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        )
        truncated = finish_reason == "length"

        if truncated and not content.strip():
            # 推理模型把额度吃光了。这是失败，不是「模型没话说」——
            # 当成成功返回空串会让上层以为「AI 认为没有可提取的信息」。
            raise UpstreamResponseError(
                "AI 的推理过程用尽了本次的 token 额度，没能给出结果，"
                "已回退到本地规则模式。可调大 ZHIGOU_LLM_MAX_TOKENS 后重试。",
                detail=f"finish_reason=length, reasoning_tokens={reasoning_tokens}",
            )

        if not content.strip():
            raise UpstreamResponseError(
                "AI 返回了空内容，已回退到本地规则模式。",
                detail=f"finish_reason={finish_reason}",
            )

        # 注意：reasoning_content 刻意不返回。它是模型的内部推理过程，
        # 可能是英文、可能复述提示词，对用户没有价值且有泄露提示词的风险。
        return LLMResponse(
            content=content,
            model=str(body.get("model") or self._model),
            total_tokens=int(usage.get("total_tokens") or 0),
            reasoning_tokens=reasoning_tokens,
            truncated=truncated,
        )

    # --- JSON 便捷方法 ----------------------------------------------------

    def complete_json(
        self, system: str, user: str, *, max_tokens: int | None = None
    ) -> dict:
        """调用并把返回解析成 JSON 对象。

        模型经常把 JSON 包在 ```json 代码块里，或者前后加一句话——
        这里只做**去包裹**，不做「尽力修复」。解析不出来就报错降级，
        免得把残缺的结果当成有效数据用。
        """
        response = self.complete(system, user, max_tokens=max_tokens)
        payload = extract_json_object(response.content)
        if payload is None:
            raise UpstreamResponseError(
                "AI 返回的内容不是可用的 JSON，已回退到本地规则模式。",
                detail=f"content={response.content[:160]!r}",
            )
        return payload


#: 匹配 ```json ... ``` 或 ``` ... ``` 代码块
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json_object(text: str) -> dict | None:
    """从模型输出里取出一个 JSON 对象。

    依次尝试：整段就是 JSON → 代码块里的 JSON → 第一个平衡的 `{...}`。
    三种都不成返回 None，由调用方报错降级。
    """
    candidate = text.strip()

    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    fence = _FENCE.search(candidate)
    if fence:
        try:
            parsed = json.loads(fence.group(1))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

    start = candidate.find("{")
    while start != -1:
        depth = 0
        for index in range(start, len(candidate)):
            if candidate[index] == "{":
                depth += 1
            elif candidate[index] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(candidate[start : index + 1])
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        break
        start = candidate.find("{", start + 1)

    return None


def get_service() -> AIService:
    """按当前环境变量构造一个服务实例。"""
    return AIService()


def probe() -> tuple[bool, str]:
    """做一次最小调用，确认配置可用。返回 (是否可用, 说明)。

    供设置页的「测试连接」按钮使用。失败信息已脱敏。
    """
    service = get_service()
    if not service.configured:
        return False, f"未配置 {config.LLM_API_KEY_ENV}"

    try:
        response = service.complete(
            "你是一个测试探针。", "回复两个字：可用", max_tokens=200
        )
    except Exception as exc:  # noqa: BLE001 - 探针要把任何失败都转成一句话
        from src.errors import to_user_message

        logger.warning("AI 探针失败: %s", redact(str(exc)))
        return False, to_user_message(exc)

    return True, f"{response.model} 可用（本次 {response.total_tokens} tokens）"
