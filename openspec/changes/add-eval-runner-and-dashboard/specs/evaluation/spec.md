## MODIFIED Requirements

### Requirement: 评测脚本的执行

系统 SHALL 提供一个可独立测试的评测 runner，把评测集逐条跑过真实链路并输出结果；原 `scripts/evaluate.py` SHALL 保留为兼容入口，原有 `--only` / `--json` / `--write` 命令 MUST 继续可用。

runner SHALL 只通过**公开入口**调用被测能力（需求解析、筛选推荐、知识检索、编排），SHALL NOT 读取被测模块的内部状态——否则等于自己测自己。

runner SHALL 支持按场景类别筛选执行，并 SHALL 在任一条用例执行失败时继续跑完其余用例，而不是中断。runner SHALL 记录每条用例的执行耗时与整次运行的总耗时。

同一份评测集、同一份商品数据与同一检索模式下，runner SHALL 产生相同的逐条通过情况与指标值；生成时间与耗时属于运行元数据，不参与结果一致性判定。

#### Scenario: 脚本跑完整链路

- **WHEN** 运行评测 runner
- **THEN** 逐条执行评测集并输出每条的实际结果与预期结果的比对

#### Scenario: 单条失败不中断整体

- **WHEN** 某条用例执行时抛出异常
- **THEN** 该条记为失败并附上原因，其余用例继续执行

#### Scenario: 可按类别执行

- **WHEN** 指定只跑某一场景类别
- **THEN** runner 只执行该类别的用例并输出对应结果

#### Scenario: 旧命令继续可用

- **WHEN** 使用 `python scripts/evaluate.py --only 知识检索` 或原有 `--json` / `--write` 旗标
- **THEN** 命令仍可执行，输出内容与新的 runner 一致，不因拆分而失效

#### Scenario: 重复执行结果一致

- **WHEN** 用同一份评测集与商品数据连续运行两次
- **THEN** 每条用例的通过状态与逐项检查结果一致，不受生成时间影响

#### Scenario: 记录执行耗时

- **WHEN** 完成一次评测运行
- **THEN** 报告中包含每条用例的耗时与整次运行的总耗时

## ADDED Requirements

### Requirement: 机器可读的评测报告

runner SHALL 产出结构化的评测报告，供界面或其它程序读取。报告 MUST 包含：schema 版本、生成时间、评测集名称/版本/更新时间/用例数、检索模式、总用例数与通过失败数、结构化指标、分类汇总、逐条用例结果。

每个自动指标 MUST 以 `numerator` / `denominator` 结构化字段表示，并附带定义与展示文本；系统 SHALL NOT 只存一个格式化后的字符串作为唯一表示。分母为零时 MUST 标记为「不适用」，SHALL NOT 输出 0% 或编造分母。

需人工复核的指标 MUST 在报告中标注为「尚未测量」，SHALL NOT 由 runner 填入推算值。报告 SHALL NOT 出现综合总分。

同一份运行结果生成的 JSON 报告与 Markdown 报告 MUST 使用同一组指标值，SHALL NOT 各自计算。

#### Scenario: 写出结构化报告

- **WHEN** 以目录输出模式运行 runner
- **THEN** 目标目录内生成 `report.json` 与 `report.md`，两者来自同一次运行

#### Scenario: 指标带分子分母

- **WHEN** 读取报告中的任一自动指标
- **THEN** 可以同时看到分子、分母、定义与展示文本

#### Scenario: 分母为零

- **WHEN** 某指标没有可判定的检查项
- **THEN** 报告中该指标标记为「不适用」，不出现 0% 或推测值

#### Scenario: 人工指标不冒充测量结果

- **WHEN** 查看需人工复核的指标
- **THEN** 报告中标注「尚未测量（需人工复核）」，并附上复核材料而非结论

#### Scenario: 两种格式数字一致

- **WHEN** 对照同一次运行的 `report.json` 与 `report.md`
- **THEN** 每个自动指标的分子、分母与展示值一致

### Requirement: 报告与输入数据的一致性

评测报告 SHALL 记录生成时所用评测集与商品数据的 SHA-256 指纹，使读取方能够判断报告是否仍对应当前输入。

系统 SHALL 允许读取方重新计算当前输入的指纹并与报告比对；比对不一致时 SHALL 能识别为「报告可能已过期」。系统 SHALL NOT 仅依赖文件修改时间判断过期，因为版本控制检出会重置该时间。

#### Scenario: 报告记录输入指纹

- **WHEN** runner 生成报告
- **THEN** 报告包含评测集文件与商品数据文件的 SHA-256 指纹

#### Scenario: 输入变化可被发现

- **WHEN** 评测集或商品数据在报告生成后发生变化
- **THEN** 重新计算的指纹与报告中的指纹不同，读取方可以提示报告可能已过期
