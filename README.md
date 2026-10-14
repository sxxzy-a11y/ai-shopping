# 智购参谋 · 基于大模型的智能消费决策助手

帮你在预算内买到真正适合自己的商品，并且告诉你这个结论**是怎么得出来的**。

它不是聊天机器人，也不是商品列表。它做的是完整的决策链路：
听懂你的需求 → 筛选候选 → 按需求匹配度打分排序 → 多商品横向比较 →
给出可解释的推荐 → 保存决策记录供你回头对比。

---

## 目录

- [快速开始](#快速开始)
- [两种运行模式](#两种运行模式)
- [环境变量](#环境变量)
- [目录结构](#目录结构)
- [功能说明](#功能说明)
- [测试](#测试)
- [常见问题](#常见问题)
- [已知限制](#已知限制)
- [数据说明](#数据说明)

---

## 快速开始

### 1. 环境要求

- **Windows 10/11**（macOS / Linux 同样可用）
- **Python 3.10 或更高**（开发与验证环境为 Python 3.13.9）

检查 Python 版本：

```bash
python --version
```

### 2. 安装依赖

在项目根目录执行：

```bash
pip install -r requirements.txt
```

会安装 5 个包：`streamlit`、`pandas`、`pydantic`、`httpx`、`pytest`。

> 如果你的机器上已经有这些包，这一步会直接跳过，不会重复下载。

### 3. 启动应用

```bash
streamlit run app.py
```

浏览器会自动打开 <http://localhost:8501>。如果没自动打开，手动访问该地址即可。

**这一步不需要任何 API 密钥**，应用会以「本地演示模式」运行，全部功能可用。

### 4. 停止应用

在运行它的终端窗口按 `Ctrl + C`。

---

## 两种运行模式

|  | 本地演示模式 | AI 增强模式 |
|---|---|---|
| 需要密钥 | 不需要 | 需要 |
| 联网 | **完全不联网** | 会调用你配置的模型服务 |
| 需求理解 | 本地规则（预算、类别、用途、核心需求） | 大模型理解，能处理更口语化的表达 |
| 推荐解读 | 只给评分构成与加减分项 | 额外给一段自然语言解读 |
| 计算推荐排序 | 本地规则 | 本地规则（AI 不参与排序） |

**默认就是本地演示模式。** 在 `.env` 里填上密钥即自动进入 AI 增强模式，
界面上的 AI 开关需要你手动打开才会真正调用模型。

### 关于密钥安全

- 密钥**只从环境变量读取**，不写进任何源码文件
- `.env` 已在 `.gitignore` 中排除，不会被提交
- 日志与异常信息里的密钥会被替换成 `sk-****`
- 界面上只显示「已配置」和脱敏片段，不回显明文
- 启用 AI 前，界面会列出**将要发送哪些数据**，由你确认后才发送

---

## 环境变量

把 `.env.example` 复制为 `.env` 后按需填写：

```bash
cp .env.example .env        # Git Bash / macOS / Linux
copy .env.example .env      # Windows CMD
```

### 大模型（可选）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ZHIGOU_LLM_API_KEY` | 空 | API 密钥。留空即本地演示模式 |
| `ZHIGOU_LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容的服务端点 |
| `ZHIGOU_LLM_MODEL` | `deepseek-flash` | 模型名 |
| `ZHIGOU_LLM_TIMEOUT` | `60` | 单次请求超时秒数，超时自动降级 |
| `ZHIGOU_LLM_MAX_TOKENS` | `2000` | 单次回复 token 上限，见下方说明 |

本项目用 `httpx` 直连 OpenAI 兼容接口，**换服务商只需要改环境变量**，不用动代码。
已验证可用的配置：

```ini
# DeepSeek
ZHIGOU_LLM_BASE_URL=https://api.deepseek.com/v1
ZHIGOU_LLM_MODEL=deepseek-flash
```

> **推理模型的 token 上限要注意**
>
> `deepseek-flash`、`deepseek-v4-pro` 这类推理模型，**推理过程也计入
> `max_tokens`**。上限给小了会出现「推理把额度用光、正文为空」的情况。
> 应用会把它当作失败并降级到本地规则模式，不会把空结果当成有效答案。
> 遇到提示「推理过程用尽了 token 额度」时，把 `ZHIGOU_LLM_MAX_TOKENS` 调大即可。

### 本地路径（通常不用改）

| 变量 | 默认值 |
|---|---|
| `ZHIGOU_PRODUCTS_PATH` | `<项目根>/data/products.json` |
| `ZHIGOU_DB_PATH` | `<项目根>/storage/zhigou.db` |
| `ZHIGOU_SETTINGS_PATH` | `<项目根>/storage/settings.json` |

---

## 目录结构

```
ai shopping/
├── app.py                  应用入口：页面配置、样式注入、导航、异常兜底
├── requirements.txt        依赖清单
├── pytest.ini              pytest 配置
├── .env.example            环境变量样例（不含真实密钥）
├── .streamlit/config.toml  Streamlit 官方主题配置
│
├── data/
│   └── products.json       112 条演示商品（10 个品类，见下方「商品品类」）
│
├── scripts/
│   └── fetch_products.py   外部数据接入 CLI（详见 docs/platform-integration.md）
│
├── src/                    业务逻辑层（不依赖 Streamlit，可单独测试）
│   ├── config.py           路径、环境变量、评分权重表与参数标签
│   ├── errors.py           领域异常 + 中文文案映射
│   ├── data_loader.py      商品数据加载与容错
│   ├── ingest.py           外部数据接入：字段映射、档位折算、写前校验
│   ├── demand_parser.py    自然语言 → 结构化需求
│   ├── scoring.py          多维度需求适配评分
│   ├── recommender.py      筛选、排序、放宽建议
│   ├── comparison.py       多商品横向比较
│   ├── database.py         SQLite：分析历史与收藏
│   ├── report_service.py   决策报告组装与导出
│   ├── settings.py         用户偏好读写
│   ├── ai_service.py       大模型调用（传输层）
│   ├── ai_enhance.py       提示词与结果校验（AI 层）
│   └── ui/                 界面层（唯一依赖 Streamlit 的地方）
│       ├── theme.py        配色令牌与全局样式
│       ├── icons.py        线性图标
│       ├── state.py        会话状态与缓存
│       ├── components.py   卡片、评分条、徽章等
│       └── pages/          六个页面
│
├── docs/
│   ├── data-disclaimer.md  数据说明
│   └── platform-integration.md  接入购物平台数据指南
│
├── tests/                  380 个测试
└── openspec/               需求规格与设计文档（含 8 份能力规格）
```

**分层原则**：`app.py` 只管编排，业务规则全在 `src/` 下。
因此评分、筛选、比较这些核心逻辑可以脱离界面做单元测试，
未来要换成 FastAPI + 独立前端时，业务模块可以原样搬走。

---

## 功能说明

### 首页

产品定位说明、需求输入入口、能力说明与数据集概览。

在首页写下需求点「开始分析」，会**直接跳到分析页并立刻出结果**，不用再点一次；
也可以到「智能分析」页用下拉选项逐项填写。

### 智能分析

- **自然语言输入**：直接描述需求，系统提取预算、类别、用途、核心需求、
  可妥协项、品牌偏好与硬性限制
- **结构化控件**：也可以用工整的选项填写；控件填了的内容会覆盖文字描述
- **定向追问**：关键信息缺失时只问缺的那项，已经说过的不会再问
- **推荐排序**：按需求匹配度排序，**不是按价格排序**
- **超预算商品单独列出**并逐条标出超出金额，不伪装成预算内
- **评分可解释**：展开任意商品可以看到每个维度的得分、权重、计算依据，
  以及主要加分项与扣分项
- **导出**：Markdown / CSV

### 商品比较

选 2–5 件商品横向对比，维度覆盖价格、核心参数、适用场景、优缺点与
预算匹配度——**具体比哪些参数按品类自动决定**（笔记本比处理器和重量，
家电比容量和能效，家具比材质和承重）。缺失数据标注为「信息缺失」，
不会用其他商品的值填充。

### 商品品类

数据集覆盖 10 个品类，共 112 条演示商品：

| 品类 | 商品数 | 评分维度的特别之处 |
|---|---|---|
| 笔记本电脑 | 17 | 含便携性 |
| 手机 | 16 | 含便携性 |
| 耳机 | 16 | 不含便携性 |
| 键盘 | 15 | 不含便携性 |
| 家用电器 | 8 | 以耐用性替代便携性 |
| 服饰鞋包 | 8 | 以耐用性替代便携性 |
| 家居家具 | 8 | 耐用性权重最高（0.20） |
| 运动户外 | 8 | 以耐用性替代便携性 |
| 个护美妆 | 8 | 不设耐用性与便携性 |
| 母婴用品 | 8 | 以耐用性替代便携性 |

**再加品类只需两步**：往 `data/products.json` 补商品记录，在
`src/config.py` 的 `CATEGORY_LABELS` 与 `SCORING_WEIGHTS` 里登记类别
与权重。评分、比较与界面会自动适配，不用改业务逻辑代码。

### 历史记录

- 每次分析自动存档（同一组条件重复提交只存一条）
- 从列表重新打开当时的完整报告
- **报告是快照**：商品数据后来更新了，也不会改动历史结论
- 我的收藏：收藏的商品持久化保存

### 个人设置

品牌偏好、价格取向、长期关注项、显示选项。
偏好只作为**默认值**——你在分析页手填的内容永远优先。

### 项目说明

产品价值、技术架构、评分口径说明与数据限制。

---

## 测试

### 运行全部测试

```bash
pytest
```

预期输出：

```
380 passed
```

**测试不需要网络，也不需要任何 API 密钥。**
测试夹具会自动隔离本地设置、数据库，并移除环境变量中的密钥，
保证跑测试不会消耗额度、也不会依赖网络。

### 只跑某一部分

```bash
pytest tests/test_recommender.py      # 筛选、评分、排序
pytest tests/test_database.py         # 持久化
pytest tests/test_app.py              # 界面（无头运行整个应用）
pytest tests/test_acceptance.py       # 端到端验收
pytest -k "降级"                       # 按关键词筛选
```

### 测试覆盖范围

| 文件 | 数量 | 覆盖内容 |
|---|---|---|
| `test_app.py` | 55 | 六个页面的渲染与交互 |
| `test_ai_service.py` | 48 | AI 调用的全部降级路径（打桩，不联网） |
| `test_recommender.py` | 59 | 筛选、评分、排序、放宽建议、按品类维度 |
| `test_demand_parser.py` | 44 | 需求解析与追问 |
| `test_ingest.py` | 43 | 平台数据接入：映射、校验、合并与 CSV 全流程 |
| `test_report_service.py` | 32 | 报告组装、导出与条件指纹 |
| `test_database.py` | 30 | 历史与收藏的读写、容错与跨会话去重 |
| `test_comparison.py` | 19 | 多商品比较 |
| `test_data_loader.py` | 17 | 商品数据加载与降级 |
| `test_settings.py` | 17 | 偏好读写与合并规则 |
| `test_acceptance.py` | 16 | 八类异常场景与完整决策链路 |

（数量以 `pytest --collect-only` 的统计为准，参数化测试会展开成多条。）

### 验证 AI 通路（会用真实密钥联网）

```bash
python -c "from src import ai_service; print(ai_service.probe())"
```

或者启动应用后到「个人设置」页点「测试连接」。

---

## 常见问题

**Q：页面报「商品数据文件不存在」怎么办？**

确认 `data/products.json` 存在，且是合法的 JSON。
你也可以用 `ZHIGOU_PRODUCTS_PATH` 环境变量指向别处。

**Q：报「历史记录读取失败」怎么办？**

`storage/zhigou.db` 可能损坏了。历史与收藏功能会不可用，但**分析功能不受影响**。
想恢复的话，删掉这个文件重启应用，会自动新建一个空库。

**Q：填了预算却提示「格式不正确」？**

结构化预算输入框只接受阿拉伯数字（`3000`、`3000 元` 都可以）。
`三千块` 这类中文数字在自然语言输入框里能识别，在数字框里不行，
因为那是你明确填写的字段，格式不对应该提示而不是猜。

**Q：AI 开关点了没反应？**

没配 `ZHIGOU_LLM_API_KEY` 时开关不会出现。
配了密钥后需要重启应用才会生效（环境变量在启动时读取）。

**Q：提示「推理过程用尽了 token 额度」？**

推理模型的推理过程也计入 `max_tokens`。把 `ZHIGOU_LLM_MAX_TOKENS` 调到
4000 或更高再试。这不影响本地演示模式的任何功能。

**Q：端口 8501 被占用？**

```bash
streamlit run app.py --server.port 8502
```

---

## 已知限制

**数据方面**

- 全部 112 条商品均为**演示数据**，不是真实在售商品，价格不是实时价格，
  参数不是厂商实测值，优缺点不是真实用户评价（见 [数据说明](docs/data-disclaimer.md)）
- 不接入任何电商平台，不提供实时价格、库存、销量或真实评价；目前只覆盖
  10 个常见品类，不是「市面上所有商品」
- 参数中的档位值（处理器档位、能效等级、耐用档位等）是本项目为规则评分设定的
  分级，不是厂商跑分或专业评测结果

**功能方面**

- 中文数字只识别按位书写（`三千`、`两千五百`），口语省略式
  （`两千五` 表示 2500）识别不了，会退回「未识别到预算」并由界面追问
- 需求解析只覆盖预算、类别、用途、核心需求这类高置信字段，拿不准的一律留空
- 商品图片用类别图标占位，没有实拍图
- 第一版不做账号体系与多用户隔离，数据保存在本机

**技术方面**

- 深色侧栏依赖 Streamlit 的 `[data-testid="stSidebar"]` 选择器
  （Streamlit 没有官方 API 改侧栏底色）。已锁定版本并加了断言测试，
  升级 Streamlit 把它改坏时测试会失败，而不是悄悄退化成浅色
- `st.pills` 的多选模式可用，单选模式在 Streamlit 的测试框架 `AppTest` 下
  会报错（浏览器里正常），因此「价格取向」使用了 `st.radio`

---

## 数据说明

**本项目使用的一切商品数据均为演示数据**，由项目自行构造，
仅用于验证筛选、评分与比较逻辑。

- 不冒充真实在售商品，不代表任何真实品牌的实际产品
- 价格不是实时价格，参数不是厂商公布值
- 优缺点不是真实用户评价
- 数据集中不包含销量、用户评价、售后政策与保修信息

**「系统匹配评分」衡量的是商品与你本次需求的匹配程度**，
不是用户评分、销量排名或市场口碑。

详见 [docs/data-disclaimer.md](docs/data-disclaimer.md)。

---

## 开发说明

本项目使用 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 做规格驱动开发。

**当前规格**（已归档合并，是后续改动的依据）：

```
openspec/specs/            8 份能力规格，39 条需求、99 条可测试场景
```

**这次迭代的完整记录**（提案、设计、任务）：

```
openspec/changes/archive/2026-10-12-add-zhigou-mvp/
├── proposal.md   为什么做、改什么、明确不做的事
├── design.md     9 项关键技术决策及取舍
├── specs/        8 份增量规格
└── tasks.md      104 项任务的完成情况
```

改动行为前先改 `openspec/specs/` 下的规格，再改代码。
新功能用 `openspec new change <名字>` 起一个新的变更。

### 接入购物平台数据

应用通过 `data/products.json` 这一份数据契约工作，接入真实平台数据
不需要改业务逻辑。完整指南见
[docs/platform-integration.md](docs/platform-integration.md)，最快的验证方式：

```bash
python scripts/fetch_products.py --write-template data/platform_export.csv  # 生成列名模板
python scripts/fetch_products.py --source csv --input data/platform_export.csv --dry-run
```

取数在 `scripts/fetch_products.py`（CSV / API 两种适配器），
字段映射、档位折算与写前校验在 `src/ingest.py`。
