# 变更记录

格式参考 Keep a Changelog。项目目前没有发布版本号，以日期 + commit 标记。
基线：`97e95db`（比赛提交快照）。

---

## [未发布] — 2026-11-08（v2.9：O1 轨迹落库 / O4 工具扩展 / O3 账号安全 / O7 MCP）

按用户指定顺序，四项均以「改动量小 + 复用现有代码 + 直接补缺口」为原则。

### O1 Agent 轨迹落库（过程可解释）

- 历史库新增 `agent_run` / `agent_step` 两张幂等表；`database.py` 新增
  `save_agent_run()` / `list_agent_runs()` / `get_agent_run()`。
- `runner.run_agent()` 的两个返回分支（正常结束、轮次上限降级）都落库，
  降级轨迹里被拒/出错的调用同样保留；落库失败只记 warning，不阻断编排。
- **补上 Vue 版根本不跑 Agent 的缺口**：`run_analysis()` 成功后用后台线程
  异步跑一次编排并落库，主链路延迟不变；管理端新增
  `GET /api/admin/agent/runs` 与 `GET /api/admin/agent/runs/{id}`，
  「全站概览」页新增回放卡片（列表 + 逐步展开）。

### O4 工具扩到 6 个

- `ToolContext` 增 `user_id`（默认 None，向后兼容）。
- 新增 `find_similar_products`：同品类内用 `scoring.spec_bounds` 的维度边界
  归一算规格距离，叠加价格接近度与场景重叠，**不依赖向量库**。
- 新增 `get_user_profile`：读本人 `favorites` + `analysis_history` 提炼品牌/品类/历史首选。
  参数模型刻意不收 `user_id`，身份只从上下文取，防止模型传别人 ID 越权读取。
- `TOOLS` 注册 6 个；`tests/test_agent_tools.py` 的注册断言同步到 6 个。

### O3 账号安全（roadmap T1 P0）

- 新增 `login_failures` 表（按用户名维度，时间戳存 Unix 秒）。
  `record_login_failure()` 用单事务 UPSERT 计数，连续 5 次失败锁定 15 分钟，
  登录成功 `clear_login_failures()`；组件读失败一律「放行 + 记日志」，不误伤登录。
- 会话在 12 小时绝对过期之外增加 **30 分钟空闲超时**；
  `_sessions` 从 2-tuple 改 3-tuple，滑动只更新「最近活动」，不延长绝对过期。
- `SECURITY.md` / `README.md` / `docs/roadmap.md` 的「无会话过期、无限流」表述同步。

### O7 MCP 化（可选能力，不进主站 venv）

- 新增 `mcp_server/server.py`：stdio 传输，用低层 `Server` 的
  `list_tools` / `call_tool` 把 `ToolRegistry.declarations()` 转成 MCP `inputSchema`，
  工具调用直接复用 `registry.invoke()`——协议适配层，无第二份业务规则。
- 新增 `requirements-mcp.txt`（`mcp==1.9.4` + `pydantic==2.12.4`，实测兼容；
  MIT 许可）与 `docs/MCP.md`（安装、客户端配置、边界）。
- 依赖实测记录：`mcp 1.9.4` + pydantic 2.14.x 会因内部 API
  `eval_type_backport` 移除而 ImportError，因此锁定 2.12.4。

### 验证

- `ruff check .` / `ruff format --check .`（127 文件）/ `mypy src` 全绿；
- `pytest -q`：**1114 / 0 failures / 0 errors**；`npm run build` 通过；
- Wave 1 隔离库：`run_id=1`、列表 1 条、详情 2 步（`ok` + `rejected`）、接口 200/200/400；
- Wave 2 隔离库：6 个工具注册、`find_similar_products` 返回 3 件、
  非法 ID 与无用户画像都正确 `rejected`；
- Wave 3 隔离库：5 次失败 `[401,401,401,401,429]`、锁定期正确密码 429、
  解锁后 200、空闲超时后 `me` 401；`_sessions` 解包点 grep 全量核对；
- Wave 4 真实 stdio JSON-RPC 会话：`initialize` / `tools/list`（6 个）/
  两次 `tools/call`，4 个响应齐全、退出码 0。

---

## [未发布] — 2026-11-08（v2.8：Vue 版向量索引构建）

Vue 版管理页此前只有「刷新检索索引」（清缓存），没有生成向量的入口；
legacy 的 `src/ui/pages/knowledge_admin.py` 有，一直没搬过来。结果是配了
Embedding 密钥也永远走不了语义检索。

