# 代码审查与优化说明（2026-11-08）

本轮对 Vue 版（`backend/` + `src/` + `frontend/src/`）及其文档做了逐项审查：代码质量、
可读性、可维护性、命名与风格一致性、潜在缺陷、冗余与重复逻辑、性能，以及文档与实现的
一致性。下面按「缺陷 → 可维护性 → 文档」三块说明改了什么、为什么改。

审查分三批：**第一批**覆盖 Vue 主链路（`backend/app/*` + `frontend/src` 主要视图 + 主文档）；
**第二批**补齐 `src/` 核心业务模块、`scripts/`、构建与 CI 配置（第六节）；
**第三批**由部署后反馈触发，处理 Streamlit 耦合、检索回退与向量索引构建（第八节）。

累计改动：46 个文件，+1007 / −315 行，新增 2 个前端模块、1 个 Python 运行时缓存模块、
1 份 Vue 版依赖清单。

---

## 一、缺陷修复

按影响从高到低排列。每条都给出触发条件，便于日后回归。

### 1. 请求头会被整体覆盖（`frontend/src/api/client.ts`）

**问题**：对象展开顺序写反了。

```ts
headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
...init,   // ← init 里的 headers 在这里把上面整个覆盖掉
```

**后果**：任何调用方只要传了 `headers`，默认的 `Content-Type: application/json` 就丢失，
后端按纯文本解析 → 422。本次部署调试时我自己就踩到过（PowerShell 拼 JSON 触发的 422，
虽然根因不同，但同一处代码确实会让手写 headers 的调用静默失效）。

**改法**：用 `Headers` 合并，并放在 `...init` 之后。

```ts
const headers = new Headers(init.headers)
if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
const response = await fetch(`/api${path}`, { credentials: 'same-origin', ...init, headers })
```

### 2. 新机器首次启动永远登录不了（`backend/app/main.py`）

**问题**：legacy 版在 `app.py` 里有 `_bootstrap_once()`，负责导商品种子、建初始管理员、
接入 `ZHIGOU_RESET_ADMIN_PASSWORD` 恢复通道。Vue 版入口 `backend/app/main.py` **完全没有**
这段逻辑——数据库表建了，但账号表是空的，登录必然 401。

**证据**：线上实测时 `/api/health` 返回「数据库正常」，而登录持续 401；手动执行
`scripts/init.py` 后才恢复正常。

**改法**：增加 `lifespan` 启动初始化，三件事全部幂等，失败只记日志不阻断启动
（否则连 `/api/health` 都打不开，排查更难）：

1. 商品库为空 → `product_store.seed_from_json()`
2. 账号表为空 → `accounts.ensure_initial_admin()`
3. 设置了 `ZHIGOU_RESET_ADMIN_PASSWORD` → 覆盖已有管理员密码

**理由**：初始化必须跟着应用启动走，而不是依赖运维记得手动跑脚本。同时保留
`scripts/init.py` 作为独立体检手段，文档已注明其不再是必需步骤。

### 3. 评测快照在部署环境读不到（`backend/app/services.py`）

**问题**：`Path("data/evaluation")` 是相对路径，依赖进程当前工作目录。用 systemd 启动时
`WorkingDirectory` 一旦不是项目根，就静默读不到报告，页面显示「尚未生成评测报告快照」
——看起来像数据缺失，实际是路径错了。

**改法**：改用 `config.PROJECT_ROOT / "data" / "evaluation"`（项目内所有路径都走这个常量，
这里是唯一漏掉的一处）；多份快照按 `st_mtime` 取最新，而不是取字典序第一份。

### 4. 全站记录数虚报（`backend/app/admin_api.py` + `OverviewView.vue`）

**问题**：`/api/admin/analyses` 硬截 100 条，前端把 `entries.length` 直接显示成
「全站分析记录（N）」。记录超过 100 条后这个数字就是错的，而且没有任何提示。

**改法**：接口补返回 `total`（`database.count_analyses()`，函数本来就有）与 `limit`；
界面统计卡用 `total`，标题按是否截断显示「共 N 条，显示最近 M 条」。

### 5. 退出登录可能不跳转（`frontend/src/stores/session.ts`）

**问题**：`logout()` 在 `finally` 里清空用户状态，但异常继续向调用方冒泡。
`AppShell.vue` 里是 `await session.logout()` 紧接着 `router.replace('/')`，
接口一旦失败，第二句不执行，用户停在原页面，还会产生未捕获的 rejection。

**改法**：`catch` 掉并补注释说明「退出以本地状态为准」。顺带修 `restore()`：
原先只在 401 时清 `user`，其它错误既不重置 `user` 也不重置 `error`，错误提示会一直残留。

