## Why

效果评测已经能跑，但全部逻辑挤在 `scripts/evaluate.py` 一个脚本里：结果只有终端文本和 Markdown，机器读不到；runner 本身没有测试，重构或加用例时坏了也不会有人发现；界面上看不到任何评测结论，答辩时只能现场跑脚本或翻文档。

把评测链路拆成可测试的包、固定产出机器可读报告，并把它接进管理端页面，才能让「系统效果如何」成为应用里随时可查的事实，而不是一份容易过期的文档。

## What Changes

- 把 `scripts/evaluate.py` 拆成 `eval/` 包：`checks.py` 放各类用例的检查逻辑，`runner.py` 负责载入、调度、计时与 CLI，`report.py` 负责终端表 / Markdown / JSON 三种输出。
- `scripts/evaluate.py` 保留为薄包装，原有命令（`--only` / `--json` / `--write`）继续可用，不破坏 README 和已有自动化。
- 报告新增机器可读的 `report.json`：包含生成时间、用例数、通过/失败、逐条耗时、分类汇总、自动指标与检索模式；`report.md` 与之同源生成，避免两份数字不一致。
- 新增管理端「效果评测」页，读取 `data/evaluation/report.json`，展示总通过率、分类通过情况、失败明细与检索模式；报告不存在或格式过期时给出明确的生成命令，不展示任何推算数字。
- 新增 `tests/test_eval_runner.py` 与 `tests/test_eval_dashboard.py`：覆盖 runner 可执行、单条失败不中断、输出结构、可复现性、报告缺失时的页面行为。
- `.gitignore` 忽略本地生成的 `report.md`，并保留一份 `report.json` 快照供线上演示；README「测试与评估」补充生成命令与报告位置；`docs/eval-report.md` 用新渲染器重新生成。

**不做**：不改 `src/scoring.py` / `src/recommender.py` / 知识检索的核心逻辑；不新增运行时依赖；不联网；不引入第三方基准，评测仍是自评。

## Capabilities

### New Capabilities

- `evaluation-dashboard`: 管理端读取并展示评测报告的行为，包括空状态、指标口径、失败明细与检索模式说明。

### Modified Capabilities

- `evaluation`: 评测脚本的交付形态从「单脚本 + 文本/Markdown」扩展为「可测试的 runner + 机器可读报告」，并新增 runner 自身可复现、单条失败隔离的明确要求。

## Impact

- 新增：`eval/__init__.py`、`eval/checks.py`、`eval/runner.py`、`eval/report.py`、`src/ui/pages/eval_dashboard.py`、两个测试文件。
- 修改：`scripts/evaluate.py`（改为薄包装）、`app.py`（管理员导航项）、`src/config.py`（报告路径）、`.gitignore`、`README.md`、`docs/eval-report.md`。
- 不改：Streamlit 之外的页面、数据库结构、鉴权与商品数据；无新增依赖。
- 范围外：清单中的 FastAPI 服务层（与 `openspec/project.md` 技术约束第 1 条「FastAPI 暂缓」冲突，需先单独修订约束）、启动/部署脚本（Docker 资产已存在）、反事实解释、PDF/分享、价格提醒，均留待后续变更。