### 新增

- **后端**（`backend/app/admin_api.py`）：
  - `GET /api/admin/knowledge/vector`：返回配置状态、模型/维度、切片总数、
    已就绪数、待生成数、最近构建时间；未配置密钥时如实说明「当前使用关键词检索」。
  - `POST /api/admin/knowledge/vector/build`：调用 `VectorStore.build_index`
    增量构建。切片来自 `runtime_cache.get_knowledge_index().documents`（含商品级
    合成文档，不能只读 Markdown 目录）；上游鉴权/超时/维度不符统一转中文 503。
  - 辅助函数 `_knowledge_slices()` 与 legacy 的 `_slices()` 同源。
- **前端**（`KnowledgeAdminView.vue`）：新增「语义检索索引」卡片，展示三个统计位、
  模型/维度/最近构建时间、待生成数量；按钮在构建中禁用并显示耗时提示，
  全部就绪后变为「索引已是最新」。状态读取单独兜错，不会拖垮整页。

### 为什么用同步接口

`build_index` 按内容哈希增量生成，`EmbeddingService` 按 10 条一批请求。
线上实测 **38 个切片约 2 秒完成**，同步请求完全够用，不需要引入后台任务 +
进度轮询的复杂度。重复点击也不会重复消耗额度（见下方验证）。

### 验证（线上真实调用）

| 步骤 | 结果 |
|---|---|
| 构建前状态 | `total_slices=38, ready=0, generation_needed=38` |
| 首次构建 | `200`，`embedded=38, skipped=0, removed=0` |
| 构建后状态 | `ready=38, generation_needed=0` |
| 检索调试 | `mode=vector, count=3`（此前 `keyword`） |
| AI 问答 | `source=knowledge+products, retrieval_mode=vector` |
| 再次构建 | `embedded=0, skipped=38`，耗时 **0.01s**，未调用向量服务 |

`ruff` / `mypy` / `pytest`（1114）/ `npm run build` 全部通过。

---

## [未发布] — 2026-11-08（v2.7：解除 Streamlit 耦合 + 检索回退修复）

### 解除 Streamlit 耦合

- **后端不再依赖 Streamlit**：`backend/app/services.py` 与 `admin_api.py` 原先
  `from src.ui.state import get_knowledge_index, get_vector_store`，而 `src/ui/state.py`
  第一行就是 `import streamlit` —— 一个不跑 Streamlit 的服务端进程被迫拖进整个框架
  （site-packages 里 streamlit 占 28MB，连同 pyarrow / altair 等传递依赖更多）。
  新增 `src/runtime_cache.py`，用 `functools.lru_cache` 实现同一套缓存语义
  （键含文件 mtime，改库/改语料自动重建），两处改为从它导入。
- `src/ui/state.py` 改为从 `src.runtime_cache` **显式重导出**（`as` 写法），
  界面层 `state.get_catalog()` / `state.get_vector_store()` 调用方式不变，
  既有 Streamlit 测试无需改动。
- `knowledge_reindex` 改用 `runtime_cache.clear_caches()`：原先靠
  `getattr(state, name)` 猜私有函数名，缓存实现一改名就静默清不掉。
- 新增 `requirements-vue.txt`（与 `requirements.txt` 版本一致，只少 streamlit），
  `DEPLOY.md` 的 Vue 部署段落据此更新。

**验证**：`import backend.app.main` 后 `streamlit` 与 `src.ui` 均不在 `sys.modules`；
服务器上 `uv pip uninstall streamlit` 后服务正常启动，首页与 `/api/health` 均 200。

### 检索回退修复

- **配了 Embedding 密钥反而查不到资料**：配置密钥后走语义检索，但向量索引从未构建，
  `VectorStore.search` 返回空。原设计「语义检索没命中就视为没有资料、不回退」混淆了
  两种情形——**库为空是能力缺失**，不是「语义上不相关」。结果问答永远回落
  `general-knowledge`，比不配密钥还差。
  现在区分：库为空 → 回退关键词并说明「向量索引尚未构建」；库里有向量但低于阈值 →
  维持原有不回退策略。

**验证**：修复前 `mode=vector count=0`、问答 `source=general-knowledge`；
修复后 `mode=keyword count=1`、`source=knowledge+products`。

---

## [未发布] — 2026-11-08（v2.6：补齐全量覆盖审查）

