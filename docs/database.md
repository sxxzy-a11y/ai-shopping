# 数据库设计

> **智购参谋 —— 基于 RAG 与 Agent 的智能消费决策助手**

**状态标记**：✅ 已实现 ｜ 🚧 开发中 ｜ 📋 规划中

---

## 1. 设计原则

| # | 原则 | 说明 |
|---|---|---|
| 1 | **先设计最小可用的数据模型** | 不要一开始建立几十张表 |
| 2 | **结构化字段与语义知识分开存放** | 价格、参数进关系库；商品介绍、选购指南进知识库 |
| 3 | **向量库不是关键业务字段的唯一数据源** | Chroma 只存用于语义检索的向量与元数据 |
| 4 | **报告以快照存储** | 商品数据更新后不改动历史结论 |
| 5 | **不用 ORM** | 表少，手写 SQL + 统一参数化查询更易维护 |

---

## 2. 目标数据模型 📋

```
                    ┌──────────────┐
                    │   products   │  商品主表
                    └──────┬───────┘
             ┌─────────────┼─────────────┬──────────────┐
             │             │             │              │
      ┌──────▼──────┐ ┌────▼─────┐ ┌─────▼────────┐ ┌───▼────┐
      │product_price│ │product_  │ │  knowledge_  │ │ data_  │
      │    s        │ │attributes│ │  documents   │ │sources │
      │  价格记录    │ │  参数表  │ │  知识文档     │ │ 来源表 │
      └─────────────┘ └──────────┘ └──────────────┘ └────────┘
             │
      ┌──────▼────────────────┐        ┌──────────────────────┐
      │recommendation_sessions│───────▶│recommendation_feedback│
      │      推荐会话          │        │       用户反馈         │
      └───────────────────────┘        └──────────────────────┘
```

### 2.1 表清单与状态

| # | 表 | 职责 | 状态 |
|---|---|---|---|
| 1 | `products` | 商品主表：ID、名称、品牌、品类、型号、描述、图片、状态 | 🚧 JSON 文件承载 |
| 2 | `product_prices` | 价格记录：商品 ID、价格、币种、来源、采集时间、有效状态 | 📋 |
| 3 | `product_attributes` | 参数表：商品 ID、参数名、值、单位、来源、核验状态 | 🚧 JSON 内嵌 `specs` |
| 4 | `data_sources` | 来源表：名称、URL、许可说明、获取时间、数据质量 | 📋 |
| 5 | `knowledge_documents` | 知识文档：ID、关联商品、类型、来源、版本、索引状态 | 📋 |
| 6 | `recommendation_sessions` | 推荐会话：需求、条件、候选、结果摘要、模型版本 | ✅ SQLite |
| 7 | `recommendation_feedback` | 用户反馈：会话 ID、反馈类型、评分或意见 | 📋 |

> **首个可运行版本只需优先完成 1–4 项。**
> 知识文档、推荐历史和反馈表可以随着功能逐步增加。

---

## 3. 当前实际表结构 ✅

现在有**两个 SQLite 库**，都由 `src/database.py` 用标准库 `sqlite3` 管理。

| 库 | 文件 | 内容 | 谁来写 |
|---|---|---|---|
| 商品库 | `storage/products.db` | `products` / `product_prices` / `dataset_meta` | 接入脚本、迁移脚本 |
| 历史库 | `storage/zhigou.db` | `analysis_history` / `favorites` | 应用运行时 |

**为什么分成两个文件**：共用一个文件时，文件一旦损坏，商品数据与历史会同时
读不出来，整个应用直接不可用；分开之后损坏是局部的——历史坏了仍能做分析，
商品库坏了历史仍在。这与「不因某一处失败而整体不可用」的既有立场一致。

### 3.1 商品库（`storage/products.db`）

