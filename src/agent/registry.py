"""工具的注册、声明与调用分发。

这个模块是**模型与业务代码之间唯一的通道**。模型只能碰到注册表里的东西，
而且每次调用都要先过参数校验——模型给的参数一律当**不可信输入**处理，
这与 `ai_enhance` 对模型输出的立场一致。

两条硬边界：

1. **工具集只读。** 这里不存在修改商品数据、写数据库或对外发起请求的工具。
   「禁止执行模型生成的任意 SQL」在本项目里的答案比「禁止」更彻底——
   **根本没有能执行 SQL 的工具**。
2. **未注册的名字一律拒绝。** 模型完全可能编一个工具名，拒绝时要告诉它
   有哪些可用的，让它下一轮能改对。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from src.data_loader import Catalog
    from src.knowledge.index import BM25Index

logger = logging.getLogger("zhigou.agent")


@dataclass(frozen=True)
class ToolContext:
    """工具执行需要的外部依赖。

    工具本身是纯函数式的——数据从上下文里取，不自己读文件、不自己建索引。
    这样它们可以脱离界面和缓存单独测试。
    """

    catalog: Catalog
    knowledge_index: BM25Index | None = None


@dataclass(frozen=True)
class ToolResult:
    """一次工具调用的结果。

    界面看 `ok` 与 `summary`，模型看 `payload`。两者分开是因为**界面要简洁、
    模型要细节**——把完整返回铺进界面会把它淹掉，把摘要喂给模型则信息不足。

    `status` 把「参数被拒」与「执行出错」分开，因为它们在轨迹里是**不同的信号**：
    前者说明校验在拦（模型没按 schema 给值），后者说明工具本身有问题。
    混成一个颜色展示，看轨迹的人就分不清该改提示词还是改代码。
    """

    ok: bool
    #: 给模型看的结果。校验失败时带 `error` 说明，让它下一轮能改对。
    payload: dict[str, Any]
    #: 给界面看的摘要，进执行轨迹。
    summary: str
    #: 校验失败或执行出错时的中文原因。成功时为空。
    error: str = ""
    #: `ok` / `rejected`（参数不合法）/ `error`（执行出错）。
    status: str = "ok"

    @classmethod
    def rejected(cls, message: str) -> "ToolResult":
        """参数没通过校验。**不是程序缺陷**——模型该按 schema 给值。"""
        return cls(
            ok=False,
            payload={"error": message},
            summary=message,
            error=message,
            status="rejected",
        )

    @classmethod
    def failed(cls, message: str) -> "ToolResult":
        """工具执行本身出了问题。"""
        return cls(
            ok=False,
            payload={"error": message},
            summary=message,
            error=message,
            status="error",
        )


@dataclass(frozen=True)
class Tool:
    """一个可被模型调用的工具。

    Attributes:
        name: 模型用的调用名。
        description: 给模型看的用途说明——**写得含糊模型就会乱调**。
        params_model: 参数校验模型。声明用的 JSON Schema 由它派生，
            两者同源，不会出现「声明说可选、校验说必填」的漂移。
        run: 执行函数，只接受**校验后的参数**与上下文。
    """

    name: str
    description: str
    params_model: type[BaseModel]
    run: Callable[[BaseModel, ToolContext], ToolResult]

    def declaration(self) -> dict[str, Any]:
        """OpenAI 兼容的工具声明。"""
        schema = self.params_model.model_json_schema()
        # pydantic 会带出 title 之类的展示字段，对模型没用，删掉减小体积
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }


class ToolRegistry:
    """工具注册表。"""

    def __init__(self, tools: Sequence[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"工具名重复：{tool.name}")
            self._tools[tool.name] = tool

    @property
    def names(self) -> list[str]:
        """已注册的工具名，按注册顺序。"""
        return list(self._tools)

    def declarations(self) -> list[dict[str, Any]]:
        """全部工具的声明，用于请求体里的 `tools` 字段。"""
        return [tool.declaration() for tool in self._tools.values()]

    def has(self, name: str) -> bool:
        return name in self._tools

    def invoke(
        self, name: str, arguments: dict[str, Any], *, context: ToolContext
    ) -> ToolResult:
        """按名调用工具。

        **任何失败都返回失败的 `ToolResult` 而不是抛异常**——编排循环要
        把失败原因回灌给模型让它重试，抛异常会直接中断整轮编排。唯一的例外
        是工具内部出现未预期错误：那属于程序缺陷，记日志后同样转成失败结果，
        不让它顺着界面炸开。
        """
        tool = self._tools.get(name)
        if tool is None:
            available = "、".join(self.names)
            return ToolResult.rejected(
                f"没有名为「{name}」的工具。可用的工具：{available}。"
            )

        try:
            params = tool.params_model(**arguments)
        except ValidationError as exc:
            return ToolResult.rejected(f"参数不合法：{_describe(exc)}")

        try:
            return tool.run(params, context)
        except Exception as exc:  # noqa: BLE001 —— 工具出错不该中断编排
            logger.warning(
                "工具 %s 执行失败（参数 %s）", name, arguments, exc_info=True
            )
            return ToolResult.failed(f"工具执行失败：{type(exc).__name__}")


def _describe(exc: ValidationError) -> str:
    """把 pydantic 的校验错误压成一句中文说明。

    **保留字段名与原因，去掉 pydantic 的英文前缀**——这段文字要回灌给模型，
    字段名是它改对参数的唯一线索。
    """
    parts: list[str] = []
    for error in exc.errors()[:4]:
        location = ".".join(str(item) for item in error.get("loc", ()))
        message = str(error.get("msg") or "不合法")
        parts.append(f"{location} {message}" if location else message)
    return "；".join(parts)