第一轮审查聚焦 Vue 主链路，本轮补齐 `src/` 核心模块、`scripts/`、构建与 CI 配置。

### 缺陷修复

- **商品数据可能写进历史库**（`scripts/fetch_products.py`）：`DEFAULT_DB_PATH` 硬编码
  `storage/zhigou.db`（历史库），而商品库是 `products.db`。缺省 `--out` 时会把商品写进
  历史库、真实商品库保持旧数据，脚本还打印「已写入」。改为 `config.products_db_path()`。
- **覆盖写入可能留下空商品表**（`src/product_store.py`）：`replace_all` 先在一条连接里
  `DELETE` 并提交，再调 `save_products` 另开连接写入；写入失败即空表。改为单事务，
  并把「构造待写行」提到删除之前，空记录时直接中止。
- **`--mode replace` 无确认**（`scripts/fetch_products.py`）：一条命令可清空演示库商品，
  新增 `--yes` 确认开关。
- **保存分析会往历史库建商品表**（`src/database.py`）：`save_analysis` 用了 `init_db`，
  而该函数自己的文档写着「应用读写的入口别用这个」。改为 `init_history_db`。
- **预算下限被静默丢弃**（`src/agent/tools.py`）：`budget_min` 过了参数校验却从未参与筛选，
  模型传「3000–5000」会返回 2000 元的商品并回报成功。改为在工具层按 price 过滤。
- **读路径上反复写库**（`src/catalog_meta.py`）：`brand_entries()` 每次调用都 `sync_brands`，
  而它处在分析渲染路径上，每次分析都开写事务，多线程下易撞 `SQLITE_BUSY`。
  改为先比对已有品牌，无新增则零写入。
- **`restore_db.py --verify/--restore` 必然失败**：`--db` 默认 `all`，却拿同一个备份文件
  去校验两套表。改为要求显式指定 `--db`，并提示一个备份只含一个库。
- **配置加载失败后永久转圈**（`SettingsView.vue`）：`cfg` 为 null 时模板命中
  「正在读取设置…」，失败也一直转。补 `cfgLoading` 与失败态 + 重试按钮。
- **账号页破坏性操作可重复提交**（`UsersView.vue`）：删除与改密码没有在途守卫，双击会发两次
  DELETE；重置密码也不做 8 位校验，只能拿到服务端泛化 400。均补上。
- **知识库操作无守卫与表单残留**（`KnowledgeAdminView.vue`）：`reindex` 不受 `busy` 保护；
  新建成功后只清标题与正文，`doc_type`/`category`/`source` 残留，连点易造出错配资料。
- **前端无全局错误出口**（`main.ts`）：渲染期异常与未捕获 Promise 拒绝在控制台之外无痕。

### 配置与文档一致性

- `scripts/init.py`：`MIN_PYTHON` 由 `(3, 11)` 改为 `(3, 12)`（与 README、
  `requirements.txt` 的声明对齐）；末行提示由 `streamlit run app.py` 改为 `python backend/run.py`。
- `.github/workflows/ci.yml`：注释里过时的 `python_version = "3.11"` 改为 3.12，
  并注明以 `pyproject.toml` 为唯一来源。
- 页脚版本号 `2.5` → `2.6`。

### 验证

- `ruff check` / `ruff format --check` / `mypy src` 全绿；
- `pytest -q`：**1114 通过 / 0 失败**；
- `npm run build`（含 `vue-tsc --noEmit`）通过；
- 仓储层单独验证：`replace_all` 正常替换、空记录被拒且原数据保留、
  `sync_brands` 第二次返回 0（读路径不再写库）。

---

## [未发布] — 2026-11-08（v2.5：代码审查与部署加固）

### 缺陷修复

- **请求头被覆盖**：`api/client.ts` 里 `...init` 写在 `headers` 之后，任何传入 headers 的
  调用都会把默认 `Content-Type` 整块覆盖；改用 `Headers` 合并后传入。
- **新机器首次启动无法登录**：Vue 版入口缺少旧版的 `_bootstrap_once`，商品种子与初始管理员
  从不创建。`backend/app/main.py` 增加 `lifespan` 启动初始化（幂等、失败只记日志），
  并把 `ZHIGOU_RESET_ADMIN_PASSWORD` 恢复通道一并接入。
