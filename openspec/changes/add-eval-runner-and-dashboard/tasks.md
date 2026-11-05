## 1. 抽取评测包

- [x] 1.1 新建 `eval/__init__.py`，声明包并导出 `run_cases`、`load_cases`、`evaluate` 等公开入口
- [x] 1.2 新建 `eval/checks.py`，把 `Outcome`、检查项类型与 8 个场景检查函数从 `scripts/evaluate.py` 迁入
- [x] 1.3 在 `checks.py` 中实现调度组合：需求类用例只解析一次 `Demand`，再分别执行字段检查与推荐检查
- [x] 1.4 新建 `eval/runner.py`，实现评测集载入、上下文构建、逐条调度、异常隔离、计时与 `main()`
- [x] 1.5 新建 `eval/report.py`，定义 `EvaluationReport`、结构化指标与分类汇总，提供 Markdown / 终端 / JSON 三种渲染
- [x] 1.6 把 `scripts/evaluate.py` 改为薄包装：插入项目根到 `sys.path`、从 `eval.runner` 导入 `main`、透传退出码
- [x] 1.7 运行默认、`--only`、`--json`、`--write` 四种命令，确认输出内容与拆分前一致（指标数字以实测为准）

## 2. 结构化报告

- [x] 2.1 为 `report.json` 定义 `schema_version`、`generated_at`、`dataset`、`retrieval`、`summary`、`metrics`、`manual_metrics`、`categories`、`outcomes`
- [x] 2.2 指标改为 `numerator` / `denominator` / `definition` / `display` 结构；分母为零时 `display` 为「不适用」
- [x] 2.3 计算 `data/evaluation/cases.json` 与 `data/products.json` 的 SHA-256 并写入报告
- [x] 2.4 记录实际检索模式（当前为 BM25 本地关键词检索）与逐条/总耗时
- [x] 2.5 实现 `--output-dir DIR`：一次运行同时写 `report.json` 与 `report.md`，两者由同一 `EvaluationReport` 渲染
- [x] 2.6 在 `src/config.py` 增加 `eval_report_path()`，默认指向 `data/evaluation/report.json`
- [x] 2.7 在 `.gitignore` 忽略生成的 `data/evaluation/report.json` 与 `report.md`
- [x] 2.8 在 `eval/report.py` 实现 `load_report(path)`：处理缺失、坏 JSON、未知 schema、指纹不匹配，返回可直接渲染的加载结果

## 3. 评测页面

- [x] 3.1 新建 `src/ui/pages/eval_dashboard.py`，`render(catalog=None)` 首先调用 `auth.require_admin(state.current_user())`
- [x] 3.2 页面只读取 `config.eval_report_path()`，不调用评测 runner、不启动推荐或检索链路
- [x] 3.3 渲染总览：用例数、通过/失败、总耗时、生成时间、评测集版本
- [x] 3.4 渲染自动指标：定义、分母、实测值同屏；不合成总分
- [x] 3.5 渲染分类通过情况与失败明细（用例 ID、类别、失败检查项与说明）
- [x] 3.6 渲染人工指标为「尚未测量」并列出复核材料；渲染检索模式，缺失时显示「未记录」
- [x] 3.7 在显著位置展示自评声明，复用 `components` / `theme` 现有组件与视觉风格
- [x] 3.8 实现四种异常状态：报告缺失、坏 JSON、未知 schema、输入指纹不匹配；均给中文提示与生成命令，不暴露堆栈
- [x] 3.9 在 `app.py` 导入 `eval_dashboard`，并在 `NAV_ITEMS` 增加 `NavItem("效果评测", ":material/fact_check:", eval_dashboard.render, admin_only=True)`

## 4. 测试

- [x] 4.1 新建 `tests/test_eval_runner.py`：用 1–3 条用例验证 runner 可执行、每条都有 `Outcome` 与检查项
- [x] 4.2 测试单条异常不中断：monkeypatch 某个检查函数抛异常，断言该条失败、其余用例仍有结果
- [x] 4.3 测试可复现：同一子集连续跑两次，比较 `passed` 与逐项 `(name, ok)`，忽略生成时间与耗时
- [x] 4.4 测试 `--only` 过滤与无匹配退出码；测试 `--output-dir` 同时生成 JSON 与 Markdown
- [x] 4.5 测试报告结构：schema、指标分子分母、分母为零「不适用」、人工指标「尚未测量」、Markdown 与 JSON 同源一致
- [x] 4.6 测试 `scripts/evaluate.py` 兼容入口仍能执行 `--only` 子集
- [x] 4.7 新建 `tests/test_eval_dashboard.py`：覆盖 `load_report` 的缺失、坏 JSON、未知 schema、指纹不匹配、正常报告五个分支
- [x] 4.8 按现有 UI 测试方式验证页面正常渲染与空状态，不依赖网络或密钥

## 5. 文档与实测

- [x] 5.1 更新 README「测试与评估」：加入 `python -m eval.runner --output-dir data/evaluation`、`report.json` / `report.md` 位置与页面入口
- [x] 5.2 更新 README「项目结构」，加入 `eval/` 目录说明
- [x] 5.3 更新 `docs/testing.md` 的评测命令与报告位置
- [x] 5.4 用新渲染器重新生成 `docs/eval-report.md`，确认自评声明与逐条明细仍在
- [x] 5.5 实测重跑评测，按实际输出核对 README、`docs/eval-report.md`、`docs/testing.md`、`docs/technical-introduction.md`、`docs/competition-brief.md`、`docs/roadmap.md`、`docs/demo_script.md` 中重复的用例数与指标数字；不一致处按实测更新，不手填
- [x] 5.6 运行完整 `pytest`，确认全绿且没有新增警告
- [x] 5.7 手动验收：生成报告后打开「效果评测」页，逐一验证正常、缺失、坏文件、未知 schema、指纹不匹配五种状态
- [x] 5.8 检查 `git status`：只包含预期文件，确认生成的 `report.json` / `report.md` 未被提交
