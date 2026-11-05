## Context

`scripts/evaluate.py`（565 行）已经实现了完整的评测链路：载入 `data/evaluation/cases.json`、按场景调度 8 类检查、汇总 5 个自动指标、渲染 Markdown，并支持 `--only` / `--json` / `--write`。它被 README、`docs/testing.md`、`docs/eval-report.md` 和 `docs/technical-introduction.md` 引用。

问题不在能力，而在形态：

- 检查逻辑、调度、汇总、渲染全在一个脚本里，无法单独测试任何一层；runner 本身也没有测试。
- `--json` 只输出指标与逐条结果，没有版本号、生成时间、耗时、检索模式或输入指纹，界面无法可靠消费。
- 界面上没有入口，评测结论只能靠翻文档或现场跑命令。
- 报告只有 Markdown，数字与 `report.json` 若各自生成会漂移。

约束来自 `openspec/project.md`：不新增运行时依赖、不联网、保持 Streamlit 单体、评测必须声明为自评、不得报告未测量值。

## Goals / Non-Goals

**Goals:**

- 把评测链路拆成可独立测试的 `eval/` 包，同时保留 `scripts/evaluate.py` 作为兼容入口。
- 产出带版本号、输入指纹、逐条耗时与检索模式的 `report.json`，并让 `report.md` 与它同源。
- 新增管理员可见的「效果评测」页，只读报告，不执行评测。
- 用测试守住 runner 的可执行性、失败隔离、可复现性与报告结构。

**Non-Goals:**

- 不修改评分、推荐、检索或抗幻觉逻辑，也不改评测用例内容。
- 不新增依赖、不联网、不引入第三方基准或综合总分。
- 不在页面里触发评测执行、不制定定时任务、不写 CI 阻断规则。
- 不包含 FastAPI、部署脚本、反事实、PDF/分享、价格提醒等清单中的其它方向。

## Decisions

### D1. 评测代码放在顶层 `eval/`，不放进 `src/`

`src/` 的约定是「业务规则、不依赖 Streamlit」；评测是开发/测量工具，不是运行时业务能力。放顶层 `eval/` 能明确这一点，也避免 `src` 内部的运行时模块反向依赖评测代码。

替代方案：`src/evaluation/`。放弃，因为它会让 `src` 的导入图多出一整块只服务评测的子树，且容易诱导业务代码调用评测模块。

包名 `eval` 与内置函数 `eval()` 不冲突（Python 没有名为 `eval` 的标准库模块），但项目内只允许评测工具与页面读取器导入它。

### D2. `scripts/evaluate.py` 保留为薄包装

现有文档与历史命令都指向它。包装器只做三件事：把项目根加入 `sys.path`、从 `eval.runner` 导入 `main`、透传退出码。这样 `python scripts/evaluate.py --only 知识检索` 继续可用，同时 `python -m eval.runner` 成为新的正式入口。

替代方案：删除脚本、全量迁移命令。放弃，因为会破坏 README、docs 与用户已有习惯，收益只是少一个 10 行文件。

### D3. `eval/checks.py` 按场景拆成 8 个检查函数，调度器负责组合

公开函数与职责：

| 函数 | 输入 | 输出 |
|---|---|---|
| `run_demand_case` | case | 解析后的 `Demand` + 字段检查 |
| `run_recommend_case` | case, catalog, demand | 预算/必含必排/账面闭合检查 + 人工复核材料 |
| `run_unsupported_case` | case | 表外品类识别与提示检查 |
| `run_knowledge_case` | case, index | 检索命中/类型/来源检查 |
| `run_compare_case` | case, catalog | 比较成功/差异维度检查 |
| `run_consistency_case` | case | 矛盾识别与不误报检查 |
| `run_claim_guard_case` | case | 无依据断言被丢弃检查 |
| `run_tool_case` | case, context | 工具调用成功/拒绝检查 |

需求类用例由调度器先调用 `run_demand_case` 解析一次，再把同一个 `Demand` 传给 `run_recommend_case`——**不重复解析**，否则两条检查可能看到不同状态。

替代方案：每个场景一个函数、需求与推荐合并。放弃合并，因为字段解析和推荐筛选是两类可独立失败的断言，合并后失败原因会糊在一起；放弃重复解析，因为会掩盖解析的非确定性。

### D4. 结果对象统一为 `Outcome`，报告对象统一为 `EvaluationReport`

