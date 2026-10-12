# decision-report Specification

## Purpose
TBD - created by archiving change add-zhigou-mvp. Update Purpose after archive.
## Requirements
### Requirement: 决策报告内容组成

系统 SHALL 为每次分析生成一份消费决策报告，内容 SHALL 至少包含：用户需求摘要、预算与筛选条件、推荐商品及排序、推荐理由、各候选商品的优缺点、预算匹配情况、需要进一步核实的信息、最终决策建议。报告文案 SHALL 使用中文，SHALL NOT 使用与本次商品数据无关的通用套话。

#### Scenario: 报告包含全部必需小节

- **WHEN** 一次分析正常完成并生成报告
- **THEN** 报告包含需求摘要、筛选条件、推荐排序、推荐理由、优缺点、预算匹配、待核实项、最终建议八个部分

#### Scenario: 待核实项基于真实缺口生成

- **WHEN** 参与分析的商品数据中缺少某些参数或数据更新时间较早
- **THEN** 报告的待核实项列出这些具体缺口，而不是输出泛泛的免责声明

#### Scenario: 无推荐结果时报告说明原因

- **WHEN** 分析过程中没有任何商品匹配用户条件
- **THEN** 报告说明无匹配的原因与放宽条件建议，不生成虚假的推荐条目

### Requirement: 报告导出

系统 SHALL 支持将报告导出为 Markdown 或 CSV 文件供用户保存。导出内容 SHALL 与界面上展示的报告一致，SHALL NOT 在导出时丢失演示数据来源标注。

#### Scenario: 导出 Markdown

- **WHEN** 用户点击导出 Markdown
- **THEN** 系统生成可下载的 Markdown 文件，内容包含报告全部小节与数据来源说明

#### Scenario: 导出 CSV

- **WHEN** 用户点击导出 CSV
- **THEN** 系统生成包含推荐商品及其得分、价格、预算匹配状态的 CSV 文件，文件可被表格软件正常打开

#### Scenario: 导出失败时给出提示

- **WHEN** 报告导出过程中发生错误（如无写入权限）
- **THEN** 系统提示导出失败及可能原因，不展示 Python 异常堆栈

### Requirement: 报告的保存与再次打开

保存后的报告 SHALL 可以从历史记录中再次打开，再次打开时 SHALL 还原当时的推荐结果与得分，SHALL NOT 使用当前商品数据重新计算而覆盖历史结论。

#### Scenario: 历史报告还原原始结论

- **WHEN** 用户从历史记录中打开一份早先保存的报告
- **THEN** 展示的推荐商品、排序与得分与保存时一致

#### Scenario: 历史报告标注生成时间

- **WHEN** 用户打开历史报告
- **THEN** 报告显示该次分析的生成时间，用户可据此判断数据时效

### Requirement: 报告不得编造事实

报告中的价格、参数、销量、用户评价等事实性陈述 SHALL 全部来源于传入的商品数据。当数据不足时，报告 SHALL 明确说明信息不足并指出需要核实的内容，SHALL NOT 以推测值补充。

#### Scenario: 数据不足时明确说明

- **WHEN** 商品数据中不含销量信息而用户报告需要参考销量
- **THEN** 报告说明当前数据不含销量信息，建议用户另行核实，不给出具体销量数字

#### Scenario: 不使用未提供的数据背书推荐

- **WHEN** 生成推荐理由
- **THEN** 理由中的论据均可追溯到商品数据字段，不引入数据中不存在的事实

