# 数据库说明

## 1. 两个数据库

系统运行时使用两个 SQLite 文件：

| 文件 | 内容 |
|---|---|
| `storage/products.db` | 商品、价格记录、数据集说明、分类和品牌元数据 |
| `storage/zhigou.db` | 账号、分析历史、收藏、个人偏好、知识向量 |

商品库和历史库分开，是为了让故障局部化：历史库损坏时仍能做商品分析，商品库损坏时历史报告仍可查看。

`data/products.json` 是种子数据，只在商品库为空时导入一次。运行时读取的是 SQLite，不是每次直接读 JSON。

## 2. 商品库

### 2.1 `products`

```sql
CREATE TABLE products (
    product_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    brand        TEXT NOT NULL DEFAULT '',
    category     TEXT NOT NULL DEFAULT '',
    model        TEXT,
    specs        TEXT NOT NULL DEFAULT '{}',
    use_cases    TEXT NOT NULL DEFAULT '[]',
    pros         TEXT NOT NULL DEFAULT '[]',
    cons         TEXT NOT NULL DEFAULT '[]',
    data_source  TEXT NOT NULL DEFAULT '',
    source_url   TEXT,
    image_url    TEXT,
    data_status  TEXT NOT NULL DEFAULT 'unverified',
    updated_at   TEXT NOT NULL DEFAULT '',
    is_active    INTEGER NOT NULL DEFAULT 1,
    entered_by   TEXT,
    entered_at   TEXT
);
```

字段说明：

| 字段 | 说明 |
|---|---|
| `product_id` | 商品唯一标识，推荐、比较、历史和收藏都用它关联 |
| `category` | 当前为 `laptop` 或 `phone`；分类展示名可被 `category_meta` 覆盖 |
| `specs` | JSON 文本，键按品类不同；档位字段为项目自定的 1–5 级 |
| `use_cases` | JSON 数组，如 `["办公", "学习"]` |
| `pros` / `cons` | JSON 数组，界面上作为优缺点展示 |
| `data_source` | 数据来源说明，界面和导出报告会展示 |
| `source_url` | 逐条来源链接，允许为空 |
| `image_url` | 外链图片；缺失或加载失败时界面回落类别图标 |
| `data_status` | `verified` 或 `unverified`；当前全部为 `unverified` |
| `is_active` | 是否启用；停用后不再进入推荐，但历史记录中的引用仍可读 |
| `entered_by` / `entered_at` | 管理员界面录入时的记录人和时间 |

### 2.2 `product_prices`

```sql
CREATE TABLE product_prices (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   TEXT NOT NULL,
    price        REAL NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'CNY',
    source_note  TEXT NOT NULL DEFAULT '',
    collected_at TEXT NOT NULL DEFAULT '',
    verified_at  TEXT,
    is_current   INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);
```

商品表里不再直接存价格。读取商品时，当前价格从 `product_prices` 中 `is_current = 1` 的记录派生；没有价格记录时价格为 `None`，筛选项会按“缺价格”处理，不默认符合预算。

价格单独成表的原因是历史价格和来源需要保留。重新录入价格时新增一条记录并把旧记录置为非当前，而不是覆盖原值。

### 2.3 元数据表

`dataset_meta` 保存整批数据的说明，例如免责声明和档位说明。它不随种子文件删除而消失。

`category_meta` 保存分类的展示名、排序和启停状态。新增分类可以先使用默认权重，之后在商品维护页补参数和知识指南。

`brand_meta` 保存品牌字典。品牌可以从商品数据自动同步，也可以先登记一个暂无商品的品牌。登记品牌不会让需求解析自动认识它，解析仍以商品数据为准。

## 3. 历史库

### 3.1 `users`

```sql
CREATE TABLE users (
    username      TEXT PRIMARY KEY,
    role          TEXT NOT NULL DEFAULT 'user',
    is_active     INTEGER NOT NULL DEFAULT 1,
    password_hash TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT ''
);
```

角色为 `admin` 或 `user`。密码使用 PBKDF2 加盐派生，格式为 `pbkdf2_sha256$迭代次数$盐$哈希`，不存明文。

账号表不采集邮箱、手机号、姓名、设备标识或地理位置。

### 3.2 `analysis_history`

```sql
CREATE TABLE analysis_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT    NOT NULL,
    demand_summary TEXT    NOT NULL,
    top_product    TEXT    NOT NULL DEFAULT '',
    top_score      REAL,
    result_count   INTEGER NOT NULL DEFAULT 0,
    report_json    TEXT    NOT NULL,
    signature      TEXT,
    user_id        TEXT
);
```

`report_json` 保存当时的完整报告快照。打开历史记录时直接读快照，不用当前商品数据重新计算。这样商品价格或参数更新后，旧报告的结论不会改变。

