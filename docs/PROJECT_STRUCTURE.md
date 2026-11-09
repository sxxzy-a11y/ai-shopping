# 项目目录分类规范

> 本文说明「什么东西放哪里」。新增文件前先看这里，避免根目录继续堆积散落文件。
> 最后更新：2026-11-08（v2.13，与全库整理后的实际结构核对过）。

## 1. 顶层分类

| 目录 / 文件 | 分类 | 职责 | 是否入库 |
|---|---|---|---|
| `frontend/` | 前端应用 | Vue 3 + Vite + TS 源码、`package.json`、构建配置 | 源码入库；`node_modules/`、`dist/` 不入库 |
| `backend/` | 后端应用 | FastAPI 路由、鉴权、请求模型、业务桥接、启动入口 | 入库 |
| `src/` | 业务领域层 | 需求解析、评分、推荐、比较、报告、知识库、数据库。**不依赖任何 Web 框架** | 入库 |
| `src/ui/` + `app.py` | legacy 界面 | Streamlit 旧版入口与页面，保留可运行、可回退 | 入库 |
| `mcp_server/` | 可选协议适配 | stdio MCP Server，复用 `src.agent.tools` 的 6 个工具 | 入库 |
| `tests/` | 测试 | Python 单元 / 集成 / 契约测试 | 入库 |
| `scripts/` | 运维脚本 | 初始化、数据导入、备份恢复、评测入口 | 入库 |
| `data/` | 静态数据 | 商品种子、知识语料、评测用例与报告快照 | 入库（生成物除外） |
| `eval/` | 评测框架 | runner、场景检查、报告渲染 | 入库 |
| `frontend/src/styles/` | 前端样式 | `tokens.css`（变量）/ `base.css`（表单·骨架）/ `components.css`（组件）/ `responsive.css`（断点）/ `index.css`（入口） | 入库 |
| `docs/` | 项目文档 | 需求、架构、测试、部署说明、迁移与本文 | 入库 |
| `docs/archive/` | 历史归档 | 跨轮次检查汇总等**时间点快照**，不作为当前状态依据 | 入库，只读 |
| `openspec/` | 规格与变更 | 当前规范 + 历史变更提案/归档 | 入库 |
| `design/` | 设计资产 | UI 组件与视觉参考 | 入库 |
| `submission/` | 提交材料 | 比赛/提交用的截图、脚本、渲染产物 | 部分入库；按归档约定只读 |
| `Plan/` | 执行计划 | 大项目档的规划文档与检查点 | 入库 |
| `.ai-memory/` | 会话记忆 | 交接检查点与当日决策记录 | 开发过程文件 |
| `storage/` | 运行时数据 | SQLite 数据库、本机 API 覆盖配置 | **不入库**（含密钥） |
| `.github/` | CI 配置 | workflows、dependabot；含 Python 与 Vue 两套构建门禁 | 入库 |

## 2. 根目录文件清单

根目录散文件分两类，**不做迁移**——平台与工具链按固定路径识别，移动会失效：

```
README.md  LICENSE  CONTRIBUTING.md  SECURITY.md  CHANGELOG.md  DEPLOY.md
Dockerfile  docker-compose.yml  .dockerignore  .gitignore  .gitattributes
pyproject.toml  pytest.ini  requirements.txt  requirements-dev.txt
requirements-vue.txt  requirements-mcp.txt  .env.example
app.py
```

跨轮次的检查汇总已归档到 `docs/archive/项目全面检查报告.md`（时间点快照，不作当前状态依据）；
根目录只保留平台约定文件。
`.env` 是本机配置，**不入库**；`zhigou.log` 等调试日志已清理，不得再产生。

## 3. 依赖清单的分工（不是单一来源）