```sql
CREATE TABLE IF NOT EXISTS products (
    product_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    brand        TEXT NOT NULL DEFAULT '',
    category     TEXT NOT NULL DEFAULT '',
    model        TEXT,                                -- 可空：服装家具没有型号概念
    specs        TEXT NOT NULL DEFAULT '{}',          -- JSON 列，按品类异构
    use_cases    TEXT NOT NULL DEFAULT '[]',
    pros         TEXT NOT NULL DEFAULT '[]',
    cons         TEXT NOT NULL DEFAULT '[]',
    data_source  TEXT NOT NULL DEFAULT '',
    source_url   TEXT,                                -- 可空：自造数据没有真实来源
    data_status  TEXT NOT NULL DEFAULT 'unverified',  -- verified / unverified
    updated_at   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS product_prices (
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

CREATE TABLE IF NOT EXISTS dataset_meta (      -- 数据集级说明：免责声明、档位说明
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
```

**三处值得说明的设计**：

1. **价格单独成表**：价格是最需要核实的字段，却曾经只是商品表上一个无来源、
   无时效的孤立数值。成表之后，重新录入变成「新增一条记录 + 旧的置为非当前」，
   历史不丢；没有价格记录时价格**视为缺失**，不默认符合预算。
2. **`specs` 保持 JSON 列不拆 EAV**：键按品类异构，消费方（`scoring`）本来就按
   dict 读，拆成三张表再拼回去收益为零。需要按参数做 SQL 级筛选时才是该拆的信号。
3. **`dataset_meta` 单独存**：免责声明这类整批数据共有的说明，不能留在种子文件里——
   种子删掉之后它不能跟着消失。

> ⚠️ **外键要显式开启**：SQLite 默认不启用外键约束，必须逐连接
> `PRAGMA foreign_keys = ON`，否则 `ON DELETE CASCADE` 只是一句摆设。
>
> ⚠️ **写入用 UPSERT 而不是 `INSERT OR REPLACE`**：后者在 SQLite 里是
> **先删后插**，会触发外键级联、把该商品的价格记录一起删掉，价格历史因此永远
> 累积不起来。这个坑实际踩过一次。

### 3.2 历史库（`storage/zhigou.db`）

```sql
-- 对应目标表 recommendation_sessions
CREATE TABLE IF NOT EXISTS analysis_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT    NOT NULL,
    demand_summary TEXT    NOT NULL,
    top_product    TEXT    NOT NULL DEFAULT '',
    top_score      REAL,
    result_count   INTEGER NOT NULL DEFAULT 0,
    report_json    TEXT    NOT NULL,   -- 报告整段 JSON 快照
    signature      TEXT                -- 条件指纹，跨会话去重
);

CREATE INDEX IF NOT EXISTS idx_history_created_at
    ON analysis_history (created_at DESC);

-- 同一组条件只存一条。
-- 部分索引让「老记录」（签名为 NULL）与「没算出签名的报告」互不冲突，
-- 升级老库时不会因为历史重复数据而失败。
CREATE UNIQUE INDEX IF NOT EXISTS idx_history_signature
    ON analysis_history (signature)
    WHERE signature IS NOT NULL;

-- 收藏（目标态 7 表中未列出，属于额外功能）
CREATE TABLE IF NOT EXISTS favorites (
    product_id TEXT PRIMARY KEY,
    added_at   TEXT NOT NULL
);
```

### 3.3 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | 自增主键 |
| `created_at` | TEXT | 本地时间字符串 |
| `demand_summary` | TEXT | 需求摘要，用于历史列表展示 |
| `top_product` | TEXT | 首推商品名（冗余字段，避免列表页解析整段 JSON） |
| `top_score` | REAL | 首推商品的匹配评分 |
| `result_count` | INTEGER | 结果数量 |
| `report_json` | TEXT | **完整 `DecisionReport` 的 JSON 快照** |
| `signature` | TEXT | 需求条件指纹，用于跨会话去重 |

### 3.4 为什么报告存 JSON 快照

需求要求「再次打开历史记录时还原当时的结论」。
如果用当前商品数据重算，**商品价格变了、参数改了、权重调了，
历史结论就会跟着变**——那就不叫历史记录了。

