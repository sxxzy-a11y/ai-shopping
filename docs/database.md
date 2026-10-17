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
| 1 | `products` | 商品主表：ID、名称、品牌、品类、型号、描述、图片、来源、核验状态 | ✅ SQLite 商品库 |
| 2 | `product_prices` | 价格记录：商品 ID、价格、币种、来源、采集时间、有效状态 | 📋 |
| 3 | `product_attributes` | 参数表：商品 ID、参数名、值、单位、来源、核验状态 | ✅ SQLite 内嵌 `specs`（JSON 列） |
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
    model        TEXT,                                -- 可空：字段可选，当前 20 条均已填
    specs        TEXT NOT NULL DEFAULT '{}',          -- JSON 列，按品类异构
    use_cases    TEXT NOT NULL DEFAULT '[]',
    pros         TEXT NOT NULL DEFAULT '[]',
    cons         TEXT NOT NULL DEFAULT '[]',
    data_source  TEXT NOT NULL DEFAULT '',
    source_url   TEXT,                                -- 可空：取不到来源时留空
    image_url    TEXT,                                -- 可空：外链图片，挂了由界面回落类别图标
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
-- 账号。字段刻意只有这些：用户名、角色、状态、凭据、创建时间。
-- 没有邮箱/手机号/姓名——本应用不需要它们，收了也只是白拿用户信息。
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    role          TEXT    NOT NULL DEFAULT 'user',   -- admin / user
    is_active     INTEGER NOT NULL DEFAULT 1,
    password_hash TEXT    NOT NULL DEFAULT '',       -- pbkdf2 自描述串
    created_at    TEXT    NOT NULL DEFAULT ''
);

-- 对应目标表 recommendation_sessions
CREATE TABLE IF NOT EXISTS analysis_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT    NOT NULL,
    demand_summary TEXT    NOT NULL,
    top_product    TEXT    NOT NULL DEFAULT '',
    top_score      REAL,
    result_count   INTEGER NOT NULL DEFAULT 0,
    report_json    TEXT    NOT NULL,   -- 报告整段 JSON 快照
    signature      TEXT,               -- 条件指纹，**按用户**去重
    user_id        TEXT                -- 归属账号；遗留记录为空
);

CREATE INDEX IF NOT EXISTS idx_history_created_at
    ON analysis_history (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_history_user
    ON analysis_history (user_id, created_at DESC);

-- 同一组条件**在同一用户下**只存一条。
-- 部分索引让「老记录」（签名为 NULL、或归属为 NULL）与「没算出签名的报告」
-- 互不冲突，升级老库时不会因为历史重复数据而失败。
CREATE UNIQUE INDEX IF NOT EXISTS idx_history_signature
    ON analysis_history (user_id, signature)
    WHERE signature IS NOT NULL AND user_id IS NOT NULL;

-- 收藏：主键带上用户。旧形态是 product_id 单列主键，
-- 那意味着**全站只能有一个人收藏某件商品**。
CREATE TABLE IF NOT EXISTS favorites (
    user_id    TEXT,                   -- 可空仅对遗留收藏有意义
    product_id TEXT NOT NULL,
    added_at   TEXT NOT NULL,
    PRIMARY KEY (user_id, product_id)
);

-- 偏好按用户存（原先是全局的 storage/settings.json）
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id    TEXT PRIMARY KEY,
    prefs_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT ''
);

