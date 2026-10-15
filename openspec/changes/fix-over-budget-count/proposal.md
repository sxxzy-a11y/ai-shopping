## Why

界面把**截断后的条数当成总数**显示，会让人对候选规模产生错误印象。

实测（预算 500 元找耳机）：

```
候选商品 16 件
  ├─ 预算内   6 件  → 界面显示「为你推荐 6」
  └─ 超预算  10 件  → 界面显示「超出预算的候选 6」   ← 少了 4 件，且没有任何说明
```

账面也对不上：`6 + 6 = 12 ≠ 16`。用户看到「超出预算的候选 6」会以为一共只有 6 件超预算。

**根因**：`recommend()` 里两处用了同一个 `limit`：

```python
within_budget=within[:limit],
over_budget=over[:limit],      # ← 这个 limit 的文档写的是「预算内推荐条数上限」
```

查过归档的提案、设计、任务——**从没提过超预算列表要限条数**。这不是设计决策，
是复用参数带出来的意外后果。

**它是怎么产生的**：`limit` 的语义是「预算内推荐条数上限」（`recommend()` 的
docstring 原文），作用在超预算列表上属于越界使用。更糟的是界面直接把
`len(result.over_budget)` 当总数展示，把「截断」这件事完全抹掉了。

## What Changes

- **截断与否要如实反映在数字上**
  - `RecommendationResult` 增加 `over_budget_total`：**截断前**的真实条数
  - 界面展示的条数一律用真实总数，不用列表长度

- **超预算列表用**独立**的上限，不与「预算内推荐条数」共用**
  - 新增 `config.MAX_OVER_BUDGET_SHOWN`（默认 10）
  - `limit` 回归它文档里写的语义：只管预算内推荐条数

- **截断了就说清楚**
  - 展示的条数少于真实总数时，界面明确说明「另有 N 件超出更多未列出」，
    并说明列出的规则（按需求匹配度排序的前 N 件）

- **不做的**：不改评分与排序逻辑；不改超预算商品的标注方式（超出金额照旧逐条标）；
  不改比较页与报告里已经正确的部分。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `recommendation-engine`: 「预算过滤与超预算商品显式标注」需求增加两条约束——
  展示的条数须为真实总数；只展示一部分时须说明还有多少未展示。

## Impact

**代码**

| 文件 | 改动 |
|---|---|
| `src/recommender.py` | `RecommendationResult` 增加 `over_budget_total`；`over_budget` 改用独立上限 |
| `src/config.py` | 新增 `MAX_OVER_BUDGET_SHOWN` |
| `src/ui/pages/analysis.py` | 条数用真实总数，截断时补说明 |
| `src/report_service.py` | 报告与导出同样用真实总数并带上说明 |

**测试**

- `tests/test_recommender.py`：超预算条数与真实总数一致；独立上限生效；`limit` 不再影响超预算列表
- `tests/test_app.py`：界面展示真实总数；截断时有说明文案
- `tests/test_report_service.py`：导出同样如实

**风险**

- **列表可能变长**：无类别限制且预算很低时，超预算候选可能很多。用独立上限（10）挡住，
  同时把真实总数告知用户——**能看全与看得清之间，选「说清楚」**。
- **报告快照的字段变化**：`over_budget_total` 有默认值，老的历史报告仍能打开。