### 6. 评测页失败后无限转圈（`frontend/src/views/EvalView.vue`）

**问题**：模板末尾是 `v-else` 的「正在读取评测数据…」，没有 `loading` 标志。
请求失败后 `response` 为 `null`，仍然命中这个分支，spinner 永远转。

**改法**：加 `loading` 状态，`finally` 里置 `false`，模板改 `v-else-if="loading"`。

### 7. 历史详情存在竞态（`frontend/src/views/HistoryView.vue`）

**问题**：`open(id)` 先清空 `detail` 再请求，快速点两条记录时，**先发出的慢请求后返回**，
会把后选中那条的内容覆盖掉。

**改法**：记录 `requested = id`，响应回来后校验 `activeId.value === requested`，不一致就丢弃。

顺带把收藏加载并入 `load()` 的 `Promise.all`：原先先关 `loading` 再拉收藏，
「我的收藏」会先闪一下空状态再跳成真实数据。

### 8. 收藏加载失败伪装成「没有收藏」（`HistoryView.vue`）

**问题**：`catch { favorites.value = [] }` —— 加载失败和「确实没有收藏」在界面上完全一样。

**改法**：记录到 `error`，让用户看到「收藏加载失败」而不是误以为数据丢了。

### 9. 收藏重复提交（新增 `frontend/src/composables/useFavorites.ts`）

**问题**：`AnalysisView` 与 `QAView` 各写了一份**完全相同**的收藏逻辑，而且都缺两点：
`QAView` 没有 `if (!productId) return` 守卫；两者都没有在途保护，连点两次会发两次请求，
并用过期快照回写数组，最终状态可能反掉。

**改法**：抽成 `useFavorites()`，含 `load()` / `toggle()` / `pending`，两处共用。
`toggle` 内部用 `pending` 数组做重入守卫，`finally` 里释放。
调用方只负责把异常翻译成自己的错误文案。

### 10. 下架商品可以被加入比较（`frontend/src/views/CompareView.vue`）

**问题**：`/api/products` 会返回下架商品（这是有意的，历史记录要能读到），
但 `CompareView` 没过滤 `is_active`，用户能把已下架商品拉进比较表。

**改法**：过滤条件补 `x.is_active !== false`（与后端 `data_loader` 的「缺字段按在售处理」
保持同一口径，不能用 `=== true`）。

### 11. `/api/meta` 的用户字段与前端类型不符（`backend/app/main.py`）

**问题**：`/api/meta` 手写返回 `{username, role, is_admin}`，少了 `role_label`；
`/api/auth/login` 和 `/api/auth/me` 各自也手写了一份几乎相同的字典。三处字段已经开始漂移，
而前端 `Meta.user` 声明的是 `SessionUser`（含 `role_label`）。

**改法**：抽 `_session_payload(user)`，三处共用。一处定义，字段不可能再漂。

### 12. 登出硬编码 Cookie 名（`backend/app/main.py`）

`request.cookies.get("zg_session")` / `delete_cookie("zg_session")` 改成 `COOKIE_NAME`。
改名时不会漏掉某一处，这是会话类代码最容易出的低级错误。

### 13. 检索调试接口没有兜底（`backend/app/admin_api.py`）

`/api/admin/knowledge/retrieve` 直接调 `retrieve()`，链路一炸就是 500，FastAPI 的通用文案
会把真实原因盖住。改为按降级语义返回（`mode: "unavailable"` + 可读提示 + 空结果），
与 `/api/qa` 的回退约定保持一致。

### 14. 非法数字静默提交（新增 `utils/format.ts` 的 `toNumberOrUndefined`）

`Number('abc')` 得到 `NaN`，`JSON.stringify` 后变成 `null`，后端看到的是「用户清空了字段」。
`SettingsView` 的 `embedding_dim` 就是这么写的。改为统一的安全解析：空串与非法输入都返回
`undefined`，调用方只在有值时才放进 payload。

### 15. 管理页没有路由守卫（`frontend/src/router/index.ts`）

五个管理页在路由表里都标了 `meta.admin: true`，但**没有任何地方读它**——手动改 hash 就能
进入页面。虽然后端每个管理接口都有 `AdminUser` 依赖（权限没被绕过），但用户会看到满屏 403。

**改法**：补 `router.beforeEach`，未登录先 `restore()`，非管理员访问 `meta.admin` 页重定向首页。
注释里写明这是第三层防线，权限判定仍以后端为准。

同时把 `App.vue` 里的 `onMounted(() => session.restore())` 移除，避免和守卫各发一次
`/auth/me`。

---

## 二、可维护性与风格

