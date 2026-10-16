# 接入购物平台数据指南

本文说明如何把真实购物平台的数据接进本项目。**应用本身不需要改**——
所有业务逻辑都通过**商品数据库**这一份数据契约工作，
只要落库的记录结构一致，筛选、评分、比较、界面自动适配。

> 商品数据存在 `storage/products.db` 里。`data/products.json` 已经**降级为种子数据**：
> 只在库为空时被导入一次，不再参与运行时读取。

---

## 1. 流程总览

```
平台 API / CSV 导出
        │
        ▼
scripts/fetch_products.py      ← 取数（HTTP、读文件）
        │  原始记录（字段名随平台）
        ▼
src/ingest.py                  ← 转换（字段映射、档位折算、类目归一）
        │  内部商品结构
        ▼
写前严格校验                    ← 不合格就不写库
        │
        ▼
storage/products.db            ← 应用读取的唯一入口
  ├── products                 商品记录
  ├── product_prices           价格记录（价格单独成表，带来源与采集时间）
  └── dataset_meta             数据集级说明（免责声明、档位说明、抓取时间）
```

- 取数与转换分离：转换规则可以脱离网络做单元测试
- **写库前严格校验**：坏数据不落库（与读取端的宽容策略刻意相反）
- 主键保证去重：同 ID 覆盖而不新增，导入可重复执行
- 价格**变了才新增记录**、旧的置为非当前——价格历史因此可追溯

---

## 2. 快速跑通（CSV 通道，不需要任何平台账号）

```bash
# 1) 生成列名模板
python scripts/fetch_products.py --write-template data/platform_export.csv

# 2) 把模板改成你平台导出的结构，然后先空跑看报告
python scripts/fetch_products.py --source csv --input data/platform_export.csv --dry-run

# 3) 确认无误后写入（merge：同 id 覆盖，新 id 追加，其余保留）
python scripts/fetch_products.py --source csv --input data/platform_export.csv
```

**列名不要求固定**。脚本按别名表识别（见 `src/ingest.py` 的
`_FIELD_ALIASES`），常见的「商品ID / 标题 / 价格 / 类目 / 品牌 / 参数」
都能直接认。新平台第一次接入时，把它的列名补进别名表即可。

「参数」列支持三种写法：

- JSON 对象：`{"内存": 16, "屏幕尺寸": 14}`
- 文本：`内存: 16; 屏幕尺寸: 14`
- 留空

---

## 3. 接入真实 API

`scripts/fetch_products.py` 里的 `ApiSource` 是一个骨架，
典型的分页 JSON 接口只需要改三个「接入点」：

| 接入点 | 位置 | 要做什么 |
|---|---|---|
| 鉴权 | `ApiSource._headers()` | 改成平台的 AppKey / 签名 / Token 方式 |
| 分页 | `ApiSource._params()` | 改成平台的页码、offset 或 cursor 协议 |
| 结构 | `ApiSource._extract_items()` | 按平台的返回包装取商品数组 |

其余流程（转换、校验、合并、写库）都无需改动。

### 环境变量

| 变量 | 说明 |
|---|---|
| `ZHIGOU_PLATFORM_BASE_URL` | 平台接口根地址，如 `https://open.example.com` |
| `ZHIGOU_PLATFORM_API_KEY` | 平台密钥。**只从环境变量读，不写进代码** |
| `ZHIGOU_PLATFORM_SOURCE_LABEL` | 数据来源标注，会盖进每条商品的 `data_source` |

```bash
python scripts/fetch_products.py --source api --mode replace
```

---

## 4. 字段映射规则

### 4.1 类目

平台的类目名映射到内部类别键，配置在 `src/ingest.py` 的
`DEFAULT_CATEGORY_MAP`。匹配顺序：精确 → 包含 → 内部类别中文名包含。

**商品库当前只覆盖两个电子产品类**：笔记本电脑（`laptop`）、手机（`phone`）。
平台类目对不上时有两种处理：