-- 单用户时期那份 settings.json 的归宿：新用户的初始偏好模板
CREATE TABLE IF NOT EXISTS preference_template (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    prefs_json TEXT NOT NULL DEFAULT '{}'
);
```

### 3.2.1 三处必须知道的改动理由

| 改动 | 不改会怎样 |
|---|---|
| 签名唯一索引加上 `user_id` | 旧索引是全局 `(signature)` 唯一。李四提交与张三完全相同的条件时，`save_analysis` 的去重查询会命中张三那条，把**张三的记录 ID 返回给李四**——不报错、不崩溃，只是把别人的报告当成自己的给出去 |
| `favorites` 主键改成 `(user_id, product_id)` | 旧主键下，第二个人点收藏是**覆盖**第一个人那条，两个人共用一条记录 |
| 偏好从全局文件搬进按用户的表 | 一份全局偏好意味着李四的分析会被张三的设置影响——这不是「功能缺失」，是**一个人的设置作用在另一个人身上** |

### 3.2.2 从单用户库升级（迁移）

`_migrate()` 是幂等的，每次建表都会跑一遍。顺序与要点：

1. **迁移前先备份** `zhigou.db` → `zhigou.db.bak-<日期>`（只在真的需要迁移时）
2. `users` 建表；`analysis_history` 补 `signature` 与 `user_id` 两列（可空）
3. `favorites` 重建：建新表 → 搬数据 → 删旧 → 改名（SQLite 改不了主键）
4. 删掉全局的旧签名索引，按 `(user_id, signature)` 重建
5. 单用户时期的 `settings.json`：内容写进 `preference_template`，文件改名 `.bak`

**遗留数据一律标为无归属，只对管理员可见。** 系统不把它们划给任何账号——
那份数据是谁产生的我们并不知道，编一个归属不如如实留空。

> ⚠️ **整段迁移必须在一个显式事务里。** Python 的 `sqlite3` 只在 DML
> （INSERT/UPDATE/DELETE）前隐式开事务，`ALTER TABLE` / `CREATE INDEX`
> 各自自动提交——不写 `BEGIN` 的话，中途失败时表已经被改掉了，
> 而 `rollback()` 无事可回滚。这个坑由「迁移中途失败」那条用例逮住过。
>
> ⚠️ **索引不能建在补列之前。** 建表脚本先于 `_migrate` 执行，而
> `CREATE TABLE IF NOT EXISTS` 对老表是空操作——紧跟其后的
> `CREATE INDEX ... (user_id, ...)` 会以 `no such column: user_id` 直接失败。

### 3.2.3 删除账号时的级联

`database.delete_user()` 在**一个事务**里依次删四张表：

```
analysis_history  WHERE user_id = ?
favorites         WHERE user_id = ?
user_preferences  WHERE user_id = ?
users             WHERE username = ?
```

**为什么不用外键 `ON DELETE CASCADE`**：这三张表的 `user_id` 都是普通 TEXT 列，
**没有被 `FOREIGN KEY` 约束住**。想享受级联删除就得先给它们加上外键，
而 SQLite 改不了已有表的约束——只能重建表。为了让库替我们删三行而重建三张表，
代价远大于写四条 DELETE。

**为什么必须在一个事务里**：删了历史却没删掉账号（或反过来）会留下**半删状态**——
账号没了数据还在，或者数据没了账号还在。这类中间态最难排查。

> ⚠️ 这里**不需要**显式 `BEGIN`，而迁移那段需要。区别在语句类型：
> `DELETE` 是 DML，Python 的 `sqlite3` 会在第一条 DML 之前隐式开启事务；
> 而 `ALTER TABLE` / `CREATE INDEX` 是 DDL，**不会**自动开事务。
> 两处写法不同不是疏忽。

删除记录（`delete_analysis`）只动 `analysis_history` 一行，同样在一个事务里；
归属校验（本人或管理员）在数据层入口，界面上的判断只是提示。

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
| `signature` | TEXT | 需求条件指纹，**按用户**去重 |
| `user_id` | TEXT | 归属账号。单用户时期的遗留记录为空，只对管理员可见 |

`users` 表的字段：

| 字段 | 说明 |
|---|---|
| `username` | 主键，登录名 |
| `role` | `admin`（管理员）/ `user`（普通用户） |
| `is_active` | 停用的账号不能登录，其历史数据仍在 |
| `password_hash` | `pbkdf2_sha256$<迭代>$<盐>$<哈希>`，**绝不是明文** |
| `created_at` | 创建时间 |

### 3.3.1 商品库新增的两张元数据表

```sql
-- 分类元数据。**只放既有分类的覆盖项**，全集永远是 config.CATEGORY_LABELS。
CREATE TABLE IF NOT EXISTS category_meta (
    category_key  TEXT PRIMARY KEY,
    display_label TEXT,                       -- 空则用配置里的默认名
    sort_order    INTEGER NOT NULL DEFAULT 0,
    is_active     INTEGER NOT NULL DEFAULT 1,
    updated_by    TEXT,
    updated_at    TEXT
);