| 清单 | 用途 | 关键差异 |
|---|---|---|
| `requirements.txt` | 完整运行环境（含 legacy Streamlit） | 7 个直接依赖 |
| `requirements-dev.txt` | 开发/测试工具 | 在前者基础上加 ruff、mypy、pytest |
| `requirements-vue.txt` | **云端 Vue 单端口部署专用** | 6 个包，**不含 streamlit** |
| `requirements-mcp.txt` | 独立的可选 MCP 进程 | `mcp==1.9.4` + `pydantic==2.12.4`（实测兼容组合） |
| `frontend/package.json` + `package-lock.json` | 前端依赖 | 锁文件必须提交 |

新增 Python 依赖时同步：对应清单 → CI 矩阵 → README 版本声明 → 本文。

## 4. 忽略规则

`.gitignore` 已覆盖：`node_modules/`、`frontend/dist/`、`storage/`、`*.db`、`__pycache__/`、
`.venv/`、`.tmp/`、`.mypy_cache/`、`.ruff_cache/`、`*.bak*`、`pip-*` 临时目录等生成物。

**绝不入库**：`.env`、`storage/api_config.json`、`.streamlit/secrets.toml`（含明文密钥）。

## 5. 生成物与源码的边界

| 类型 | 例子 | 处理 |
|---|---|---|
| 源码 | `frontend/src/**`、`backend/app/**`、`src/**`、`mcp_server/**` | 提交 |
| 构建产物 | `frontend/dist/` | 忽略；部署前由 `npm run build` 生成并单独上传 |
| 运行时数据 | `storage/*.db` | 忽略；应用启动时自动初始化（`scripts/init.py` 仍可单独执行） |
| 快照/截图 | `submission/screenshots/` | 归档材料，按约定只读 |
| 临时探针 | `.tmp/`、`.mypy_cache/`、`.ruff_cache/` | 忽略，收尾时清理 |

## 6. 命名约定

- Python：模块/函数用 `snake_case`，测试文件 `test_*.py`
- Vue：`views/*View.vue`（路由页）、`components/*.vue`（可复用组件）、`api/`（请求层）、
  `stores/`（全局状态）、`composables/use*.ts`（跨页复用的状态与副作用）、`utils/`（无状态纯函数）
- 样式：`styles/` 四层（`tokens` 变量 / `base` 表单与骨架 / `components` 组件 / `responsive` 断点）
  + `index.css` 汇总。新增样式归到对应层，不新建散文件、不内联颜色
- 公共逻辑的唯一实现：`src/ui/components.py` 的 `queue_flash`/`render_flash`、
  `composables/useConfirm.ts`、`useInitialLoad.ts`、`useFavorites.ts`
- 文档：`docs/<主题>.md` 小写连字符；变更归档按 `openspec/changes/archive/<日期>-<主题>/`
- 计划：`Plan/<序号>. <中文名>_plan.md`

## 7. 双入口并存期间

`app.py`（legacy）与 `backend/run.py`（当前）都在根目录附近，不是遗漏：
前者是备份要求下保留的旧版入口，后者是当前推荐入口。两者共用 `src/`，不共用会话与数据库写入口。
决定下线旧版时，删除 `app.py` + `src/ui/` + `streamlit` 依赖，并同步更新本文件与
`docs/VUE_MIGRATION.md`。

## 8. 目录重组的边界

v2.17 已在**前端源码内部**（`styles/` 四层）与**文档层**（`docs/archive/`）完成重组；
下面这些运行时顶层目录仍不搬动：

- `backend/app/main.py` 用 `Path(__file__).resolve().parents[2] / "frontend" / "dist"` 定位静态产物；
- `src/config.py` 的 `PROJECT_ROOT` 决定 `.env`、`data/`、`storage/` 的解析基准；
- CI、Dockerfile、systemd unit、四份 requirements 与 20 余份文档都引用当前层级。

迁移会同时打断已上线服务与 1117 项测试的导入路径，收益仅是目录观感。
归档区 `openspec/changes/archive/`、`submission/` 按项目约定只读；重复文件只在
**内容哈希完全相同**时才清理，且先备份到桌面 `_zhigou_archive_backup/` 再删（可逆）。
审计中提到的 3 个截图脚本是「相似」而非「相同」，属于各自版本的提交材料，因此保留。