### 统一格式化（新增 `frontend/src/utils/format.ts`）

审查发现时间格式化写了 **4 份**，而且有 **2 种口径**（`.slice(0,16)` 到分钟、
`.slice(0,19)` 到秒）；价格也有两套写法——前端 `¥2999`、后端 `price_label` 却是「2999 元」。

现在统一为 `formatDateTime(value, { seconds })`、`formatPrice(value)`、
`toNumberOrUndefined(value)`，`HomeView` / `HistoryView` / `OverviewView` / `EvalView` /
`CompareView` / `CatalogView` / `QAView` / `SettingsView` 全部改为调用。

### 消除类型重复声明（`CatalogView.vue`）

该文件把 18 个字段的 `ProductRow` 重新声明了一遍，与 `api/types.ts` 的 `Product` 高度重复
且已经漂移（缺 `entered_by` / `entered_at` / `price_source` / `price_collected_at`）。
改为 `type ProductRow = Product`，只保留别名以免模板大改；同时把 `Product` 的缺失字段补齐。

顺带修一个多余请求：原先 `Promise.all` 里多拉一次全量 `/products`，只为取 `categories`，
而 `/admin/catalog-meta` 已经带回带中文 label 的品类。现在直接从 meta 映射。

### 在途守卫

`SettingsView.saveConfig`、`CatalogView.saveCategory/saveBrand/toggleActive` 原先都没有
在途保护，连点会重复提交并触发多次全量刷新。统一补 `busy` 守卫 + `finally` 复位。

### 静默异常补日志（`backend/app/services.py`）

三处 `except Exception: pass` 改成 `logger.warning(..., exc_info=True)`：
知识检索回退、模型服务初始化失败、模型回答失败。

**理由**：降级是设计好的行为，但「线上问答永远走规则模式」这类问题，在没有日志的情况下
根本无法定位——它和「用户没配密钥」表现完全一样。

### 会话过期与清理（`backend/app/core.py`）

`_sessions` 原本只增不减：Cookie 有 12 小时有效期，但服务端字典里那些「登录后就没再回来」
的 token 会一直留到进程重启。

改为 `dict[str, tuple[User, float]]`，记录过期时刻；`user_from_request` 命中过期即删除并视为
未登录；`create_session` 时顺手清理其它过期项。

### 其它细节

- `AppShell.vue` 的 `route.path === item.to` 改为 `exact-active-class="active"`
  （将来加子路由时高亮不会失效）。
- `health()` 返回类型 `dict` → `dict[str, str]`。
- `CompareView` 的 `rows` 去掉与字段类型完全一致的冗余 `as Record<string, unknown>[]`。
- 页脚版本号 `2.2` 与变更记录（已到 v2.4）不一致，对齐为 `2.5`。

---

## 三、文档同步

审查发现文档里「无会话过期」这句话出现在 9 个文件里，而本轮已经实现了 12 小时绝对过期，
必须同步；同时规范里还留着一句 Vue 版不成立的描述。

| 文件 | 修改 |
|---|---|
| `SECURITY.md` | 「没有会话过期」→「有 12 小时绝对过期、无空闲超时」；未做清单里去掉绝对过期 |
| `README.md` | 鉴权边界描述同步 |
| `DEPLOY.md` | 同上；并**补齐部署必需但缺失的步骤**（见下） |
| `docs/auth-boundary.md` | 顶部说明与待办清单同步 |
| `docs/architecture.md` | 鉴权边界同步 |
| `docs/requirements.md` | 鉴权边界同步 |
| `docs/technical-introduction.md` | 鉴权边界同步 |
| `docs/VUE_MIGRATION.md` | 已知限制同步；`scripts/init.py` 标注为可选 |
| `openspec/specs/web-ui/spec.md` | 「刷新页面后需要重新登录」是 legacy 行为，Vue 版 Cookie 会话刷新不掉线，改为「会话仅保存在服务端内存」 |
| `CHANGELOG.md` | 新增 v2.5 条目 |

**`DEPLOY.md` 补的内容**（本次实际部署踩出来的，原文档完全没有）：

1. 启动时会自动初始化，不再要求手动跑 `scripts/init.py`；
2. `ZHIGOU_ADMIN_PASSWORD` **必须显式配置**——不配就随机生成，明文只出现在启动日志里，
   用 systemd 部署时很容易错过；
3. 云服务器要在安全组放行 8000/80/443。「本机 curl 正常、外面连接超时」几乎都是这一步；
4. 必须用 systemd 守护，否则 SSH 断开或重启后站点就打不开；
5. 2G 内存的机器要在本地构建 `dist/` 再上传，避免 `vue-tsc` 构建 OOM。