JSON 快照保证：**报告一旦生成，永久不变。**

### 3.5 为什么用部分唯一索引

普通的 `UNIQUE` 索引会把多个 `NULL` 视为互不相同（SQLite 语义），
但需求是「同一组条件只存一条」。部分索引 `WHERE signature IS NOT NULL`
额外解决了两个问题：

- 老版本写入的记录（`signature` 为 `NULL`）不会互相冲突
- 升级已有数据库时，不会因为历史中的重复数据而迁移失败

---

## 4. 目标表结构设计 📋

以下为迁移到 MySQL 时的目标 DDL。

### 4.1 `products` 商品主表

```sql
CREATE TABLE products (
    product_id   VARCHAR(32)  PRIMARY KEY,
    name         VARCHAR(255) NOT NULL,
    brand        VARCHAR(128) NOT NULL,
    category     VARCHAR(32)  NOT NULL,
    model        VARCHAR(128),
    description  TEXT,
    image_url    VARCHAR(512),
    data_status  VARCHAR(16)  NOT NULL DEFAULT 'pending',  -- verified / pending
    created_at   DATETIME     NOT NULL,
    updated_at   DATETIME     NOT NULL,
    INDEX idx_category (category),
    INDEX idx_brand (brand)
);
```

### 4.2 `product_prices` 价格记录

```sql
CREATE TABLE product_prices (
    id          BIGINT      PRIMARY KEY AUTO_INCREMENT,
    product_id  VARCHAR(32) NOT NULL,
    price       DECIMAL(10,2) NOT NULL,
    currency    CHAR(3)     NOT NULL DEFAULT 'CNY',
    source_id   BIGINT,
    collected_at DATETIME   NOT NULL,
    is_current  BOOLEAN     NOT NULL DEFAULT TRUE,
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    INDEX idx_product_current (product_id, is_current)
);
```

> **设计要点**：价格单独成表，既能保存**当前价格**，也能按需记录**历史价格**。
> 这是「价格必须有时效戳」这一需求的落点。

### 4.3 `product_attributes` 参数表

```sql
CREATE TABLE product_attributes (
    id          BIGINT      PRIMARY KEY AUTO_INCREMENT,
    product_id  VARCHAR(32) NOT NULL,
    attr_name   VARCHAR(64) NOT NULL,
    attr_value  VARCHAR(255),
    unit        VARCHAR(16),
    source_id   BIGINT,
    verify_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    UNIQUE KEY uk_product_attr (product_id, attr_name),
    INDEX idx_attr_name (attr_name)
);
```

> **为什么用 EAV（实体-属性-值）而不是宽表**：不同品类的参数完全不同——
> 笔记本有 `cpu_tier`，手机有 `chip_tier`/`camera_tier`，服饰有
> `comfort_tier`/`breathability_tier`。宽表会变成几十列且大部分为空。
>
> 当前实现用 JSON 内嵌 `specs` 达到同样效果，代价是无法用 SQL 直接
> 按参数筛选。演示规模下这个代价可接受。

### 4.4 `data_sources` 数据来源表

```sql
CREATE TABLE data_sources (
    id            BIGINT       PRIMARY KEY AUTO_INCREMENT,
    name          VARCHAR(255) NOT NULL,
    url           VARCHAR(512),
    license_note  TEXT,
    fetched_at    DATETIME,
    quality_note  TEXT
);
```

> ⚠️ **这张表是「创新点二」的前置条件。**
> 当前 112 条商品的 `data_source` 是同一串免责说明，
> 没有独立的来源表，也没有逐条 URL 与许可说明。

### 4.5 `knowledge_documents` 知识文档表