- **评测快照读不到**：`eval_summary` 用相对路径 `Path("data/evaluation")`，依赖进程 cwd，
  systemd 启动时会静默失败；改用 `config.PROJECT_ROOT`，多份快照按 mtime 取最新。
- **全站记录数虚报**：`/api/admin/analyses` 硬截 100 条却被界面当作全站总数；
  接口补返回 `total` 与 `limit`，界面区分「显示最近 N 条」与「共 N 条」。
- **登录/登出两处缺陷**：`logout()` 在 `finally` 清状态但仍把异常抛给调用方，导致
  `router.replace('/')` 不执行；`restore()` 只处理 401，错误状态从不重置。
- **评测页失败后无限转圈**：补 `loading` 状态，失败即停止 spinner。
- **历史详情竞态**：快速切换记录时慢的旧响应会覆盖新选中项，加请求序号校验。
- **收藏误报为空**：加载失败被静默当成「没有收藏」，改为提示错误。
- **收藏重复提交**：分析页与问答页各写一份收藏逻辑且都无在途保护，抽成
  `composables/useFavorites.ts`，补齐空值与重入守卫。
- **下架商品可加入比较**：`CompareView` 未过滤 `is_active`，改为按 `is_active !== false` 过滤。
- **`/api/meta` 用户字段缺 `role_label`**：与前端 `SessionUser` 类型不符；抽出
  `_session_payload()` 供登录、`/auth/me`、`/meta` 共用。
- **登出硬编码 Cookie 名**：改用 `core.COOKIE_NAME`，避免改名时漏改。
- **检索调试接口无兜底**：`/api/admin/knowledge/retrieve` 故障直接 500，改为降级返回。
- **非法数字静默提交**：`Number('abc')` 得到 `NaN`，序列化成 `null` 提交；新增
  `toNumberOrUndefined()`。
- **管理页无路由守卫**：`meta.admin` 是死配置，手动改 hash 可进入；补 `beforeEach`。

### 可维护性

- 新增 `utils/format.ts`：统一时间格式化（原先 4 处实现、2 种口径）与价格口径
  （原先前端 `¥2999` 与后端 `2999 元` 两套）。
- `CatalogView` 删除与 `Product` 重复的 `ProductRow` 声明，改用公共类型；
  去掉一次「只为取品类而拉全量商品」的多余请求。
- 配置保存、品类/品牌保存、上下架操作补在途守卫，避免连点重复提交与重复全量刷新。
- 导航高亮改用 `exact-active-class`，不再依赖 `route.path === item.to`。
- 三处静默 `except Exception: pass` 补日志（知识检索回退、模型初始化失败、模型回答失败）。
- 会话增加 12 小时绝对过期与惰性清理，避免 token 只增不减。

### 文档同步

- `SECURITY.md` / `README.md` / `DEPLOY.md` / `docs/auth-boundary.md` / `docs/architecture.md` /
  `docs/requirements.md` / `docs/technical-introduction.md` / `docs/VUE_MIGRATION.md` /
  `openspec/specs/web-ui/spec.md`：把「无会话过期」更正为「有 12 小时绝对过期、无空闲超时」；
  规范中沿用 legacy 的「刷新页面需重新登录」改为 Vue 版实际行为。
- `DEPLOY.md` 补充部署必需但原先缺失的步骤：启动自动初始化、必须显式配置管理员密码、
  安全组放行端口、systemd 守护、2G 内存机器在本地构建。
- 登录页「长时间未操作后需要重新登录」与实现不符，改为「登录满 12 小时后」；
  登录页与关于页补演示级鉴权边界披露。
- 页脚版本号由 `2.2` 对齐到本轮的 `2.5`。

### 验证

- `ruff check` / `ruff format --check` / `mypy src` 全绿；
- `pytest -q` 全量通过；
- `npm run build`（含 `vue-tsc --noEmit`）通过；
- 临时库接口实测：登录、`/auth/me`、`/meta`、`/admin/overview`、`/admin/analyses`（含 total）、
  `/eval`、会话过期与清理均符合预期。

---

## [未发布] — 2026-11-07（v2.4：问答结果可展开）

### 改动

- 去掉 AI 问答页「引用的资料」区块（后端仍保留 `citations` 字段，界面不再展示）
- 「相关商品」改成可展开卡片，点开后展示：评分构成（维度 / 得分 / 权重 / 理由）、
  核心参数（中文标签）、亮点与需要留意、适用场景、资料来源与核验状态、
  原始资料外链、收藏；支持展开与收起
