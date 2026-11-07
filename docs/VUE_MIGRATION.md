# Vue 化迁移说明（v2.1：能力对齐）

> 本文是**当前版本状态的单一事实源**。其它文档里出现的 Streamlit 描述，除旧版入口说明外，
> 均指 v1.x 实现；`openspec/changes/archive/` 下的 86 篇文档是历史快照，保持原样不改。
>
> **v2.1 变更**：旧版的写操作与诊断能力已全部搬到 Vue 版（API 配置、AI 连接检测、
> 商品 CRUD、品类品牌元信息、用户管理、知识库文档与索引、全站记录删除、完整问答链路、收藏）。
> 不再有「管理员页面只读 / AI 问答简化版」的限制，详见第 2、7 节。

**更新日期**：2026-11-07
**对应提交**：以 `git log -1` 为准；迁移计划见 `Plan/1. Vue前端迁移_plan.md`

---

## 1. 现在跑的是什么

```
浏览器 ──HTTP──> FastAPI（:8000）
                  ├── /api/*          JSON API
                  └── /              托管 frontend/dist（Vue SPA，hash 路由）
                          │
                          └── 调用 src/ 下的业务函数（与旧版同一批代码）
```

- **主界面**：Vue 3 + Vite + TypeScript + Vue Router + Pinia，源码在 `frontend/`
- **后端**：FastAPI + Uvicorn，源码在 `backend/`，只做鉴权、参数校验与业务桥接
- **业务逻辑**：`src/` 原封不动复用，`recommend` / `compare` / `build_report` / `database.*` 是同一批函数
- **旧版**：`app.py`（`streamlit run app.py`，8501 端口）完整保留，仍可运行，是 legacy 入口

结论一致性的实测证据：同一条需求「5000 元以内，主要写代码，需要便携，14 寸左右」，
两版都给出 **红米 REDMI Book 14 2025 / 81 分 / 3519 元**。

## 2. 页面覆盖矩阵

| 页面 | Vue 路由 | 主要数据来源 | 读 | 写 |
|---|---|---|---|---|
| 登录 | 登录页（未登录时全屏） | `POST /api/auth/login` | — | 会话 |
| 首页 | `/#/` | `GET /api/meta` | ✅ | — |
| 智能分析 | `/#/analysis` | `POST /api/analysis` | ✅ | ✅ 保存历史、收藏 |
| 商品比较 | `/#/compare` | `GET /api/products` `POST /api/compare` | ✅ | — |
| AI 问答 | `/#/qa` | `POST /api/qa`（检索 → 商品意图 → 回答策略 → 回退） | ✅ | — |
| 历史记录 | `/#/history` | `GET/DELETE /api/history` `GET /api/favorites` | ✅ | ✅ 删除 / 导出 / 取消收藏 |
| 个人设置 | `/#/settings` | `GET/PUT /api/preferences`、`/api/admin/api-config` | ✅ | ✅ 偏好、**API 配置保存/恢复**、**两个连接检测** |
| 关于 | `/#/about` | `GET /api/about` | ✅ | — |
| 商品维护 | `/#/catalog` | `/api/admin/products`、`/api/admin/catalog-meta` | ✅ | ✅ 新增 / 编辑 / 启停、品类品牌元信息 |
| 知识库管理 | `/#/knowledge-admin` | `/api/admin/knowledge/*` | ✅ | ✅ 文档增删、检索调试、重建索引 |
| 全站概览 | `/#/overview` | `/api/admin/overview`、`/api/admin/analyses` | ✅ | ✅ 删除任意用户记录 |
| 用户管理 | `/#/users` | `/api/admin/users` | ✅ | ✅ 新建 / 改角色 / 重置密码 / 启停 / 删除 |
| 效果评测 | `/#/eval` | `GET /api/eval` | ✅ 快照 | ❌ 不在线触发（旧版同样是只读快照） |

**能力对齐的实现方式**：`backend/app/admin_api.py` 把旧版写操作与诊断能力原样开放为 REST 端点，
全部调用 `src/` 里旧版同一批函数（`create_product` / `set_user_role` / `ai_service.probe` /
`knowledge_docs.create_document` 等），不重写业务规则。路由层加 `AdminUser` 依赖，
与函数内的 `require_admin` 形成三层权限校验；领域异常统一转 400 中文提示。
AI 配置里的密钥只在服务端读写，响应一律掩码。