```sql
CREATE TABLE knowledge_documents (
    doc_id       BIGINT       PRIMARY KEY AUTO_INCREMENT,
    product_id   VARCHAR(32),           -- 品类级文档可为 NULL
    doc_type     VARCHAR(32)  NOT NULL, -- product / category / service
    source_id    BIGINT,
    content_version VARCHAR(32),
    index_status VARCHAR(16)  NOT NULL DEFAULT 'pending',
    updated_at   DATETIME     NOT NULL,
    FOREIGN KEY (source_id) REFERENCES data_sources(id),
    INDEX idx_product (product_id),
    INDEX idx_type (doc_type)
);
```

### 4.6 `recommendation_sessions` 推荐会话表

```sql
CREATE TABLE recommendation_sessions (
    session_id        VARCHAR(64) PRIMARY KEY,
    raw_demand        TEXT        NOT NULL,
    parsed_conditions JSON        NOT NULL,
    candidate_ids     JSON,
    result_summary    JSON,
    model_version     VARCHAR(64),
    created_at        DATETIME    NOT NULL,
    INDEX idx_created (created_at DESC)
);
```

### 4.7 `recommendation_feedback` 用户反馈表

```sql
CREATE TABLE recommendation_feedback (
    id          BIGINT      PRIMARY KEY AUTO_INCREMENT,
    session_id  VARCHAR(64) NOT NULL,
    feedback_type VARCHAR(32) NOT NULL,
    rating      TINYINT,
    comment     TEXT,
    created_at  DATETIME    NOT NULL,
    FOREIGN KEY (session_id) REFERENCES recommendation_sessions(session_id)
);
```

> 这张表是**推荐效果评估的数据来源**——没有它，「推荐相关性」
> 和「任务完成率」两个指标只能靠人工离线标注。

---

## 5. 存储分工 📋

| 数据类型 | 存储位置 | 原因 |
|---|---|---|
| 商品名称、品牌、价格 | MySQL | 精确查询和排序 |
| 规格参数 | MySQL | 条件过滤与比较 |
| 商品详细介绍 | MySQL 原文 + Chroma 索引 | 结构化管理与语义检索兼顾 |
| 选购指南 | 文档源文件 + Chroma 索引 | 便于检索和维护 |
| 知识来源与关联关系 | MySQL | 便于追溯和管理 |
| 推荐会话与反馈 | MySQL | 结构化记录和统计 |

> **Chroma 保存的是用于语义检索的向量及相关文档元数据。
> 它不应成为商品价格、库存等关键业务字段的唯一数据源。**

**动态字段（价格、库存）与语义知识必须分别管理**：
前者查询结构化数据，后者才走检索。RAG 对动态字段只能作为辅助参考。

---

## 6. 商品数据契约

`data/products.json` 是当前**唯一的数据契约**。接入真实平台数据
不需要改业务逻辑，只需产出同样结构的 JSON。

### 6.1 顶层结构

```json
{
  "dataset_name": "智购参谋演示数据集",
  "disclaimer": "本数据集全部为演示数据……",
  "updated_at": "2026-10-01",
  "spec_tier_note": "specs 中的档位字段……为本项目为规则评分设定的分类档位",
  "products": [ /* 见 6.2 */ ]
}
```

### 6.2 商品记录

```json
{
  "id": "LP001",
  "name": "轻羽 AirBook 14",
  "category": "laptop",
  "price": 3299,
  "brand": "轻羽",
  "specs": {
    "cpu": "R5-7530U",
    "cpu_tier": 3,
    "ram_gb": 16,
    "storage_gb": 512,
    "screen_size": 14,
    "weight_kg": 1.28,
    "battery_h": 10,
    "has_dedicated_gpu": false
  },
  "use_cases": ["编程", "办公", "学习", "通勤"],
  "pros": ["1.28kg 通勤背包不累", "…"],
  "cons": ["无独显，大型 3D 游戏性能不足", "…"],
  "data_source": "演示数据 · 本项目自行构造，非真实在售商品、非实时价格",
  "updated_at": "2026-10-01"
}
```