`signature` 是条件指纹，用于同一用户重复提交相同条件时去重；`user_id` 用于按用户隔离。单用户时期留下的记录没有归属，只对管理员可见。

### 3.3 `favorites`

```sql
CREATE TABLE favorites (
    user_id    TEXT,
    product_id TEXT NOT NULL,
    added_at   TEXT NOT NULL,
    PRIMARY KEY (user_id, product_id)
);
```

收藏按用户隔离。商品后来被停用或删除时，收藏记录可以保留，但界面会提示对应商品已不在当前数据集中。

### 3.4 `user_preferences` 与 `preference_template`

`user_preferences` 按用户名保存 AI 开关、价格取向、显示偏好等设置。

`preference_template` 只有一行，用于收编单用户时期的 `settings.json`，作为新用户的初始偏好模板。

### 3.5 `knowledge_vectors`

```sql
CREATE TABLE knowledge_vectors (
    doc_id       TEXT NOT NULL,
    slice_id     TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    heading      TEXT NOT NULL DEFAULT '',
    content      TEXT NOT NULL,
    doc_type     TEXT NOT NULL DEFAULT '',
    source       TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL DEFAULT '',
    product_id   TEXT NOT NULL DEFAULT '',
    model        TEXT NOT NULL,
    dim          INTEGER NOT NULL,
    embedding    TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    indexed_at   TEXT NOT NULL,
    PRIMARY KEY (doc_id, slice_id)
);
```

只有配置了 Embedding 服务并重建索引后，这张表才会有数据。未配置或检索失败时，知识库回退到 BM25，不依赖这张表。

## 4. 商品数据契约

`data/products.json` 是种子数据的结构约定。顶层包含：

```json
{
  "dataset_name": "智购参谋电子产品数据集",
  "disclaimer": "数据集说明",
  "updated_at": "2026-10-16",
  "spec_tier_note": "档位字段说明",
  "products": []
}
```

单条商品记录：

```json
{
  "id": "LP001",
  "name": "红米 REDMI Book 14 2025",
  "brand": "红米",
  "category": "laptop",
  "model": "REDMI Book 14 2025",
  "price": 3519,
  "specs": {
    "cpu": "酷睿5 220H",
    "cpu_tier": 4,
    "ram_gb": 16,
    "storage_gb": 1024,
    "screen_size": 14,
    "weight_kg": 1.36,
    "battery_h": 10,
    "has_dedicated_gpu": false
  },
  "use_cases": ["办公", "学习", "编程", "影音"],
  "pros": ["1.36kg、15.9mm 金属机身，便携性好"],
  "cons": ["仅 Intel 核芯显卡，无独立显卡"],
  "data_source": "公开资料整理 · 参数经简化，价格非实时",
  "source_url": "https://example.com/product",
  "image_url": "https://example.com/product.png",
  "data_status": "unverified",
  "updated_at": "2026-10-16"
}
```

必填字段：`id`、`name`、`brand`、`category`、`price`、`specs`、`use_cases`、`pros`、`cons`、`data_source`、`data_status`、`updated_at`。

`source_url`、`image_url` 和 `model` 允许为空。取不到来源时留空，不补一个打不开的链接。

单条商品缺字段时，加载层逐条容错并记录缺失字段，不会让整批数据失败。

## 5. 数据质量

当前 20 条商品：

- `data_status` 全部为 `unverified`；
- `source_url` 20/20 有值，但链接不等于已核验；
- 价格是参考价，不是实时价；
- 参数部分经过简化；
- 档位值是项目为评分设定的相对刻度，不是厂商跑分。

这些口径会显示在界面、导出报告和关于页，不能只在文档里写。

## 6. 写入与并发

商品库的写入入口在 `src/product_store.py` 和 `src/catalog_admin.py`。历史库的写入入口在 `src/database.py`。

约束：

- 所有 SQL 使用参数化查询；
- SQLite 连接显式开启外键；
- 账号删除时级联删除历史、收藏和偏好；
- 报告写入失败不应让已经显示的结果消失；
- 单实例部署，SQLite 不支持多副本并发写。

## 7. 未来迁移

如果要做长期多用户部署，建议按这个顺序迁移：

1. 建 PostgreSQL/MySQL 实例；
2. 迁移 `products`、`product_prices`、`category_meta`、`brand_meta`；
3. 迁移 `users`、`analysis_history`、`favorites`、`user_preferences`；
4. 把 `knowledge_vectors` 换成独立向量存储或 pgvector；
5. 把 `data_loader.py` 改成仓储模式，页面和评分逻辑不改；
6. 补备份、恢复和迁移脚本。

迁移不是当前演示版本的优先级。当前最需要补的是数据质量和评测，不是数据库规格。

## 8. 相关文档

- [architecture.md](architecture.md)
- [data-disclaimer.md](data-disclaimer.md)
- [platform-integration.md](platform-integration.md)
- [requirements.md](requirements.md)