## 3. API 一览

所有 `/api/*`（除 `health` / `login` / `register`）都要求登录；管理员端点在**后端**校验角色，
前端隐藏入口不算权限。

| 分组 | 端点 |
|---|---|
| 鉴权 | `POST /auth/login` `POST /auth/logout` `GET /auth/me` `POST /auth/register` |
| 元数据 | `GET /meta` `GET /products` `GET /about` `GET /health` |
| 业务 | `POST /analysis` `POST /compare` `POST /qa` |
| 历史 | `GET /history` `GET /history/{id}` `GET /history/{id}/export` `DELETE /history/{id}` |
| 收藏 | `GET /favorites` `POST /favorites` `DELETE /favorites/{id}` |
| 偏好 | `GET /preferences` `PUT /preferences` |
| 管理员 · 概览 | `GET /admin/overview` `GET /admin/analyses` `DELETE /admin/analyses/{id}` |
| 管理员 · API 配置 | `GET/PUT/DELETE /admin/api-config` `POST /admin/api-config/probe/llm` `POST /admin/api-config/probe/embedding` |
| 管理员 · 商品 | `GET/POST /admin/products` `PUT /admin/products/{id}` `PUT /admin/products/{id}/active` |
| 管理员 · 元信息 | `GET /admin/catalog-meta` `PUT /admin/catalog-meta/category/{key}` `PUT /admin/catalog-meta/brand/{name}` |
| 管理员 · 用户 | `GET/POST /admin/users` `PUT /admin/users/{name}/{role,password,active}` `DELETE /admin/users/{name}` |
| 管理员 · 知识库 | `GET/POST /admin/knowledge/documents` `DELETE /admin/knowledge/documents/{id}` `POST /admin/knowledge/retrieve` `POST /admin/knowledge/reindex` |
| 评测 | `GET /eval`（只读快照） |
| 文档 | `GET /api/docs`（FastAPI 自动生成的 OpenAPI 交互文档） |

**会话模型**：登录成功后服务端生成随机 token，写入 `HttpOnly` + `SameSite=Lax` Cookie
（`zg_session`），token→User 映射只存在进程内存。服务重启即全部失效，需重新登录。
不引入 JWT 依赖，不把用户信息交给前端存储。

## 4. 启动与部署

```bash
# 一次性
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

# 启动（单端口，前端已由后端托管）
python backend/run.py
# 打开 http://127.0.0.1:8000
```

开发态前端热更新（另一个终端）：

```bash
cd frontend && npm run dev     # http://127.0.0.1:5173，/api 由 Vite 代理到 8000
python backend/run.py          # http://127.0.0.1:8000
```

云端部署见 [DEPLOY.md](../DEPLOY.md)：构建 `frontend/dist` 后只需一个 Uvicorn 进程，
比旧版更容易绑定到任意域名。

旧版入口（回退用）：

```bash
streamlit run app.py           # http://127.0.0.1:8501
```

## 5. 备份与回退

| 备份物 | 位置 |
|---|---|
| Git 分支 | `backup/streamlit-v1` → `8b3ae9b` |
| Git 标签 | `v1.0.0-streamlit` → `8b3ae9b` |
| 源码快照 | `ai-shopping-streamlit-v1.0.0.zip`（仓库外，桌面） |

回退到纯 Streamlit 版：`git checkout backup/streamlit-v1`，或删除新增的 `frontend/`、`backend/`
并还原 `requirements.txt` 中两行依赖即可；`src/` 从未改动。

## 6. 验证证据（2026-11-07 实测）

| 项 | 结果 |
|---|---|
| `npm run build` | ✅ vue-tsc 零错、62 模块、13 个页面 chunk |
| `ruff check .` / `ruff format --check .` | ✅ All checks passed / 124 文件已格式化 |
| `mypy src` | ✅ 57 个源文件零错误（无回归） |
| `pytest -q --junitxml` | ✅ **tests=1114 failures=0 errors=0 skipped=0**（109.8s） |
| API 冒烟 | ✅ 20/20（含 401/400/422 拒绝两态、登出失效、管理员端点） |
| **管理员写操作冒烟** | ✅ **30/30**（在临时库实例上跑，不碰真实数据） |
| **AI 连接检测实测** | ✅ 对话：`deepseek-flash 可用，消耗 42 tokens`；向量化：`text-embedding-v4 · 1024 维` |
| 浏览器真人验证 | ✅ 15/15（登录→分析→首选方案 + 12 页面 + 375px） |
| 界面能力标记断言 | ✅ 8 个页面的旧版能力标记全部存在 |
| 界面成品化检查 | ✅ 12 页痕迹词残留 0、统一页脚覆盖 12/12 |
| 问答商品详情 | ✅ 8 项详情区块、收藏与收起交互、控制台 0 错误 |
| 控制台致命错误 | 0 |
| 前端构建产物托管 | ✅ `GET /` 返回 Vue SPA |