**界面文案与规范披露**：

- `LoginView.vue` 原写「长时间未操作后需要重新登录」——实现是**绝对过期**，不是空闲超时，
  文案在描述一个不存在的功能。改为「登录满 12 小时后需要重新登录」。
- 规范要求登录页与说明页披露鉴权边界，但界面原本一处都没有。已在登录页补演示级鉴权提示
  （明确「请勿使用真实密码或填写个人信息」），在 `AboutView.vue` 补一条 FAQ
  逐条列出不具备的能力。

---

## 四、有意保留的取舍

以下几点审查中发现但**本轮不改**，理由记录在此，避免下次重复讨论：

1. **`DecisionReport` 的索引签名 `[key: string]: unknown`**：它会让拼写错误的字段访问逃过
   类型检查，属于真实的类型安全损失。但报告结构由后端 `asdict()` 动态产出，删除它需要
   先逐个确认所有访问点，改动面明显大于本轮收益，风险也更高。
2. **七处表单提交的样板代码**（`busy = true` → try/catch → `finally`）没有抽成 composable：
   每个页面的错误文案、成功提示、刷新行为都不同，强行抽象会引入参数爆炸。只补了缺失的守卫。
3. **登录限流**：属于产品决策（阈值、锁定时长、是否按 IP），不是纯代码质量问题，
   已在文档里保留为待办。
4. **`streamlit` 仍是运行时依赖**：Vue 版不需要它，但删掉会影响 legacy 回退路径和现有测试，
   不在本次范围内。

---

## 五、验证

| 检查 | 结果 |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 124 files already formatted |
| `mypy src` | Success: no issues found in 57 source files |
| `pytest -q`（junitxml 统计） | **1114 tests, 0 failures, 0 errors** |
| `npm run build`（含 `vue-tsc --noEmit`） | 通过，64 modules transformed |

另用临时隔离库起 `TestClient` 做接口级验证：

- 登录 / `/auth/me` / `/meta` 三处均返回完整四字段（含 `role_label`）；
- `/admin/analyses` 返回 `entries` / `total` / `limit`；
- `/api/eval` 在新路径下 `available=true`（绝对路径修复生效）；
- 构造过期 token 后 `user_from_request` 返回 `None` 且 token 被清除。

> 注：本机 `pytest` 收尾会触发 IDE 的批量删除保护 shim，截断汇总行（项目文档已记录此现象）。
> 上面的 1114/0/0 取自 `--junitxml` 的机器可读结果。

---

## 六、第二批：补齐 src/ 核心模块、scripts/ 与配置

第一批只覆盖了 Vue 主链路，这一批把 `src/` 下 57 个 Python 文件、`scripts/` 五个脚本、
`pyproject.toml` / `pytest.ini` / CI / Dockerfile 全部过了一遍。**下面只列改了的**，
其余问题（如 `scoring.py` 的 O(n²) 性能、`database.py` 每次读都过一遍 schema 检查）
确实存在，但改动面大或收益有限，记在第七节。

### 1. 商品数据会被写进历史库（`scripts/fetch_products.py`）

**这是最严重的一条。** 脚本的默认写入目标是：

```python
DEFAULT_DB_PATH = PROJECT_ROOT / "storage" / "zhigou.db"   # ← 历史库
```

而商品库是 `products.db`（`config.products_db_path()`）。项目是**双库设计**，
`database.py` 里明确写着「把商品表建到历史库上会让那个文件看起来也装着商品数据」。

**后果**：`python scripts/fetch_products.py --source csv ...` 不带 `--out` 时，
商品被写进历史库、真正的商品库保持旧数据，而脚本还打印「已写入 N 条商品」。
用户以为导入了，实际线上商品一个没变。

**改法**：`DEFAULT_DB_PATH = config.products_db_path()`，`--out` 的帮助文本同步改为
动态默认值。顺带把 `--mode replace` 加上 `--yes` 确认——这条命令能清空整库商品，
此前没有任何提示。

### 2. 覆盖写入可能留下空商品表（`src/product_store.py`）

```python
with _connect(path) as connection:
    connection.execute("DELETE FROM products")
    connection.commit()          # ← 已经提交了
return save_products(records, path=path)   # ← 另开连接写，失败就只剩空表
```

**改法**：把 `save_products` 拆成 `_build_product_rows`（构造待写行）与
`_write_product_rows`（在调用方事务里写，不 commit），`replace_all` 变成单事务：

```python
rows, skipped = _build_product_rows(records, moment)   # 先构造，能在删除前发现空数据
if not rows:
    raise ProductStoreWriteError("没有可写入的商品记录，已中止覆盖操作。")
with _connect(path) as connection:
    connection.execute("DELETE FROM products")
    connection.execute("DELETE FROM product_prices")
    _write_product_rows(connection, rows, records, moment)
    connection.commit()
```

