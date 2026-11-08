# MCP Server：把智购参谋的工具暴露给外部 Agent

## 这是什么

`mcp_server/server.py` 用 **stdio 传输**实现 Model Context Protocol，把 Web 端与
Agent 编排共用的 6 个工具原样开放给 MCP 客户端（Claude Desktop、CodeBuddy 等）。

它只做**协议适配**：参数校验、业务规则、结果结构全部复用
`src.agent.tools.build_registry()`，没有第二份实现。工具集合变了，三端一起变。

## 6 个工具

| 名称 | 用途 |
|---|---|
| `search_products` | 按预算/品类/场景/需求筛选商品 |
| `get_product_detail` | 读取单件商品完整信息 |
| `compare_products` | 同品类横向比较 |
| `search_knowledge` | 检索选购指南与常见问题 |
| `find_similar_products` | 同品类内按规格/价格/场景算相似度（规则计算，不依赖向量库） |
| `get_user_profile` | 读取当前用户的收藏与历史偏好 |

## 安装与启动

依赖是**可选的**，不要装进 Vue 主站的 venv：

```bash
pip install -r requirements-mcp.txt
python -m mcp_server.server
```

`requirements-mcp.txt` 锁定 `mcp==1.9.4` + `pydantic==2.12.4`。版本组合是实测过的：
`mcp 1.9.4` 与 pydantic 2.14.x 会因内部 API `eval_type_backport` 被移除而
`ImportError`。许可证 MIT（wheel METADATA 核实），Requires-Python >=3.10。

## 客户端配置示例

以 Claude Desktop 的配置文件为例（`%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "zhigou": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "C:/Users/suchen/Desktop/ai shopping",
      "env": {
        "ZHIGOU_DB_PATH": "C:/Users/suchen/Desktop/ai shopping/storage/zhigou.db",
        "ZHIGOU_PRODUCTS_DB_PATH": "C:/Users/suchen/Desktop/ai shopping/storage/products.db"
      }
    }
  }
}
```

`cwd` 必须是项目根，否则 `data/products.json` 与知识语料目录找不到。

## 边界与已知限制

- **没有 HTTP 登录态**：stdio 进程里 `ToolContext.user_id` 为空，
  `get_user_profile` 会明确返回 `rejected`，不会拿全站数据冒充个人偏好。
  需要用户维度时，应在会话初始化时由客户端传入可信身份，不要由模型传 ID。
- **只读**：6 个工具都是读操作，不会写库、不会改商品或账号。
- **单进程**：与 SQLite 单实例部署的约束一致。
- **不随主站自动启动**：它是独立进程，主站 `requirements-vue.txt` 不含 MCP 依赖，
  装或不装都不影响 `http://<host>:8000`。

## 验证方式

`tools/list` 应返回 6 个工具且都带 `inputSchema`；`tools/call` 的
`find_similar_products` 应返回带 `similarity` 的列表。本项目用一段真实的
stdio JSON-RPC 会话做过端到端验证（`initialize` → `notifications/initialized`
→ `tools/list` → 两次 `tools/call`），四个响应全部返回、退出码 0。
