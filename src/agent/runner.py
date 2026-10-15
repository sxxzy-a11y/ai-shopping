"""编排循环：让模型自己决定调什么工具、按结果继续推进。

循环长这样：

```
用户问题 → 模型（带工具声明）
              ├─ 请求工具 → 校验 → 执行 → 把结果回灌 → 回到模型
              └─ 直接作答 → 结束
```

三个终止条件：模型给出回答 / 达到轮次上限 / 上游出错。

**执行轨迹是这里的核心产出物。** 它记录每一步真实发生过的调用——工具名、
参数、结果摘要、以及成功还是被拒。方案自己点名过一个风险：

> 「这块最容易做成看起来像 Agent、实际只是聊天的形式。」

应对就是：轨迹里只有**真的发生过的调用**，没有模型的思考文字。
被参数校验拒绝的调用同样入轨迹——那恰恰是最有说服力的展示内容，
证明校验真的在拦而不是摆设。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src import config
from src.agent.registry import ToolContext, ToolRegistry
from src.agent.tools import build_registry

if TYPE_CHECKING:
    from src.ai_service import AIService
    from src.data_loader import Catalog
    from src.knowledge.index import BM25Index

logger = logging.getLogger("zhigou.agent")

#: 编排用的系统提示。
_AGENT_SYSTEM = """你是一个消费决策助手，可以调用工具来获取真实数据。

工作方式：
1. 先判断用户的问题需不需要工具。**不需要就直接回答**，不要为了显得在工作而调工具。
2. 需要时一次可以调用一个或多个工具。拿到结果后看是否够回答，不够就继续调。
3. 最多调用 {max_rounds} 轮，之后必须给出回答。

硬性要求：
1. 商品的价格、参数、库存只能来自工具返回的数据，**绝不允许自己编**。
2. 工具返回什么就用什么。工具说没有找到，就如实告诉用户没找到，不要用常识补全。
3. 不要给出「销量第一」「口碑最好」「全网最低」这类结论——数据里没有这些依据。
4. 最终回答用中文，说明结论**依据了哪些数据**，控制在 250 字以内。
"""


@dataclass(frozen=True)
class TraceStep:
    """执行轨迹里的一步。"""

    round: int
    tool: str
    arguments: dict[str, Any]
    #: `ok` 成功 / `rejected` 参数校验被拒 / `error` 执行出错
    status: str
    summary: str

    @property
    def status_label(self) -> str:
        return {
            "ok": "成功",
            "rejected": "参数被拒",
            "error": "执行出错",
        }.get(self.status, self.status)

    @property
    def arguments_label(self) -> str:
        """参数的展示文本。空参数显示成「（无参数）」，不显示 `{}`。"""
        if not self.arguments:
            return "（无参数）"
        return json.dumps(self.arguments, ensure_ascii=False)


@dataclass(frozen=True)
class AgentRun:
    """一次编排的完整结果。"""

    answer: str = ""
    trace: tuple[TraceStep, ...] = ()
    rounds: int = 0
    #: 是否降级。为真时 `answer` 为空，调用方应改用确定性管道，
    #: 并把 `degrade_reason` 告诉用户。
    degraded: bool = False
    degrade_reason: str = ""

    @property
    def used_tools(self) -> bool:
        return bool(self.trace)


def _trim(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def _result_message(payload: dict[str, Any]) -> str:
    """把工具结果序列化成回灌给模型的消息。

    截断的是**回灌这一份**——模型不需要完整的两百行 JSON，
    轨迹里还有更严格的摘要。
    """
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > config.AGENT_TOOL_RESULT_MAX_CHARS:
        text = text[: config.AGENT_TOOL_RESULT_MAX_CHARS] + "…（已截断）"
    return text


def _assistant_message(response) -> dict[str, Any]:
    """把模型的工具调用请求还原成可回传的消息。

    协议要求：下一轮请求里必须带上这条 assistant 消息（含 `tool_calls`），
    否则后续的 `role: "tool"` 消息没有对应关系，上游会拒绝。
    """
    return {
        "role": "assistant",
        "content": response.content or "",
        "tool_calls": [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in response.tool_calls
        ],
    }


def run_agent(
    question: str,
    *,
    catalog: Catalog,
    service: AIService,
    registry: ToolRegistry | None = None,
    knowledge_index: BM25Index | None = None,
    max_rounds: int | None = None,
) -> AgentRun:
    """跑一次编排。

    Args:
        question: 用户的原始问题。
        catalog: 商品数据集。
        service: 模型服务。
        registry: 工具集，默认用标准工具集。
        knowledge_index: 知识检索索引。为 None 时 `search_knowledge` 会明确
            报告「知识库未加载」，而不是给出错误结果。
        max_rounds: 轮次上限，默认取 `config.AGENT_MAX_ROUNDS`。

    Returns:
        `AgentRun`。达到轮次上限时返回 `degraded=True` 的结果——
        那是一个**设计内的终止**，不是异常。

    Raises:
        上游异常（`UpstreamTimeout` 等）原样抛出，由调用方在边界处统一捕获并
        降级到确定性管道。这样整个项目只有一处处理上游异常的出口。
    """
    registry = registry or build_registry()
    rounds_limit = max_rounds or config.AGENT_MAX_ROUNDS
    context = ToolContext(catalog=catalog, knowledge_index=knowledge_index)

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": _AGENT_SYSTEM.format(max_rounds=rounds_limit),
        },
        {"role": "user", "content": question},
    ]
    trace: list[TraceStep] = []
    declarations = registry.declarations()

    for round_number in range(1, rounds_limit + 1):
        response = service.complete_messages(
            messages, tools=declarations, tool_choice="auto"
        )

        if not response.wants_tools:
            logger.info(
                "编排结束：%d 轮，%d 次工具调用", round_number, len(trace)
            )
            return AgentRun(
                answer=response.content.strip(),
                trace=tuple(trace),
                rounds=round_number,
            )

        messages.append(_assistant_message(response))

        for call in response.tool_calls:
            result = registry.invoke(call.name, call.arguments, context=context)
            trace.append(
                TraceStep(
                    round=round_number,
                    tool=call.name,
                    arguments=call.arguments,
                    # 状态直接取自工具结果：rejected 是「参数没按 schema 给」，
                    # error 是「工具本身出了问题」，两者在轨迹里要能分辨。
                    status=result.status,
                    summary=_trim(result.summary, config.AGENT_TRACE_SUMMARY_MAX_CHARS),
                )
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "content": _result_message(result.payload),
                }
            )

    logger.warning("编排达到轮次上限 %d，停止", rounds_limit)
    return AgentRun(
        trace=tuple(trace),
        rounds=rounds_limit,
        degraded=True,
        degrade_reason=(
            f"AI 已连续调用 {rounds_limit} 轮工具仍未得出结论，"
            f"已改为用既有规则完成本次分析。"
        ),
    )