异常时事务未提交，SQLite 关闭连接会回滚，原数据仍在。

### 3. 保存分析时往历史库建商品表（`src/database.py`）

`save_analysis` 调的是 `init_db(path)`，而这个函数自己的文档就是：

> 测试与迁移脚本用——它们通常只对付一个库文件。应用自己的读写在下面两个**按范围**的
> 入口里，**别用这个**。

改为 `init_history_db(path)`。

### 4. 预算下限被静默丢弃（`src/agent/tools.py`）

`_check_budget_range` 校验了 `budget_min`（正数、不大于 `budget_max`），但构造 `Demand`
时只传了 `budget=params.budget_max`，`budget_min` **从未参与筛选**。模型传
「3000–5000 元」，工具会返回 2000 元的商品并回报成功。

**改法**：在工具层按价格过滤（不改 `Demand` 模型，避免波及推荐链路）：

```python
if params.budget_min is not None:
    floor = params.budget_min
    items = [i for i in items if i.product.price is not None and i.product.price >= floor]
```

### 5. 读路径上反复写库（`src/catalog_meta.py`）

`brand_entries()` 第一行就是 `sync_brands(products)`，而 `brand_entries` 被
`recommender` 调用——**每次分析、每次渲染都开一次写事务并 commit**。多线程渲染时
容易撞 `SQLITE_BUSY`，也纯属白写盘。

**改法**：先读现有品牌集合，算出缺失项；缺失为空直接返回 `0`，不开写事务。
实测第二次调用返回 0，确认读路径不再写库。

### 6. 备份脚本的默认调用必然失败（`scripts/restore_db.py`）

`--db` 默认 `all`，而 `--verify` / `--restore` 只接受**单个**备份文件。于是
`restore_db.py --verify backup.bak` 会拿同一个文件去校验两套表，必然以
「备份缺少表」退出——看起来像备份坏了，其实是用法错了。

**改法**：`--verify` / `--restore` 时若未显式指定 `--db`，直接 `parser.error`
并说明「一个备份文件只含一个库」。

### 7. 前端剩余视图

| 文件 | 问题 | 改法 |
|---|---|---|
| `SettingsView.vue` | 配置加载失败后 `cfg` 为 null，模板永远显示「正在读取设置…」 | 补 `cfgLoading`，失败态给「重新读取」按钮 |
| `SettingsView.vue` | `clearConfig` 不受在途标志保护，可与保存并发覆写服务端配置 | 复用 `cfgBusy` |
| `UsersView.vue` | 删除账号是破坏性操作，双击会发两次 DELETE | 补 `busy` 守卫 |
| `UsersView.vue` | 重置密码只判空，不做 8 位校验（label 已写「至少 8 位」） | 前端按同一口径校验 |
| `UsersView.vue` | 刷新后 `passwordFor` 不重置，改密码输入框残留 | `load()` 成功后清空 |
| `UsersView.vue` | 创建时间直接渲染 ISO 字符串 | 改用 `formatDateTime` |
| `KnowledgeAdminView.vue` | `reindex` 不受 `busy` 保护，连点重复全量重扫 | 补守卫 |
| `KnowledgeAdminView.vue` | 新建成功后只清标题与正文，品类/来源残留 | 抽 `EMPTY_DOC_FORM` 整表重置 + 必填校验 |
| `main.ts` | 无 `errorHandler` / `unhandledrejection`，生产环境错误无痕 | 注册全局兜底并统一加前缀 |

### 8. 配置与文档不一致

| 位置 | 问题 | 改法 |
|---|---|---|
| `scripts/init.py` | `MIN_PYTHON = (3, 11)`，而 README / `requirements.txt` 声明 3.12 | 改为 `(3, 12)`，注释说明为何比 numpy 的 3.11 更严 |
| `scripts/init.py` | 末行提示 `streamlit run app.py`（legacy 入口） | 改为 `python backend/run.py` |
| `.github/workflows/ci.yml` | 注释写 `python_version = "3.11"`，`pyproject.toml` 实际是 3.12 | 更正并注明以 pyproject 为唯一来源 |
| `AppShell.vue` | 页脚版本 `2.5` | 对齐 `2.6` |

---

## 七、第二批中确认存在、但本轮未改的问题

按影响排序，理由都在「为什么不改」。

