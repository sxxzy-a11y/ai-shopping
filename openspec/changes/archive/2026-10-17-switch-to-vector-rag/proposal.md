## Why

参考项目展示的是「Embedding 检索」形态：知识切片向量化、按语义相似度检索、管理端可见切片模型/维度/状态。本项目当前是关键词检索（bigram + BM25），两条全局约束（零依赖、离线必可演示）把向量化挡在门外。

用户明确要求采用向量检索，并同意**解除这两条约束**（AI 增强本来就依赖网络）。因此本变更把知识库升级为语义检索，并补上管理端页面。

## What Changes

- **约束修订**（`openspec/project.md`）：
  - 移除「零新增依赖」的绝对限制，允许为向量检索引入依赖/接口
  - 移除「离线可用是硬约束」，改为「联网功能必须可降级」：核心决策链路仍离线可用，AI 与向量检索失败时回退
- **Embedding 接入**：
  - OpenAI 兼容的 `/embeddings` 客户端（httpx 直连，与现有 AI 通道同一风格）
  - 可配服务商（示例默认阿里云百炼 `text-embedding-v4` / 1024 维；也兼容 SiliconFlow、OpenAI）
  - 批量向量化、超时、错误翻译与密钥脱敏
- **知识切片与向量库**：
  - 文档按标题/段落切成切片（≤500 字/片），切片带稳定 ID、来源、类型、更新时间
  - **向量存 SQLite**（`knowledge_vectors` 表）+ numpy 余弦相似度（pandas 已带 numpy）；
    不引入 Chroma 等外部服务——接口按可替换设计，需要时可换
  - 切片状态：未向量化 / 可用 / 过期（内容、模型或维度变化即过期）
  - 支持「生成全部向量」：增量执行，未变化切片跳过；删除已不存在的切片
- **检索升级**：
  - 向量优先：配置了 Embedding 服务且索引可用时，按余弦相似度检索（阈值 + 相对截断 + 条数上限）
  - **回退**：未配置或调用失败时回退到现有 BM25 检索，并告知用户当前检索方式
- **管理端页面「知识库管理」**（仅管理员）：
  - 概览：文档数 / 切片数 / 已向量化切片数 / 模型 / 维度
  - 一键生成全部向量（带进度与失败提示）
  - 切片列表：标题、来源、状态、维度、更新时间
  - **检索调试台**：输入问题 → 展示命中的切片、相似度分数与来源
- **AI 问答与 Agent 的 `search_knowledge` 工具共用同一检索入口**，自动享受向量检索

## Capabilities

### New Capabilities

无（并入 `knowledge-base` 与 `web-ui`）。

### Modified Capabilities

- `knowledge-base`：
  - 「中文检索能力」→「检索能力（语义优先、关键词回退）」
  - 新增「知识切片与向量索引」要求（切片规则、状态、增量生成）
  - 新增「向量服务不可用时的回退」要求
- `web-ui`：「页面构成」新增管理员专属「知识库管理」页；新增该页的行为场景

## Impact

**代码**

| 文件 | 改动 |
|---|---|
| `src/knowledge/embeddings.py` | 新增：OpenAI 兼容 `/embeddings` 客户端（批量、超时、错误翻译） |
| `src/knowledge/chunking.py` | 新增：文档切片 |
| `src/knowledge/vector_store.py` | 新增：SQLite 向量表、增量索引、余弦检索 |
| `src/knowledge/retrieval.py` | 新增：检索调度（向量优先 / BM25 回退） |
| `src/ui/pages/knowledge_admin.py` | 新增：知识库管理页 |
| `src/ui/pages/knowledge.py` | 改用统一检索入口，界面标注当前检索方式 |
| `app.py` | 导航新增管理员页 |
| `src/config.py` | Embedding 环境变量、默认端点/模型/维度、相似度阈值 |
| `.env.example` | 新增 Embedding 配置样例 |
| `src/agent/tools.py` | `search_knowledge` 工具改走统一入口（若接口签名受影响） |

**依赖**

- 新增 `numpy`（当前已随 pandas 安装，无需额外安装；显式登记到 requirements 以便声明）
- 不新增 Chroma / LangChain

**测试**

- `tests/test_embeddings.py`：打桩传输、批量、超时、未配置、密钥脱敏
- `tests/test_chunking.py`：按标题/段落切片、长度上限、稳定切片 ID
- `tests/test_vector_store.py`：增量索引、过期判定、余弦排序、阈值、删除陈旧切片
- `tests/test_retrieval.py`：向量优先、回退 BM25、失败降级
- `tests/test_app.py`：管理页渲染（管理员可见 / 普通用户不可见）、检索调试

**文档**

- `README.md`：知识库章节、设置项、环境变量、已知限制（离线策略变化）
- `docs/architecture.md`、`docs/requirements.md`、`docs/testing.md`
- `openspec/project.md`（本变更内已改）

**风险**

- **向量化依赖外部服务与费用**：批量生成一次约 N 个切片 × 文本长度；界面必须显示数量与失败原因。
- **维度/模型不一致导致检索无结果**：状态与检索都按当前模型+维度过滤，切换模型后提示重新生成。
- **Embedding 服务不可用**：一律回退 BM25，不阻断问答。
- **依赖 Numpy 的版本兼容**：显式登记并锁定下限（pandas 已依赖，实际风险低）。
