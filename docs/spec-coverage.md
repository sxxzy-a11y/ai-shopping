# 规格与测试追溯

项目的正式需求规格在 `openspec/specs/`，变更记录在 `openspec/changes/archive/`。这里说明规格和测试怎么对应，不再维护一份容易过期的手工矩阵。

## 怎么对应

1. 每个能力规格包含若干 Requirement 和 Scenario；
2. 场景对应的测试优先放在 `tests/` 下同名或相近的测试文件里；
3. 跑 `pytest` 验证行为；
4. 如果规格变化，先改规格，再改代码和测试；
5. 如果测试无法覆盖（例如浏览器样式、真实模型输出），在测试文档里注明“人工验证”，不要写成自动覆盖。

## 当前规格范围

`openspec/specs/` 覆盖：

- 商品目录与数据契约；
- 需求解析；
- 推荐与评分；
- 商品比较；
- 历史与收藏；
- 决策报告；
- 知识库；
- AI 增强；
- Agent 编排；
- 账号与权限；
- Web 界面；
- 效果评测。

具体条目以 `openspec/specs/` 下的文件为准。归档变更里有每次迭代的 proposal、design、specs 和 tasks，能看出某个功能为什么这样做、放弃了什么。

## 自动化测试

当前 1037 条测试，分布在 34 个测试文件。测试覆盖业务规则、数据层、界面、知识库、AI 降级、Agent 参数校验、权限边界和端到端流程。

测试分布和运行方式见 [testing.md](testing.md)。效果评测见 [eval-report.md](eval-report.md)。

## 不再维护手工矩阵的原因

早期版本有一份逐条 Scenario 对照表，把归档快照里的 99 个场景手工映射到测试函数。后来规格继续增加，矩阵没有同步，继续保留会让人误以为它覆盖了当前全部需求。

现在以规格文件和测试文件为准。需要追溯某个场景时，直接搜对应的测试名或 `openspec/specs/` 中的关键词，比维护一张手工表更可靠。

## 相关文档

- [requirements.md](requirements.md)
- [testing.md](testing.md)
- [architecture.md](architecture.md)
- [`openspec/specs/`](../openspec/specs/)