| 位置 | 问题 | 为什么不改 |
|---|---|---|
| `src/scoring.py:359` | `_score_value` 为每件商品重算全部 peer 的性能分，112 件约 1.2 万次重复计算 | 需要改 `score_all` 的签名把缓存传进去，会波及评分链路的多个调用点；2G 机器上实测分析仍在 1 秒内，先记为已知性能项 |
| `src/database.py:558` | `_ensure_ready` 每次读都做 schema 检查 + `executescript` + 迁移，`is_favorite` 每张卡片都走一次 | 加 `(path, mtime)` 就绪标记是正确方向，但它处在所有读操作的咽喉上，改错会让「历史库损坏不影响分析」这条既有约定失效，需要专门的回归用例护航 |
| `src/ai_enhance.py:44` | `_ALLOWED_CONSTRAINTS` 还含静音/降噪等，而 `recommender` 侧已只剩独显 | 属于提示词与推荐层的一致性设计，应把约束表抽成单一来源，改动跨两个模块 |
| `src/report_service.py:80` | `is_over_budget` 用 `budget_label.startswith("超出预算")` 嗅探展示文案 | 改文案即静默失效，正确做法是加结构化字段；但 `budget_label` 是对外展示字段，加字段要同步前端与报告导出 |
| `src/recommender.py:199` | 用 `"无法确认" in explanation` 判断「参数不可校验」 | 同上，应改为三态返回，涉及硬约束检查的返回值契约 |
| `src/config.py:512` | `_DYNAMIC_LOADED = True` 写在 `try` 之前，失败后永久退回内置分类且无日志 | 单独修这一处是安全的，但它与「分类表可被管理页修改」的加载时机耦合，本轮先把明显的日志缺失记下来 |
| `scripts/api_smoke.py:77` | 冒烟脚本会在目标环境真实创建分析记录，用完不清理 | 需要先确认清理接口的删除语义（连带收藏/历史），避免脚本反而删掉真实数据 |
| `Dockerfile` / `docker-compose.yml` | 仍是 legacy Streamlit 版，未改为 Vue 多阶段；以 root 运行 | `DEPLOY.md` 已明确标注为 legacy 并给出替代路径，改造属于独立任务 |
| `.github/workflows/ci.yml` | 没有 `npm run build` 与 Vue 版 API 契约测试 | 加前端 job 需要确定 `npm ci` 的缓存策略与 Node 版本矩阵，属于 CI 改造，单独立项更合适 |

这些不是遗漏，是**明确排期**：改动都会触及跨模块契约，需要在有回归用例的前提下单独做。

---

## 八、第三批：部署后反馈触发的两项修复

这一批不是审查发现的，是**上线后暴露出来的**：模型密钥没同步到服务器、以及「Vue 版为什么还装着 Streamlit」。

### 1. Vue 版为什么仍然 import Streamlit

**不是装多了，是真的有依赖。** 调用链是：

```
backend/app/services.py:214   from src.ui.state import get_knowledge_index, get_vector_store
backend/app/admin_api.py:420  同上
        ↓
src/ui/state.py:14            import streamlit as st
src/ui/state.py:125/181       @st.cache_resource   ← 数据集与索引缓存
```

后端只是想复用那两个缓存函数，代价是整条 `streamlit + pyarrow + altair` 依赖树。

**改法**：把缓存层抽到 `src/runtime_cache.py`，用 `functools.lru_cache` 实现，
缓存键仍是「路径 + 文件 mtime」，语义完全一致：

| 原实现 | 现实现 |
|---|---|
| `@st.cache_resource(max_entries=4)` | `@lru_cache(maxsize=4)` |
| 键含 `path` + `mtime` | 同左（`_mtime` 参数只参与键） |
| `get_catalog()` / `get_knowledge_index()` | 同名，移入 `runtime_cache` |

`src/ui/state.py` 改为**显式重导出**（`from src.runtime_cache import get_catalog as get_catalog`），
界面层调用方式一个字没变，既有 Streamlit 测试全部照旧。

顺带修了 `knowledge_reindex`：它原先 `getattr(state, "_load_index_cached")` 反射猜私有名，
缓存实现一改名就静默清不掉（`cleared_caches` 变成 0 却不报错），改为显式 `clear_caches()`。

**验证**（这是关键，不靠推断）：

```
import backend.app.main →
  streamlit in sys.modules: False
  src.ui      in sys.modules: False

服务器 uv pip uninstall streamlit → 重启 → 首页 200、/api/health 200
```

同时在服务器上卸掉了 streamlit，venv 从 373MB 降下来，并新增 `requirements-vue.txt`
（与 `requirements.txt` 版本一致、只少 streamlit），`DEPLOY.md` 的 Vue 部署段落改为装它。

### 2. 配了 Embedding 密钥反而查不到资料

