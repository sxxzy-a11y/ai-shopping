# product-catalog Specification

## Purpose
TBD - created by archiving change add-zhigou-mvp. Update Purpose after archive.
## Requirements
### Requirement: 商品数据结构与必填字段

系统 SHALL 用统一的数据结构描述每件商品，字段包含：商品 ID、商品名称、商品类别、参考价格、品牌、核心参数、适用场景、优点、缺点、数据来源说明、数据更新时间。系统 SHALL 在加载时校验上述字段的存在性，并对缺失字段的商品记录给出明确处理结果。

#### Scenario: 字段完整的商品被正常加载

- **WHEN** 数据文件中存在一条包含全部必填字段的商品记录
- **THEN** 该商品可被加载并参与后续筛选与评分

#### Scenario: 缺失核心参数的商品不导致崩溃

- **WHEN** 数据文件中某条商品记录缺少「核心参数」字段
- **THEN** 系统正常加载其余商品，在结果中明确标记该商品信息不完整，且筛选与比较流程继续可用

### Requirement: 数据集规模与类别覆盖

系统 SHALL 在 `data/products.json` 中提供不少于 20 条彼此有差异的模拟商品记录，类别 SHALL 至少覆盖笔记本电脑、手机、耳机、键盘。

#### Scenario: 数据集满足规模要求

- **WHEN** 应用启动并加载 `data/products.json`
- **THEN** 可用商品总数不少于 20，且笔记本、手机、耳机、键盘四个类别均有商品

#### Scenario: 商品之间具有可区分差异

- **WHEN** 检查同一类别下的商品记录
- **THEN** 各商品在价格、品牌、核心参数上存在差异，不存在仅名称不同的重复条目

### Requirement: 模拟数据的溯源标注

每一条模拟商品记录 SHALL 带有明确标注其为演示数据的来源说明与数据更新时间。系统 SHALL NOT 将模拟数据呈现为真实在售商品、真实用户评价或实时市场价格。界面展示商品信息时 SHALL 同时展示该溯源标注。

#### Scenario: 商品卡片显示演示数据标识

- **WHEN** 用户查看任意商品的详情或卡片
- **THEN** 卡片上显示该数据的来源说明与更新时间，且来源说明中明确包含这是演示数据的表述

#### Scenario: 报告与导出结果保留标注

- **WHEN** 用户导出决策报告为 Markdown 或 CSV
- **THEN** 导出内容中包含演示数据来源说明，不将模拟数据表述为实时价格或真实评价

### Requirement: 数据文件缺失或损坏的容错

当 `data/products.json` 不存在、无法解析或结构非法时，系统 SHALL 给出中文错误提示，说明期望的文件路径与格式。系统 SHALL NOT 崩溃，SHALL NOT 向前端暴露堆栈，也 SHALL NOT 静默返回零条商品的空结果而不作说明。

#### Scenario: 数据文件不存在

- **WHEN** `data/products.json` 被删除后启动应用
- **THEN** 界面提示商品数据文件缺失及其预期路径，应用其余部分仍可打开

#### Scenario: 数据文件内容非法

- **WHEN** `data/products.json` 内容为非法 JSON
- **THEN** 界面提示数据解析失败并指明出错文件，不显示 Python 异常堆栈

#### Scenario: 数据文件为空列表

- **WHEN** `data/products.json` 内容为合法 JSON 但商品数组为空
- **THEN** 界面明确提示当前无可用于分析的商品数据，而不是显示一个空白结果页

### Requirement: 商品数据与页面代码分离

商品数据 SHALL 存放于独立的 JSON 或 CSV 文件中。系统 SHALL NOT 将商品数据硬编码在页面代码或业务模块的源码中。

#### Scenario: 修改数据文件即刻生效

- **WHEN** 在 `data/products.json` 中新增一条商品记录后重新运行应用
- **THEN** 新增商品出现在可选商品集合中，期间未修改任何 Python 源码