- 后端 `/api/qa` 的 `products` 从原始 dataclass 序列化改为结构化中文详情：
  标签取 `config.SPEC_LABELS` / `DIMENSION_LABELS`，参数值走
  `comparison.format_param`，与商品比较页同一套口径；顺带修正
  `"False"` 字符串被当成真值而显示成「有独显」的问题
- 问答页检索方式改为中文标签

### 验证

浏览器目检：引用资料区块已移除、5 件相关商品、8 项详情区块齐全、
收藏与收起交互正常、控制台 0 错误。

---

## [未发布] — 2026-11-07（v2.3：界面成品化）

### 去掉工作痕迹

- 顶栏移除「Vue 版 · FastAPI」技术栈徽章，改为「参考价数据 · 购买前请核实」
- 全站清理「与旧版同能力 / 同链路」「内部键 / 内部名称」「快照文件路径」
  「运行 python 命令」「查看原始数据（JSON）」「后端未返回数据 / 尚未初始化 / 语料目录为空」
  等开发态与迁移态文案；源码注释同步清理
- 12 个页面 eyebrow 统一为中文小标签，去掉「· 管理员」内部视角
- 管理员页的英文枚举（资料类型、检索方式）改中文；效果评测不再暴露原始 JSON
- 关于页去掉技术栈行；登录页、设置页与空状态文案改为用户语言

### 补齐成品要素

- 全站统一页脚：版权、数据声明、关于入口、版本号，含移动端适配
- 首页新增「最近分析」（真实历史 3 条，带空状态引导）
- 关于页新增「怎么用」三步流程与 5 条常见问题
- 统一空状态与错误提示；`Plan/`、`.ai-memory/` 等过程记录不再随成品入库

### 验证

12 页痕迹词扫描残留 **0**、统一页脚覆盖 **12/12**、控制台致命错误 **0**；
`npm run build`、全站浏览器巡检 15/15 通过。

---

## [未发布] — 2026-11-07（v2.2：品类与评测界面可读性）

### 问题与修复

- **品类与品牌页**：原来把英文 `key`（`laptop` / `phone`）当展示名，且前端绑了不存在的
  `display_label` 字段导致输入框空白；品牌用 13 行表格铺满屏。
  - 后端 `GET /api/admin/catalog-meta` 改为返回 `CategoryEntry.label`（中文）、
    `display_label`（可编辑值）、品类商品数与该品类下的品牌列表；
  - 前端改为**按中文大类分组**的卡片（笔记本电脑 / 手机），品牌用 chip 展示，
    编辑表单按需展开，并补「其他品牌（无在售商品）」区块。
- **商品清单**同样按中文大类分组：每个品类一张可折叠卡片（含商品数 / 在售数），
  支持「全部展开 / 全部收起」；分组后去掉表格里冗余的「品类」列，
  未归到已知品类的商品进「其他」组。编辑、启停功能不变。
- **效果评测页**：原来直接 `JSON.stringify` 输出整份报告，用户看到「全是代码」。
  - 改为概览统计卡、报告概况表、5 项自动指标（带进度条与口径说明）、
    13 类分类通过情况、需人工复核的指标；
  - 原始 JSON 收进默认折叠的「查看原始数据」，页面可见文本从约 24000 字符降到约 1150。

### 验证

浏览器目检：中文品类、无裸露英文键、展示名不再空白、点品牌可编辑；
评测页所有可读标签存在、默认不显示 JSON 键；
商品清单 2 个中文大类卡片、折叠 / 全部收起 / 全部展开交互正常；控制台 0 错误。

---

## [未发布] — 2026-11-07（v2.1：旧版能力对齐）

### 改动

- 新增 `backend/app/admin_api.py`（25 个路由）：把旧版写操作与诊断能力原样开放，
  全部复用 `src/` 同一批函数，路由层加 `AdminUser` 依赖形成三层权限校验
- **AI 连接检测**：`POST /api/admin/api-config/probe/llm`（`ai_service.probe`）与
  `/probe/embedding`（维度/模型判据），连同 API 配置的读取、保存（空密钥不覆盖）、恢复默认
- 商品 CRUD + 启停、品类/品牌元信息、用户新建/改角色/重置密码/启停/删除、
  知识文档增删 + 检索调试 + 索引重建、全站分析记录删除