`retrieval.py` 原本的策略是「语义检索成功但没命中 → 视为没有资料，不回退」，
注释里给的理由是对的（回退会把「语义上不相关」变成「字面碰巧命中」）。

但它混淆了两种根本不同的情况：

| 情形 | 本质 | 正确处置 |
|---|---|---|
| 向量库里**一条向量都没有** | 索引从未构建，检索能力等于零 | 回退关键词，并告知需要先构建索引 |
| 库里有向量，但都低于阈值 | 语义上确实不相关 | 不回退（原策略正确） |

线上实际表现：配了密钥 → 走向量 → 库空 → 返回 0 条 → 问答永久回落
`general-knowledge`，用户看到的是「未找到相关资料」。**配密钥比不配还差。**

**改法**：用 `store.slice_rows(limit=1)` 判断库是否为空，为空则回退并给出明确 note。

**验证**：

```
修复前：mode=vector  count=0  qa.source=general-knowledge
修复后：mode=keyword count=1  qa.source=knowledge+products
```

### 3. 向量索引构建入口（后续已实现）

上面修完回退后，Vue 管理页仍只有「刷新检索索引」（清缓存），没有生成向量的入口，
语义检索这条路依然走不通。后来按用户要求补齐了，对应 `CHANGELOG` 的 v2.8：

| 层 | 改动 |
|---|---|
| 后端 | `GET /api/admin/knowledge/vector`（状态）、`POST .../vector/build`（增量构建） |
| 前端 | `KnowledgeAdminView.vue` 新增「语义检索索引」卡片、统计位与构建按钮 |

**关于「同步会不会超时」的复盘**：我当时判断几十次 API 调用需要异步任务，这个担心
是过度的。`EmbeddingService` 按 10 条一批，线上 38 个切片只发了 4 批、约 2 秒完成；
`build_index` 又按内容哈希跳过已就绪的切片，重复点击 0.01 秒返回且不消耗额度。
所以同步接口 + 状态查询就够了，没有引入后台线程、进度轮询和状态丢失这些新复杂度。

线上实测：构建前 `generation_needed=38` → 构建后 `ready=38` → 检索
`mode=vector, count=3`（此前 `keyword`）→ 问答 `retrieval_mode=vector`。

### 4. 模型密钥为什么「没了」

部署时只写了服务端必需的 5 项（监听地址、端口、管理员账号密码、注册开关），
把 `ZHIGOU_LLM_*` / `ZHIGOU_EMBEDDING_*` 漏掉了——因为本地 `.env` 不入库，
而部署脚本只按「部署必需项」生成配置。

现在已把本地 `.env` 的 9 项模型配置合并进服务器 `.env`（14 项），
`/api/admin/api-config` 返回 `{llm: True, embedding: True}`，问答是真实模型输出。

`DEPLOY.md` 的云端要点里「密钥只放服务端环境变量」这条容易让人以为**不用配**，
已在该节补充「模型密钥需从开发机 `.env` 迁移，否则 AI 功能不可用」。

---

## 九、第四批：O1 / O4 / O3 / O7 四项优化

用户按「改动量小 + 复用现有代码 + 直接补缺口」指定了这四项与顺序。
实施计划见 `Plan/2. O1-O4-O3-O7优化_plan.md`（含三池门禁、方案取舍与回滚点）。

### 1. O1 轨迹落库：「只加两张表」不够

原判定说 `AgentRun` / `TraceStep` 已结构化、只差落库。复核发现**还差一环**：
Vue 版 `run_analysis()` 返回 `ai_enhanced=False`，后端根本没有调用 `run_agent`，
所以只加表的话线上永远没有轨迹可回放。

实际做了三层：

| 层 | 改动 |
|---|---|
| 数据 | `agent_run` / `agent_step` 两表 + `save_agent_run()` / 列表 / 详情 |
| 产生 | `run_agent` 两个返回分支都落库；`run_analysis` 成功后**后台线程**异步跑一次编排 |
| 展示 | 管理端两个接口 + 「全站概览」回放卡片 |

「后台线程」是个取舍：Agent 是多轮模型调用，塞进同步分析会把响应从毫秒拉到几十秒
（`VUE_MIGRATION.md` 已知限制 1 早就写过）。代价是轨迹与当次报告只靠
`question` + 时间戳弱关联；若以后要求强一致，得改成同步或异步任务 ID。

降级分支也落库是刻意的：被参数校验拒绝、执行出错的调用，恰恰最能证明
「校验真的在拦」，比一串全绿的轨迹更有说服力。

### 2. O4 两个新工具