两个长期验收脚本已放在 `scripts/`，可随时复验（**不内置任何凭据**）：

```powershell
$env:ZHIGOU_SMOKE_PASSWORD = "管理员密码"
python scripts/api_smoke.py          # API 冒烟（只读），退出码 0 = 全通过
python scripts/vue_browser_check.py  # 浏览器全站巡检 + 能力标记断言

# 写操作冒烟：会创建/删除数据，必须指向临时库实例（脚本无默认地址，防止误伤真实库）
$env:ZHIGOU_SMOKE_BASE_URL = "http://127.0.0.1:8001"
python scripts/admin_api_smoke.py    # 30 项写操作，退出码 0 = 全通过
```

临时库实例启动方式（另开一个 shell，把数据库、配置与知识语料全部隔离到临时目录）：

```powershell
$tmp = "$env:TEMP\zg_admin_smoke"
$env:ZHIGOU_DB_PATH = "$tmp\zhigou.db"
$env:ZHIGOU_PRODUCTS_DB_PATH = "$tmp\products.db"
$env:ZHIGOU_API_CONFIG_PATH = "$tmp\api_config.json"
$env:ZHIGOU_KNOWLEDGE_DIR = "$tmp\knowledge"
$env:ZHIGOU_ADMIN_PASSWORD = "临时库密码"
$env:ZHIGOU_API_PORT = "8001"
python scripts/init.py
python backend/run.py
```

可覆盖环境变量：`ZHIGOU_BASE_URL`（默认 `http://127.0.0.1:8000`）、
`ZHIGOU_SMOKE_USER`（默认 `admin`）、`ZHIGOU_BROWSER_CHANNEL`（默认 `msedge`，设空则用自带 Chromium）。

> pytest 在本机 pytest 收尾时可能触发 IDE 的批量删除保护，截断汇总行；
> 以 `--junitxml` 的机器可读结果为准（1114 / 0 / 0）。

## 7. 已知限制（如实披露）

1. **Agent 执行轨迹未展示**：旧版分析页可展开「执行过程」，Vue 版只展示规则结果、报告与引用来源，
   未接 `src/agent/runner.run_agent` 的轨迹。Agent 属于长任务，需要独立的 Init-Step-Poll 异步端点，
   不适合塞进同步分析请求；补齐时应单独设计，并保留失败回退规则链路的既有约定。
2. **不在线触发评测**：「效果评测」页读已有快照，旧版本身也是只读，两版一致。
3. **会话在进程内存**：重启丢失、无空闲/绝对超时、不支持多副本；公网长期开放前需补 T1 账号安全
   （登录限流、会话过期、强密码）与集中式会话存储。
4. **SQLite 仍是单实例**，持久化需挂卷；见 roadmap P2。
5. **`frontend/dist` 是构建产物**，修改前端源码后需重新 `npm run build` 并重启后端，
   否则静态托管仍指向旧产物。
6. 依赖漏洞（pillow / pyarrow）与旧版相同，仍受 `streamlit` 约束，见 `SECURITY.md`。
7. `Dockerfile` / `docker-compose.yml` 仍是 legacy 版（8501），未改为 Vue 多阶段构建。

## 8. 文档一致性约定

- **当前状态文档**（README / DEPLOY / CONTRIBUTING / SECURITY / CHANGELOG / 本文件）：随实现更新
- **技术长文档**（`docs/architecture.md` 等）：顶部带「版本状态」标注，说明 UI 章节描述旧版、
  业务层章节仍适用
- **历史快照**（`openspec/changes/archive/`、`openspec/changes/*` 里的提案与设计）：保持原样，
  它们记录的是当时的事实，改动反而破坏可追溯性