- AI 问答升级为旧版同构链路：知识检索 → 商品意图 → 三种回答策略 → 失败回退规则，
  响应带 `source` / `citations` / `retrieval_mode`；分析页与历史页补收藏
- 8 个 Vue 页面接入上述能力；`frontend/public/favicon.svg` 消除 404
- 新增 `scripts/admin_api_smoke.py`（**只在临时库实例运行**，无默认地址防误伤）；
  `scripts/vue_browser_check.py` 加 8 个界面能力标记断言

### 验证

- 管理员写操作冒烟 **30/30**（临时库实例，含两个连接检测、商品/用户/知识库 CRUD、检索、收藏）
- AI 连接检测真人点击验证：对话 `deepseek-flash 可用，消耗 42 tokens`；
  向量化 `text-embedding-v4 · 1024 维`
- 浏览器全站巡检 15/15 + 8 个能力标记全部存在、控制台致命错误 0
- `npm run build` ✅ / `ruff check .` ✅ / `ruff format --check .` ✅ 124 文件

### 剩余差异（已披露）

Vue 版未展示 Agent 执行轨迹（需独立异步端点）、不在线触发评测（旧版同样只读快照）。

---

## [未发布] — 2026-11-07（v2.0：Vue 前端 + FastAPI 后端）

### 改动

- 新增 `frontend/`：Vue 3 + Vite + TS，12 个路由页面 + 登录页，hash 路由，自写设计系统 CSS
- 新增 `backend/`：FastAPI 26 个路由，复用 `src/` 全部业务函数；`HttpOnly` Cookie 内存会话；
  后端入口做权限兜底；`frontend/dist` 存在时单端口托管 SPA
- `requirements.txt` 增加 `fastapi==0.162.0` / `uvicorn==0.54.0`
- 旧版完整备份：分支 `backup/streamlit-v1`、标签 `v1.0.0-streamlit`、仓库外源码快照 zip
- 新增 `docs/VUE_MIGRATION.md`（迁移状态/页面覆盖矩阵/API/回退）与
  `docs/PROJECT_STRUCTURE.md`（目录分类规范）；README / DEPLOY / CONTRIBUTING / SECURITY 同步现状
- 清理根目录 6 个 pip 临时目录；`.gitignore` 补 `frontend/dist/`
- 修正 `CONTRIBUTING.md` 里过时的 Python 3.11 声明

### 验证

- `npm run build` ✅ vue-tsc 零错 / 62 模块 / 13 页面 chunk；`ruff check backend` ✅；`mypy src` ✅ 无回归
- API 冒烟 20/20（含 401/400/422、登出失效、管理员端点）
- 浏览器真人验证 15/15（登录→分析→首选方案 + 12 页面 + 375px），控制台零错误
- 结论一致性：同一需求两版均为「红米 Book 14 2025 / 81 分 / 3519 元」

### 已知限制

Vue 版管理员页面只读（写操作在 legacy 版）；AI 问答为简化链路；会话存内存、无过期；
SQLite 仍单实例；`Dockerfile` 尚未改为 Vue 多阶段构建。详见 `docs/VUE_MIGRATION.md` 第 7 节。
（**前两项已在 v2.1 解决**；此处保留 v2.0 当时的真实状态，历史条目不改写。）

---

## [未发布] — 2026-11-07（CI 首次运行与门禁校准）

CI 在 `3e1531f` 上**首次真正运行**（此前仓库从未推送过），结果与处置：

| 项 | 首跑结果 | 处置 |
|---|---|---|
| ubuntu / windows × py3.12 | ✅ 全过 | 无 |
| docker build + healthcheck | ✅ 构建成功、探活返回 200 | **已转为阻断门禁** |
| coverage | ✅ | 保持信息性（未设下限） |
| dependency audit | ❌ pillow 23 项、pyarrow 1 项 | 受 streamlit 约束无法升级，记录进 SECURITY.md |
| ubuntu / windows × py3.11 | ❌ `Unit tests` 失败 | 未定位（日志需认证），矩阵收窄为 3.12 / 3.13 |

### 改动

- `pytest.ini`：`error::DeprecationWarning` 收窄为 `error::DeprecationWarning:src\..*`，
  只拦本项目代码触发的弃用告警，上游依赖的告警不再打挂整批测试
- `.github/workflows/ci.yml`：矩阵 `3.11/3.12` → `3.12/3.13`；`mypy` 只在 3.12 跑一次
  （类型目标由 `python_version` 决定，与运行矩阵无关）；audit 步骤加 `PYTHONUTF8=1`；
  docker job 去掉 `continue-on-error`