- 映射到已有的两类之一（推荐，评分维度现成）
- 新增一个品类：在 `src/config.py` 登记 `CATEGORY_LABELS` 与
  `SCORING_WEIGHTS`，再指明它的参数范围（`src/scoring.py` 的
  `_SPEC_RANGES` / `_PERFORMANCE_SPECS`）。比较表会自动带上该类别的参数

### 4.2 参数（specs）

平台参数名 → 内部参数键，配置在 `SPEC_ALIASES`。两个要点：

1. **未登记的键原样保留**——比较表能显示，只是没有中文标签。
   宁可先少映射，也不要乱映射
2. **档位要折算**。项目内部用 1–5 档（5 最高），而平台给的往往是
   「8/10 分」「一级」这类原始表述：
   - `to_tier(8, scale_max=10)` → `4`（满分 10 分制折算到 1–5）
   - `parse_energy_grade("一级")` → `5`（「一级/二级」这类分等级表述同样换算到 1–5）
   - 新品类要补同类折算函数，并加到 `TIER_KEYS`

### 4.3 价格

`parse_price()` 能处理 `￥2,999.00`、`2999元` 这类文本；
解析不出来会**报错并拒绝写库**，不会把坏价格写进数据。

---

## 5. 合并策略

| 模式 | 行为 | 适用场景 |
|---|---|---|
| `merge`（默认） | 同 id 覆盖；新 id 追加；未抓到的老商品保留 | 增量更新、平台只返回部分商品 |
| `replace` | 完全用新数据替换 | 全量抓取 |

---

## 6. 定期刷新

真实价格会变，建议用系统计划任务定期重跑：

```bash
# Windows：任务计划程序里安排每天执行
python scripts/fetch_products.py --source api --mode replace
```

注意事项：

- **刷新后无需重启应用**：应用按「路径 + 文件修改时间」缓存数据集，
  脚本写完商品库后，运行中的界面下一次操作就会加载新数据（缓存盯着库文件的修改时间）
- **限流**：平台的调用频次限制要留余量，加缓存与退避重试
- **失败不破坏现状**：校验不过时脚本直接退出且不写文件，
  旧数据集保持可用——这正是「写前校验 + 临时文件替换」的目的
- **保留快照**（可选）：需要追溯价格历史时，把每次产物按日期另存一份

---

## 7. 从整理数据再切到平台实时数据时，必须同步的事

当前数据集是「真实品牌 + 依公开资料整理的参数与参考价」。若要进一步换成
**平台实时数据**，以下四件事要一并处理：

1. **真实性标注**：`data_source` 由脚本统一盖章为「来自XX平台 · 抓取于某日」。
   **不允许**把平台营销文案当作用户评价，也不允许把未核验的数据说成已核验
2. **更新测试断言**：`tests/test_data_loader.py` 与 `tests/test_acceptance.py`
   现在守的是「每条商品有来源说明、且标注未核验」（`data_status` 字段），
   切到实时数据后需要同步修改——例如把核验状态改成 `verified` 的条件
3. **核对评分口径**：平台参数的量纲可能与当前整理数据不同，
   `src/scoring.py` 的 `_SPEC_RANGES` 需要按实际量纲校准
4. **免责声明**：`docs/data-disclaimer.md` 与界面文案中关于
   「公开资料整理 · 价格非实时」的表述，需要按实际情况改写

---

## 8. 可直接跑的命令速查

```bash
# 生成模板
python scripts/fetch_products.py --write-template data/platform_export.csv

# 空跑（只转换与校验）
python scripts/fetch_products.py --source csv --input data/platform_export.csv --dry-run

# 正式写入（合并）
python scripts/fetch_products.py --source csv --input data/platform_export.csv

# 只处理前 20 条（调试）
python scripts/fetch_products.py --source csv --input data/platform_export.csv --limit 20 --dry-run

# API 模式（需先配好环境变量）
python scripts/fetch_products.py --source api --mode replace

# 跑接入层的测试
pytest tests/test_ingest.py
```