- `find_similar_products`：**同品类硬前提**，再用 `scoring.spec_bounds` 的维度边界
  把规格数值归一求距离，叠加价格接近度与 `normalize_use_case` 后的场景重叠。
  没有可比维度时返回 `None` 并跳过该项，不把「没数据」当成「完全相似」。
- `get_user_profile`：读本人收藏与历史，提炼品牌/品类/近期首选。
  参数模型**刻意不收 `user_id`** —— 身份只能来自 `ToolContext`，
  否则模型可以传别人的 ID 读别人的数据。这是这一批里唯一新增的安全边界。

`ToolContext` 加 `user_id` 用默认值 `None`，所有既有构造点无需改动。

### 3. O3：清单判定过时，实际只剩一半

清单写「无会话过期、无限流」。复核：12 小时绝对过期早就在 `core.py` 里，
真正缺的是失败计数/锁定与空闲超时。

- `login_failures` 按**用户名**而不是 IP：公网在反向代理之后，按 IP 锁会误伤所有人。
  时间戳存 Unix 秒（REAL），避开 ISO 字符串与时区混用。
- UPSERT 与阈值判断放同一事务，并发请求不会各自读到旧计数。
- 限流表读失败一律「放行 + 记日志」：安全组件故障不能把所有人挡在门外。
- `_sessions` 从 2-tuple 改 3-tuple，交付前 grep 全部解包点确认同步；
  空闲滑动只更新「最近活动」，**不延长绝对过期时刻**。

### 4. O7：MCP 依赖踩的版本坑

用官方 `mcp` SDK 的**低层 `Server`** 而不是 `FastMCP` 装饰器：工具声明来自
pydantic 模型动态生成，装饰器靠函数签名推断会把 schema 弄丢。
`list_tools` 直接把 `registry.declarations()` 转成 `inputSchema`，
`call_tool` 直接 `registry.invoke()` —— 协议适配层，零业务重复。

**依赖引前审查实测**（B2 门禁）：`mcp 1.9.4` MIT、Python >=3.10；
但它与 pydantic 2.14.x 不兼容（`pydantic._internal._typing_extra.eval_type_backport`
已被移除）。改用项目锁定的 `pydantic==2.12.4` 后正常，于是把版本组合写死在
`requirements-mcp.txt` 并在文件里记下这次实测结论。依赖完全隔离，
Vue 部署的 `requirements-vue.txt` 不含它。

第一次端到端探针还暴露一个探针自身的问题：一次性写完 stdin 就 EOF，
`tools/call` 请求在 server 处理前流就关了。改成逐条交互式会话后，
`initialize` / `tools/list` / 两次 `tools/call` 四个响应齐全、退出码 0。

### 5. 回归基线里出现的 1 个失败，怎么处理

全量 `pytest` 第一次复验报 `tests/test_agent_tools.py::test_four_tools_are_registered`
失败——断言写死 4 个工具，而用户明确要求扩到 6 个。这是**规格变更导致断言过时**，
不是实现缺陷：把测试改名为 `test_six_tools_are_registered` 并断言 6 个，
同时注明 MCP 的 `tools/list` 复用同一顺序。没有为了「让实现通过」而放宽断言。
另修了 `mcp_server/server.py` 的 4 处 E402（`sys.path` 引导后的导入需 `# noqa`）。

### 6. 验证汇总

| 层 | 证据 |
|---|---|
| 静态 | `ruff check .` / `ruff format --check .`（127 文件）/ `mypy src` 全绿 |
| 测试 | `pytest -q` **1114 / 0 failures / 0 errors**；`npm run build` 通过 |
| O1 | 隔离库 `run_id=1`、列表 1 条、详情 2 步（`ok` + `rejected`）、接口 200/200/400 |
| O4 | 6 个工具注册；相似商品返回 3 件；非法 ID 与无用户画像均 `rejected` |
| O3 | 5 次失败 `[401,401,401,401,429]`、锁定期正确密码 429、解锁 200、空闲超时 `me` 401 |
| O7 | 真实 stdio JSON-RPC 4 个响应齐全、退出码 0；`tools/list` 6 个工具带 `inputSchema` |

### 7. 已知限制（如实披露）

- 轨迹与分析报告是**弱关联**（后台异步，靠问题文本 + 时间戳），没有任务 ID。
- MCP stdio 进程没有 HTTP 登录态，`get_user_profile` 恒返回 `rejected`；
  要支持用户维度需由客户端在会话初始化时传入可信身份，本轮没做。
- 登录限流是**单进程内存 + SQLite** 方案，多副本部署需换成集中式计数。
- `mcp` 依赖只做了本地隔离环境验证，没有装进线上 venv（它是独立可选进程）。
- 生产持久化（PostgreSQL / 连接池，roadmap T5）仍未做。
