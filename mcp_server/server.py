"""智购参谋 MCP Server（stdio 传输）。

把 `src/agent/tools.py` 的 6 个工具原样暴露给 MCP 客户端。这里只做**协议适配**：
业务规则、参数校验、结果结构全部复用既有 `ToolRegistry`，不重写第二份，
所以工具在 Web 端、Agent 编排、MCP 端的行为天然一致。

运行：

    pip install -r requirements-mcp.txt
    python -m mcp_server.server

客户端配置示例见 `docs/MCP.md`。这个依赖是**可选**的，Vue 部署用的
`requirements-vue.txt` 不含它，主站不受影响。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from mcp import types
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
except ImportError as exc:  # pragma: no cover - 缺依赖时给可执行的提示
    raise SystemExit(
        "MCP 依赖未安装。请先执行：pip install -r requirements-mcp.txt"
    ) from exc

from src.agent.registry import ToolContext  # noqa: E402 - 上面要先引导 sys.path
from src.agent.tools import build_registry  # noqa: E402
from src.data_loader import load_catalog  # noqa: E402
from src.runtime_cache import get_knowledge_index  # noqa: E402

server: Server = Server("zhigou")
registry = build_registry()


def _declarations() -> list[dict[str, Any]]:
    """把 OpenAI function 声明转成 MCP 的 `inputSchema` 形状。"""
    tools: list[dict[str, Any]] = []
    for declaration in registry.declarations():
        function = declaration["function"]
        tools.append(
            {
                "name": function["name"],
                "description": function["description"],
                "inputSchema": function["parameters"],
            }
        )
    return tools


def _context() -> ToolContext:
    return ToolContext(
        catalog=load_catalog(),
        knowledge_index=get_knowledge_index(),
        # stdio 进程没有 HTTP 登录态。画像工具会明确报告「无归属」，
        # 不拿全站数据冒充个人偏好。
        user_id=None,
    )


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [types.Tool(**item) for item in _declarations()]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None):
    result = registry.invoke(name, arguments or {}, context=_context())
    payload = {
        "ok": result.ok,
        "status": result.status,
        "summary": result.summary,
        "data": result.payload,
    }
    return [
        types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))
    ]


async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