-- 品牌字典。键是**商品里的写法**，与商品表对得上。
CREATE TABLE IF NOT EXISTS brand_meta (
    brand_name   TEXT PRIMARY KEY,
    display_name TEXT,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    is_active    INTEGER NOT NULL DEFAULT 1,
    entered_by   TEXT,
    entered_at   TEXT
);
```

**为什么分类元数据是「叠加层」而不是「分类表」**：新增一个分类要同时配评分
权重、参数档位与知识指南——那是改代码与语料的工作量，不是一次点击。
做成可增删的表，只会让系统进入「配置不完整」的状态：推荐缺权重、
问答缺资料，而且不报错，只是结果悄悄变差。

`products` 表同时新增了 `is_active`（上下架）与 `entered_by` / `entered_at`
（界面录入者与时间，命令行为空）。**停用分类或品牌、下架商品都只是读取时
过滤，不改写任何商品行**——否则恢复时无法区分「管理员当初手工下架的」与
「因分类停用而被下架的」。

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
> 笔记本有 `cpu_tier`，手机有 `chip_tier`/`camera_tier`。宽表会变成几十列且大部分为空。
>
> 当前实现用 JSON 内嵌 `specs` 达到同样效果，代价是无法用 SQL 直接
> 按参数筛选。当前规模下这个代价可接受。

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
> 当前 20 条商品的 `data_source` 统一为「公开资料整理 · 参数经简化，价格非实时」，
> 且 20 条全部带 `source_url`，
> 但**没有独立的来源表**，也没有逐条许可说明——离「逐条可追溯」仍差一张表。

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
  "dataset_name": "智购参谋电子产品数据集",
  "disclaimer": "本数据集覆盖笔记本电脑、手机两类电子产品。品牌与型号真实存在，参考价与参数依据公开资料整理而成：价格是整理时的参考价、不是实时价格，会随促销波动；参数经过简化。适用场景与优缺点由本项目依据参数整理。全部记录标注为未核验。",
  "updated_at": "2026-10-15",
  "spec_tier_note": "specs 中的档位字段（cpu_tier / chip_tier / camera_tier）为本项目为规则评分设定的分类档位（1 最低，5 最高），不是厂商跑分或专业评测结果。",
  "products": [ /* 见 6.2 */ ]
}
```

### 6.2 商品记录

```json
{
  "id": "LP001",
  "name": "红米 REDMI Book 14 2025",
  "category": "laptop",
  "model": "REDMI Book 14 2025",
  "brand": "红米",
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
  "pros": ["1.36kg、15.9mm 金属机身，便携性好", "16GB+1TB 大存储，并预留第二个 M.2 硬盘位", "…"],
  "cons": ["仅 Intel 核芯显卡，无独立显卡", "56Wh 电池，配高刷屏实际续航打折", "…"],
  "data_source": "公开资料整理 · 参数经简化，价格非实时",
  "source_url": "https://nb.zol.com.cn/1014/10149291_param.html",
  "image_url": "https://2c.zol-img.com.cn/product/276/900/ceKkwW8okziDE.png",
  "data_status": "unverified",
  "updated_at": "2026-10-15"
}
```

### 6.3 字段约束

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | 唯一标识，用于去重与关联 |
| `name` | ✅ | 商品名称 |
| `category` | ✅ | 必须在 `CATEGORY_LABELS` 中登记（当前仅 laptop / phone） |
| `price` | ✅ | 数值，用于预算筛选 |
| `brand` | ✅ | 品牌筛选 |
| `specs` | ✅ | 键按品类异构，档位字段取值 1–5 |
| `use_cases` | ✅ | 字符串数组 |
| `pros` / `cons` | ✅ | 字符串数组 |
| `data_source` | ✅ | 数据来源说明，**界面与导出报告都会展示** |
| `source_url` | — | 可空：当前 20 条均有链接；取不到来源时留空 |
| `image_url` | — | 可空：外链图片，缺失或加载失败时界面回落类别图标 |
| `data_status` | ✅ | 核验状态，当前一律 `unverified` |
| `updated_at` | ✅ | 数据更新时间，**界面与导出报告都会展示** |

> **缺失字段的商品不会导致整批加载失败**：加载层逐条容错，
> 单条失败只降级该条并标记 `missing_fields`。

### 6.4 档位字段说明

`specs` 中的 `cpu_tier` / `chip_tier` / `camera_tier`
是**本项目为规则评分设定的分类档位**（1 最低，5 最高），
**不是厂商跑分或专业评测结果**。品类收缩到电子产品后，规格表里只剩这四个档位键。

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

> **步骤 5 已过半**：商品记录现在逐条带 `source_url`（20/20）与 `data_status`
> （一律 `unverified`），但 `data_sources` 表仍只有一条整批共用的说明。
> 把来源拆成独立表并补齐许可说明，才是「创新点二」的前提。

---

## 9. 相关文档

| 文档 | 内容 |
|---|---|
| [requirements.md](requirements.md) | 需求规格说明书（含数据可追溯性 NFR-2） |
| [architecture.md](architecture.md) | 技术架构与设计决策 |
| [platform-integration.md](platform-integration.md) | 接入购物平台数据指南 |
| [data-disclaimer.md](data-disclaimer.md) | 数据说明与使用限制 |
