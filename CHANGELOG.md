# 变更记录

格式参考 Keep a Changelog。项目目前没有发布版本号，以日期 + commit 标记。
基线：`97e95db`（比赛提交快照）。

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