- 最低 Python 版本 3.11 → **3.12**（README / requirements.txt / pyproject 三处同步）

### 发现的两个真问题

1. **pip-audit 在 Windows 上直接崩溃**：`requirements.txt` 含中文注释，pip-audit 的解析器
   用系统 locale（GBK）解码，抛 `UnicodeDecodeError`。CI 的 ubuntu 不受影响，但本地
   跑不了——加 `PYTHONUTF8=1` 解决。
2. **pip-audit 发现真实漏洞但无法修**：`pillow 12.3.0`（23 项 CVE）与 `pyarrow 21.0.0`
   都要求升到 13.0.0 / 23.0.1，而 `streamlit 1.51.0` 硬约束 `pillow<13`、`pyarrow<22`。
   属上游死锁，已记录影响评估与解除条件。

---

## [未发布] — 2026-11-07（第八轮：类型归零与冒烟实测）

### 类型检查

mypy 从 13 处降到 **0 处**，`mypy src` 提升为 CI 阻断门禁：

- `eval/checks.py`：类别/预算分支改用独立变量名；补 `LP001` 夹具断言；
  `per_product` 收窄为 dict 并校验返回契约
- `settings.py`：`_save` 签名对齐 `api_config.save` 的字段类型
- `knowledge_admin.py`：会话缓存加 `RetrievalResult` 注解
- `history.py`：报告详情补 `selected` 非空判断
- `knowledge.py`：补 `demand` 不变量断言
- `analysis.py`：零参回调由默认参数 lambda 改为 `functools.partial`（行为一致）

CI 结构同步：`mypy` 移入阻断 job，原 `quality` job 改名 `coverage`，只留覆盖率报告。

### 浏览器验证

`submission/smoke_test.py` **首次实际运行并通过**（桌面 + 375px，各 4 项断言）：

- 新增 `--channel` 参数，默认 `msedge` 复用系统 Edge，无需下载 chromium
- 固定 8 秒等待改为 45 秒**条件等待**：实测分析耗时约 14 秒，原写法会假失败
- 断言失败也保存全页截图（原实现只在异常分支截图，漏掉「判断错了」这类失败）
- `.gitignore` 忽略 `submission/screenshots/smoke-*.png`

---

## [未发布] — 2026-11-06（第七轮：全量收尾）

在 `d32382c` 之后继续，把剩余待办逐项补齐。

### 代码质量

- 全库 `ruff format`：79 个文件统一格式，`ruff format --check` 已收敛为 CI 阻断门禁。
- mypy 错误从 32 处降到 13 处：修掉 `Tool.run` 的 Callable 逆变（4 处）、
  `catalog_meta` 的 dict/Product 混用（3 处）、`recommender` 的可选价比较（3 处）、
  `eval_dashboard` 的报告空值守卫（8 处）、`catalog_admin` 的元组/列表（1 处）。
  剩余 13 处均为可选值语义（eval 断言与页面里的 `Demand | None`），
  需逐个确认业务意图，仍保持信息性 job。

### 功能与健壮性

- 新增 `src/http_client.py`：进程内共享 httpx 连接池（对话与向量化复用），
  `post_with_retry()` 对超时 / 连接错误 / 429 / 5xx 做最多 3 次指数退避重试；
  4xx 立即返回，重试耗尽后把最后一次结果交给上层降级。+5 条测试。
- 新增 `tests/test_data_contract.py`：11 条商品与评测数据契约断言
  （id 唯一、必填字段、品类枚举、价格为正、来源可追溯、specs/pros/cons 形状）。
  换数据源时先跑它，避免评分静默失真。
- 新增 `scripts/init.py`：一键初始化（检查 Python、空库导种子、建初始管理员、
  打印现状体检），幂等。
- 新增 `scripts/restore_db.py`：`--backup` / `--verify` / `--restore`，
  备份用 `VACUUM INTO`（含 WAL 未 checkpoint 数据），恢复前自动备份当前库。
- 新增 `submission/smoke_test.py`：真实浏览器冒烟断言（登录、分析出首选方案、
  375px 无横向溢出、控制台无致命错误）。**本次未在开发环境运行**，需装
  Playwright 浏览器后先跑一次。

### 文档与发布

