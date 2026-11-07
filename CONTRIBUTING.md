# 参与开发

本文说明如何把项目跑起来、改动要遵守哪些约定，以及提交前要过哪些检查。
需求与设计决策记录在 `openspec/`，定位「为什么这样做」优先看那里。

## 1. 准备环境

> **版本状态**：当前主界面是 Vue 3 + FastAPI；`src/` 业务层与 legacy Streamlit 版共用。
> 目录分类见 [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)，
> 迁移状态与 API 清单见 [docs/VUE_MIGRATION.md](docs/VUE_MIGRATION.md)。

需要 **Python 3.12 或更高版本**（最低版本已收窄；3.11 的测试未验证通过，见 `README.md`）
与 **Node.js 18+**（本机实测 v24.15.0 / npm 11.12.1）。

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cd frontend && npm install && cd ..

# 当前版本：先构建前端，再启动单端口服务
npm --prefix frontend run build
python backend/run.py                 # http://127.0.0.1:8000

# 开发态热更新（另开终端）
npm --prefix frontend run dev         # http://127.0.0.1:5173，/api 代理到 8000

# legacy 版（回退 / 对照用）
streamlit run app.py                  # http://localhost:8501
```

不配置任何密钥也能使用智能分析、商品比较、历史记录等核心功能；
AI 增强与向量检索需要密钥，配置方式见第 3 节。

前端提交前另跑：

```bash
npm --prefix frontend run build       # vue-tsc --noEmit && vite build
```

## 2. 提交前检查

```bash
pytest -q                          # 全量测试，不需要网络与密钥
ruff check .                       # 阻断门禁：未定义名、未使用导入/变量等
ruff format --check .              # 阻断门禁：格式
python -m eval.runner --write /tmp/report.md   # 评测冒烟；--list-categories 可看类别
python scripts/init.py --check     # 只看现状：商品数、账号数、语料、评测用例
```

真实浏览器冒烟（可选，需另开终端 `streamlit run app.py`）：

```bash
python submission/smoke_test.py            # 默认 --channel msedge，复用系统 Edge
python submission/smoke_test.py --mobile   # 375px 视口
# 非 Windows 或没有 Edge：playwright install chromium，再传 --channel ""
```

实测（2026-11-07）：桌面与手机视口各 4 项断言全部通过。本地规则模式下「分析」
约 14 秒，脚本用 45 秒条件等待；断言失败会在 `submission/screenshots/` 留全页截图。

`tests/` 全部跑在 Streamlit AppTest 里，不渲染真实 DOM；登录页重影、
`:has()` 兼容性这类问题只能靠上面这个脚本发现。

CI（`.github/workflows/ci.yml`）会在 ubuntu + windows、Python 3.12 / 3.13
上跑测试，以及 `ruff check`、`ruff format --check`、`mypy src` 三项**阻断**门禁；
`docker build + healthcheck` 也已转为**阻断**门禁。
覆盖率、`pip-audit` 是**信息性** job，不阻断合并，但结果值得看一眼。

## 3. 配置与密钥

复制 `.env.example` 为 `.env` 后按需填写，变量名与用途都在样例里。读取优先级是：

```
storage/api_config.json（个人设置页写入）> 环境变量 / Streamlit Secrets > 内置默认值
```

- `.env`、`storage/`、`.streamlit/secrets.toml` 都已加入 `.gitignore`，**不要提交**；
- `storage/api_config.json` 含**明文密钥**，写入时权限会被收紧为 `0600`；
- 公开演示请关闭注册或改强管理员密码，见 `DEPLOY.md` 与 `SECURITY.md`。

## 4. 代码约定

这些是 `openspec/project.md` 里的硬约束，改动时不要打破：

| 约定 | 说明 |
|---|---|
| 分层 | `src/` 除 `ui/` 外**不依赖 Streamlit**，业务函数可脱离界面单测 |
| 配置 | 可调参数集中在 `src/config.py`，业务模块不内联字面量 |
| 异常 | 领域异常定义在 `src/errors.py`，界面只通过 `to_user_message()` 转中文提示 |
| 权限 | `require_admin()` 放在**数据层入口**，界面隐藏入口不算权限 |
| 联网 | AI 增强与向量检索失败必须降级并如实告知用户，核心链路离线可用 |
| 测试 | 每条行为都要有测试；测试不联网、不需要密钥（用 `httpx.MockTransport` 打桩） |

风格上以 `ruff check`（配置见 `pyproject.toml`）为准；新增文件建议顺手跑
`ruff format`。全库格式化尚未收敛，不要一次性格式化无关文件，避免评审噪声。

## 5. 数据与评测

- `data/products.json` 是 20 条商品的种子数据，全部 `data_status=unverified`，
  价格是参考价而非实时价，口径见 `docs/data-disclaimer.md`；
- 修改商品字段后，知识索引会按商品库文件 mtime 自动重建，无需手动清缓存；
- 评测集在 `data/evaluation/cases.json`，指标口径见 `docs/eval-report.md`。
  新增用例后请重跑评测，不要为了让报告好看而删掉失败用例。

## 6. 变更流程

项目用 OpenSpec 记录需求与变更：

1. 在 `openspec/changes/` 下新建变更目录，写 `proposal.md`（改什么、不改什么）、
   `design.md`（为什么这么设计）与 `tasks.md`；
2. 影响到的能力规格，在变更里写 delta spec；
3. 实现时按 `tasks.md` 推进，每组改动跑相关测试；
4. 完成后把变更归档到 `openspec/changes/archive/`，并同步 `README.md`、
   `docs/` 与 `项目全面检查报告.md` 的状态表；
5. 一次只推进一个变更，避免预算过滤、评分权重、AI 校验、权限边界互相踩。

## 7. 相关文档

- [README.md](README.md)：功能、数据流、运行方式
- [DEPLOY.md](DEPLOY.md)：Vue + FastAPI 单端口部署（含 legacy 版部署存档）
- [SECURITY.md](SECURITY.md)：鉴权边界与漏洞报告渠道
- [CHANGELOG.md](CHANGELOG.md)：变更记录
- `docs/architecture.md`、`docs/testing.md`、`openspec/project.md`