### 6.3 字段约束

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | 唯一标识，用于去重与关联 |
| `name` | ✅ | 商品名称 |
| `category` | ✅ | 必须在 `CATEGORY_LABELS` 中登记 |
| `price` | ✅ | 数值，用于预算筛选 |
| `brand` | ✅ | 品牌筛选 |
| `specs` | ✅ | 键按品类异构，档位字段取值 1–5 |
| `use_cases` | ✅ | 字符串数组 |
| `pros` / `cons` | ✅ | 字符串数组 |
| `data_source` | ✅ | 数据来源说明，**界面与导出报告都会展示** |
| `updated_at` | ✅ | 数据更新时间，**界面与导出报告都会展示** |

> **缺失字段的商品不会导致整批加载失败**：加载层逐条容错，
> 单条失败只降级该条并标记 `missing_fields`。

### 6.4 档位字段说明

`specs` 中的 `cpu_tier` / `chip_tier` / `camera_tier` / `audio_tier` /
`noise_level` / `energy_grade` / `durability_tier` / `comfort_tier` /
`breathability_tier` / `cushion_tier` 是**本项目为规则评分设定的分类档位**
（1 最低，5 最高），**不是厂商跑分或专业评测结果**。

---

## 7. 数据导入与更新

### 7.1 导入流程 ✅

```
CSV / Excel 原始商品表
        ↓
    数据清洗         去重、单位统一、字段校验、缺失值检查
        ↓
   写入数据库         商品信息、价格、参数、来源
        ↓
📋 生成知识文档并更新 RAG 索引
```

**幂等性**：导入程序可以重复运行而不会重复创建商品。
去重依据是**商品 ID**（或经确认的品牌 + 型号组合），
**不能只依赖商品名称**。

**写盘安全**：使用「临时文件 + 替换」策略，写入中断不会留下半个文件。

### 7.2 数据更新 🚧

比赛版使用静态数据，但必须有清晰的数据时效说明。后续可加定时更新任务：

1. 获取获得授权的数据源
2. 检查价格或参数是否发生变化
3. 更新数据库中的记录
4. 记录更新成功或失败状态
5. 对变化的商品重新生成知识文档或更新索引

> **不需要每次用户提问时重新爬取所有商品。**
> 当前已实现「数据刷新免重启」——数据集缓存键包含文件修改时间，
> 刷新数据后无需重启应用即可生效。

### 7.3 数据分层

| 层级 | 含义 |
|---|---|
| **原始数据** | 从来源收集的内容 |
| **规范化数据** | 统一单位、字段名和格式后的内容 |
| **核验状态** | 哪些数据已确认、哪些存在缺失 |
| **数据版本** | 导入和更新批次，便于追踪错误 |

---

## 8. 迁移路径

| 步骤 | 内容 | 风险 |
|---|---|---|
| 1 | 建立 MySQL 实例与连接配置 | 低 |
| 2 | 建 4 张核心表（`products` / `product_prices` / `product_attributes` / `data_sources`） | 低 |
| 3 | 写迁移脚本：JSON → MySQL，保留现有 `id` | 中（需校验条数与字段完整性） |
| 4 | `data_loader.py` 改为仓储模式，读 MySQL | 中 |
| 5 | 逐条补 `source_url` 与 `data_status` | **高（需要真实数据来源）** |
| 6 | 建 `knowledge_documents` 表并生成知识文档 | 高（依赖 RAG 开发） |

> **步骤 5 是真正的瓶颈**：没有真实数据来源，`data_sources` 表只能
> 存「本项目自行构造」这一条记录。补齐它是「创新点二」的前提。

---

## 9. 相关文档

| 文档 | 内容 |
|---|---|
| [requirements.md](requirements.md) | 需求规格说明书（含数据可追溯性 NFR-2） |
| [architecture.md](architecture.md) | 技术架构与设计决策 |
| [platform-integration.md](platform-integration.md) | 接入购物平台数据指南 |
| [data-disclaimer.md](data-disclaimer.md) | 数据说明与使用限制 |