- 新增 `LICENSE`（MIT），并单独说明商品数据来源与署名要求。
- 新增 `.github/dependabot.yml`：pip 每周、Actions 每月提 PR。
- `CONTRIBUTING.md` 补格式门禁、`init.py --check` 与浏览器冒烟用法。

---

## [未发布] — 2026-11-06（第六轮）

### 性能

- `src/database.py`：所有 SQLite 连接启用 WAL、`synchronous=NORMAL`、
  `busy_timeout=10000`，并把 Python 侧 `timeout` 对齐到 10 秒。多线程
  Streamlit 下读不再阻塞写；PRAGMA 失败只记 warning，不影响原有容错路径。
- 新增 2 条测试：PRAGMA 生效、PRAGMA 失败时只记日志不抛异常。

### 代码质量

- 清理 28 处历史 lint 问题（未使用导入/变量、冗余 f-string），其中 26 处由
  `ruff check --fix` 自动修复，2 处手工确认后删除/改为副作用调用。
- `pyproject.toml` 的 ruff 规则集从 `E9/F63/F7/F82` 收紧为完整的
  `E4/E7/E9/F`，并为 `__init__.py` 的重导出加 F401 豁免。CI 的 lint 门禁
  现在覆盖未使用导入与变量。
- 收紧规则后 `ruff check .` 与全量测试均无回归。

### 功能

- `eval/runner.py` 新增 `--list-categories`，列出全部场景类别与用例数；
  `--only` 匹配不到时，错误信息会一并列出可选项，不再只说「没有匹配」。
  中文子串匹配语义保持不变，向下兼容。
- 新增 1 条 `--list-categories` 测试，并扩展原「未知类别」用例断言可选项提示。
- README 第 7 节同步新命令。

### 文档

- 新增 `CONTRIBUTING.md`（环境、提交前检查、代码约定、OpenSpec 变更流程）；
- 新增 `SECURITY.md`（演示级鉴权边界、密钥存储、已做/未做加固、报告渠道）；
- 新增本文件 `CHANGELOG.md`。

---

## 2026-11-06 — `d32382c`

汇总评审后的全部修复与工程化改动，30 个文件，测试数 1084 → 1095。

### 安全与缺陷

- 修复 `app.py` 侧栏用户名/角色未转义导致的**存储型 XSS**（用户名允许 HTML
  元字符且渲染进 `unsafe_allow_html` 块），新增回归测试。
- 修复评测 CLI 在 Windows GBK 控制台因 ✅/❌ 抛 `UnicodeEncodeError`：终端输出
  降级为 `[OK]`/`[FAIL]`，写文件仍用 UTF-8，报告内容不变。
- `api_config.save()` 在原子替换前把含明文密钥的临时文件权限收紧为 `0600`。
- 补 `Any` / `Passage` 导入，消除 4 处 F821 注解缺陷。

### 工程化

- 新增 `.github/workflows/ci.yml`：`test`（ubuntu+windows × py3.11/3.12，阻断）、
  `quality`、`security`、`docker`（后三者信息性）。
- 新增 `pyproject.toml`、`requirements-dev.txt`、`.gitattributes`；
  `.dockerignore` 排除开发工具与比赛材料。
- 运行时依赖精确锁定 `==`，最低 Python 版本对齐 3.11（`numpy 2.3.5` 要求）。
- 三处文档测试数统一并写明「以 `pytest --collect-only` 为准」。

### 健壮性与性能

- 向量矩阵模块级缓存（按库文件 mtime 失效、重建后主动清除），`search` 不再
  每次全表读 + 逐行 `json.loads`。
- 损坏向量行逐行跳过并记 warning；查询向量与 `limit` 边界校验。
- 检索入口拒绝空白/超长查询、空向量响应带原因降级、语义无命中给出中文说明，
  补分级日志与模块注释。
- 累计新增 11 条回归测试。

### 文档与脚本

- `submission/` 三个截图脚本的本机绝对路径改为 `__file__` 定位，账号口令改为
  环境变量可覆盖（默认值不变）。
- README、DEPLOY、openspec、technical-introduction 同步现状；新增评审大纲。

---

## 已知边界（非缺陷）

- 账号体系是演示级：无登录限流、无会话过期，见 `SECURITY.md`；
- 商品数据 20 条、2 品类，全部 `unverified`，价格非实时；
- Streamlit 单体、无 HTTP API，SQLite 不适合多实例并发写；
- `ruff format --check` / `mypy` 仍有历史差距，CI 中暂为信息性步骤。