`Outcome` 保存：用例 ID、类别、是否通过、逐项检查 `(名称, 是否通过, 说明)`、人工复核材料、错误信息、耗时。检查函数只返回结果，不打印、不写文件——这样测试可以直接断言对象。

`EvaluationReport` 是 `report.py` 的汇总对象，包含数据集元信息、检索模式、总览、结构化指标、分类汇总与逐条结果。Markdown、终端输出、JSON 三种渲染都从同一个对象出发，避免三套数字。

### D5. `report.json` 使用显式 schema 版本与输入指纹

```json
{
  "schema_version": 1,
  "generated_at": "2026-11-05T14:00:00+08:00",
  "dataset": {
    "name": "智购参谋效果评测集",
    "version": "2.0",
    "updated_at": "2026-10-15",
    "case_count": 41,
    "cases_sha256": "…",
    "products_sha256": "…"
  },
  "retrieval": {"mode": "bm25", "label": "BM25 本地关键词检索"},
  "summary": {"total": 41, "passed": 41, "failed": 0, "duration_ms": 1830},
  "metrics": [
    {
      "key": "demand_understanding",
      "label": "需求理解准确率",
      "definition": "分母＝标注了预期的字段数；分子＝解析结果与预期一致的字段数",
      "numerator": 25,
      "denominator": 25,
      "display": "25/25（100.0%）"
    }
  ],
  "manual_metrics": [
    {"name": "任务完成率", "definition": "…", "status": "尚未测量（需人工复核）"}
  ],
  "categories": [
    {"category": "工具调用", "total": 3, "passed": 3, "failed": 0}
  ],
  "outcomes": [
    {
      "id": "tool_001",
      "category": "工具调用",
      "passed": true,
      "duration_ms": 12,
      "checks": [{"name": "按预期成功", "ok": true, "detail": "…"}],
      "review": [],
      "error": ""
    }
  ]
}
```

三个关键点：

1. **指标不存格式化字符串作为唯一表示。** `numerator` / `denominator` 是结构化字段，`display` 只是渲染结果；分母为 0 时 `display` 为「不适用」，JSON 里不出现 0% 或编造的分母。
2. **记录两个输入指纹。** 页面重新计算当前 `cases.json` 与 `products.json` 的 SHA-256，与报告比对；不一致时提示「报告可能已过期」，而不是把旧数字当成当前结论。用哈希而不是文件 mtime，因为 git checkout 会重置 mtime。
3. **检索模式如实记录。** 当前 runner 只构建 BM25，报告就写 `bm25`；不写「向量检索」或「混合检索」这类没发生的事。将来接向量评测时扩展 `mode` 并保留旧值可读。

替代方案：沿用现有 `--json` 的 `{metrics, manual, outcomes}`。放弃，因为它没有版本与身份信息，页面无法判断报告是否对应当前数据；且 `metrics` 是给人读的字符串，无法稳定比较。该变化对仓外消费者是 breaking，仓内没有消费者，README 会注明新结构。

### D6. CLI 面保持旧旗标，新增目录输出

| 命令 | 行为 |
|---|---|
| `python scripts/evaluate.py` | 打印 Markdown 报告与汇总行（与现在一致） |
| `python scripts/evaluate.py --only 知识检索` | 只跑匹配类别 |
| `python scripts/evaluate.py --json` | 把完整 `report.json` 结构打到 stdout |
| `python scripts/evaluate.py --write docs/eval-report.md` | 把 Markdown 写到指定文件 |
| `python -m eval.runner --output-dir data/evaluation` | 写 `report.json` + `report.md` 到目录，并打印汇总 |

`--only` 无匹配时退出码 2，其余成功执行退出 0——即使有用例失败也返回 0，保持现有语义，避免把「评测发现问题」误当成「命令执行失败」。是否需要 `--fail-on-failure` 留给后续，不在本次范围。

### D7. 「效果评测」页只读报告，且有两道管理员守卫

