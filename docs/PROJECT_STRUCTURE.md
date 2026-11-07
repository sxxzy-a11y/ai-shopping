# 项目目录分类规范

> 本文说明「什么东西放哪里」。新增文件前先看这里，避免根目录继续堆积散落文件。

## 1. 顶层分类

| 目录 / 文件 | 分类 | 职责 | 是否入库 |
|---|---|---|---|
| `frontend/` | 前端应用 | Vue 3 + Vite + TS 源码、`package.json`、构建配置 | 源码入库；`node_modules/`、`dist/` 不入库 |
| `backend/` | 后端应用 | FastAPI 路由、鉴权、请求模型、业务桥接、启动入口 | 入库 |
| `src/` | 业务领域层 | 需求解析、评分、推荐、比较、报告、知识库、数据库。**不依赖任何 Web 框架** | 入库 |
| `app.py` + `src/ui/` | legacy 界面 | Streamlit 旧版入口与页面，保留可运行、可回退 | 入库 |
| `tests/` | 测试 | Python 单元 / 集成 / 契约测试 | 入库 |
| `scripts/` | 运维脚本 | 初始化、数据导入、备份恢复、评测入口 | 入库 |
| `data/` | 静态数据 | 商品种子、知识语料、评测用例与报告快照 | 入库（生成物除外） |
| `eval/` | 评测框架 | runner、场景检查、报告渲染 | 入库 |
| `docs/` | 项目文档 | 需求、架构、测试、部署说明、迁移与本文 | 入库 |
| `openspec/` | 规格与变更 | 当前规范 + 历史变更提案/归档 | 入库 |
| `design/` | 设计资产 | UI 组件与视觉参考 | 入库 |
| `submission/` | 提交材料 | 比赛/提交用的截图、脚本、渲染产物 | 部分入库 |
| `Plan/` | 执行计划 | 大项目档的规划文档与检查点 | 入库 |
| `storage/` | 运行时数据 | SQLite 数据库、本机 API 覆盖配置 | **不入库**（含密钥） |
| `.github/` | CI 配置 | workflows、dependabot | 入库 |

## 2. 根目录为什么还留着这些文件

根目录的散文件分两类，**不做迁移**，原因写在这里以免被误当成「没整理干净」：

**平台约定文件**（GitHub / 工具链按固定路径识别，移动会失效）：

```
README.md  LICENSE  CONTRIBUTING.md  SECURITY.md  CHANGELOG.md
DEPLOY.md  Dockerfile  docker-compose.yml  .dockerignore  .gitignore
pyproject.toml  pytest.ini  requirements.txt  requirements-dev.txt
```

**当前状态总览**：`项目全面检查报告.md` 是跨轮次的检查汇总，放在根目录便于一眼找到；
细节仍以 `docs/` 下各专项文档为准。

## 3. 依赖清单的单一来源

| 生态 | 清单 | 说明 |
|---|---|---|
| Python | 根目录 `requirements.txt`（运行）、`requirements-dev.txt`（开发） | 前后端 Python 依赖统一在此，避免两份清单漂移 |
| Node | `frontend/package.json` + `frontend/package-lock.json` | 只在前端目录内，锁文件必须提交 |

新增 Python 依赖时同步 `requirements.txt` → `requirements-dev.txt` → CI 矩阵 → README 版本声明。

## 4. 忽略规则

`.gitignore` 已覆盖：`node_modules/`、`frontend/dist/`、`storage/`、`*.db`、`__pycache__/`、
`.venv/`、`.tmp/`、`pip-*` 临时目录、`submission/screenshots/smoke-*.png` 等生成物。

**绝不入库**：`.env`、`storage/api_config.json`、`.streamlit/secrets.toml`（含明文密钥）。

## 5. 生成物与源码的边界

| 类型 | 例子 | 处理 |
|---|---|---|
| 源码 | `frontend/src/**`、`backend/app/**`、`src/**` | 提交 |
| 构建产物 | `frontend/dist/` | 忽略；部署前由 `npm run build` 生成 |
| 运行时数据 | `storage/*.db` | 忽略；由 `scripts/init.py` 初始化 |
| 快照/截图 | `submission/screenshots/`、`.tmp/shots/` | `.tmp/` 忽略；提交材料里的代表性截图可入库 |
| 临时探针 | `.tmp/*.py` | 忽略，收尾时清理 |

## 6. 命名约定

- Python：模块/函数用 `snake_case`，测试文件 `test_*.py`
- Vue：`views/*View.vue`（路由页）、`components/*.vue`（可复用组件）、`api/`（请求层）、`stores/`（状态）
- 文档：`docs/<主题>.md` 小写连字符；变更归档按 `openspec/changes/archive/<日期>-<主题>/`
- 计划：`Plan/<序号>. <中文名>_plan.md`

## 7. 双入口并存期间

`app.py`（legacy）与 `backend/run.py`（当前）都在根目录附近，不是遗漏：
前者是备份要求下保留的旧版入口，后者是当前推荐入口。两者共用 `src/`，不共用会话与数据库写入口。
决定下线旧版时，删除 `app.py` + `src/ui/` + `streamlit` 依赖，并同步更新本文件与
`docs/VUE_MIGRATION.md`。