- `app.py` 的 `NAV_ITEMS` 增加 `admin_only=True` 的入口，普通用户看不到。
- 页面入口再调用 `auth.require_admin(state.current_user())`，与 `admin.py` / `catalog_admin.py` 的做法一致——导航隐藏不是权限。
- 页面**不执行评测**。评测要跑完整推荐链路，放在 `st.rerun()` 驱动的页面里会导致每次交互阻塞数秒；页面只读 `config.eval_report_path()` 指向的 JSON。
- 报告缺失时用 `components.empty_state` + 生成命令；schema 版本未知时提示「报告格式与当前版本不匹配」并给命令，**不尝试猜字段**。
- 内容顺序：总览（用例数 / 通过 / 失败 / 耗时）→ 自动指标（定义、分母、实测值）→ 分类通过情况 → 失败明细 → 人工复核项（标「尚未测量」）→ 检索模式与生成时间 → 自评声明。

### D8. 报告解析放在 `eval/report.py`，页面保持薄

`load_report(path)` 负责读文件、校验 `schema_version`、返回 `LoadedReport`（报告对象或明确的错误原因），并计算「输入指纹是否仍匹配」。它是纯函数，不依赖 Streamlit，测试可以直接覆盖缺失文件、坏 JSON、旧 schema、哈希不匹配四种情况。

页面只负责把 `LoadedReport` 渲染成现有组件。这样 dashboard 的行为测试不需要启动 Streamlit 运行时，也避免把解析规则复制到界面层。

### D9. 测试策略：子集执行，断言语义而非时间戳

- runner 测试只跑 1–3 条用例（优先「工具调用」这类无需完整推荐链路的类别），避免测试套件被一次全量评测拖慢。
- 可复现性测试对同一子集连续跑两次，比较每条用例的 `passed` 与逐项 `(name, ok)`；**不比较** `generated_at` 和 `duration_ms`。
- 失败隔离用 monkeypatch 让某个检查函数抛异常，断言该条记为失败、其余用例仍有结果。
- 报告测试断言：schema 字段齐全、每个指标有 `numerator`/`denominator`、分母为 0 时 `display == "不适用"`、Markdown 与 JSON 的指标值一致、全文含「自评」。
- 页面测试覆盖：报告缺失、坏 JSON、未知 schema、指纹不匹配、正常报告五种分支。

## Risks / Trade-offs

- **`--json` 输出结构变化** → 仓内没有消费者；README 与 `docs/testing.md` 更新说明；旧旗标本身保留。若未来外部脚本依赖旧结构，可按 `schema_version` 适配。
- **报告文件被 `.gitignore` 忽略，克隆后页面为空** → 这是有意的：报告是本地生成物，提交它会让数字随生成时间漂移。空状态直接给出生成命令。
- **旧报告与当前数据不匹配** → 双哈希比对 + 页面提示「可能已过期」；仍展示旧报告，但明确标注生成时间与指纹不一致，不静默当成当前结论。
- **拆包后 Markdown 与 JSON 渲染不一致** → 两者都从 `EvaluationReport` 生成，指标只计算一次；测试断言同源值一致。
- **包名 `eval` 可能让人误以为可以动态执行代码** → 文档明确它是「evaluation」缩写；模块内不调用内置 `eval()`。
- **测试拖慢** → 只用子集，不跑完整评测；全量评测留给命令与文档生成。
- **页面展示报告后被误读为实时结果** → 固定展示生成时间、数据版本、检索模式和自评声明；过期时额外提示。

## Migration Plan

1. 新建 `eval/` 包并从 `scripts/evaluate.py` 搬运逻辑；把脚本改成包装器。先跑旧命令（默认、`--only`、`--json`、`--write`）确认行为与数字不变。
2. 增加 `--output-dir` 与 `report.json` 结构；用同一份结果生成 Markdown 与 JSON，比对指标一致。
3. 增加 `config.eval_report_path()`、`.gitignore` 规则和 dashboard 页面；用一份真实生成的报告验证页面，再验证缺失/坏文件/旧 schema 三种空状态。
4. 更新 README「测试与评估」与项目结构；用新渲染器重新生成 `docs/eval-report.md`，数字以实际运行为准。
5. 全量 `pytest` 与 `python scripts/evaluate.py` 通过后提交。

回滚：删除 `eval/` 与 dashboard 入口、恢复 `scripts/evaluate.py` 单文件版本即可；不涉及数据库迁移、不改变运行时数据，回滚无数据风险。

## Open Questions

- 是否需要在 CI 中让评测失败返回非零退出码？本次明确不做，等有 CI 流程后再定。
- 向量检索接入后如何在报告中表达 `mode` 的组合与回退？本次只记录当前实际使用的 BM25，未来变更单独设计。
