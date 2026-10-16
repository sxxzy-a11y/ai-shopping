"""集中配置：环境变量、路径解析、评分权重表。

设计要点：所有可调参数集中在本模块，业务模块通过导入获取，
不得在业务代码中内联这些字面量。评分权重尤其如此——需求明确要求
权重集中配置，不散落在多个文件里。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------

#: 项目根目录。用 __file__ 反推而非依赖当前工作目录，
#: 这样从任意目录启动应用都能找到数据文件。
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """把 .env 的键值对写入 os.environ，已存在的环境变量不覆盖。

    只做最小解析：跳过空行与 # 注释、去掉包裹引号、不做变量展开。
    目的是避免为了读一个 .env 文件而额外引入 python-dotenv 依赖。
    """
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv(PROJECT_ROOT / ".env")


# --------------------------------------------------------------------------
# 环境变量读取辅助
# --------------------------------------------------------------------------


def _env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_float(name: str, default: float) -> float:
    raw = _env_str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# --------------------------------------------------------------------------
# 数据与存储路径
# --------------------------------------------------------------------------


def products_path() -> Path:
    """种子数据文件路径。

    商品数据已存进数据库（见 `products_db_path`），这个文件只在**库为空时**
    被导入一次。保留它而不是删掉，是为了「克隆下来直接能跑」——
    没有种子就得先执行迁移命令才能启动。
    """
    override = _env_str("ZHIGOU_PRODUCTS_PATH")
    return Path(override) if override else PROJECT_ROOT / "data" / "products.json"


def database_path() -> Path:
    """SQLite 数据库文件路径。"""
    override = _env_str("ZHIGOU_DB_PATH")
    return Path(override) if override else PROJECT_ROOT / "storage" / "zhigou.db"


def settings_path() -> Path:
    """用户偏好设置文件路径。

    和商品数据、数据库一样支持环境变量覆盖——测试靠它把设置写进临时目录，
    避免污染开发机上的真实设置文件（这个坑真的踩过一次：
    设置页的测试写到了 storage/settings.json，把后续测试全带偏了）。
    """
    override = _env_str("ZHIGOU_SETTINGS_PATH")
    return Path(override) if override else PROJECT_ROOT / "storage" / "settings.json"


#: 商品核验状态。
#: 放在 config 而不是 product_store：`data_loader` 也要用它，而
#: `product_store` 会经 `database` 间接引到 `report_service`，那条链上回头引
#: `data_loader` 会成环。config 是叶子模块，两边都能引它。
STATUS_VERIFIED: Final[str] = "verified"
STATUS_UNVERIFIED: Final[str] = "unverified"


def products_db_path() -> Path:
    """商品数据库文件路径。

    **与历史记录分开是两个文件**，理由不是洁癖：共用一个文件时，
    文件一旦损坏，商品数据与历史会同时读不出来，整个应用直接不可用。
    分开之后损坏是局部的——历史坏了仍能做分析，商品库坏了历史仍在。

    这也对应数据分工：商品是**外部录入**的数据，历史是**程序产生**的记录，
    两者的写入节奏、备份需求、损坏后果都不一样。
    """
    override = _env_str("ZHIGOU_PRODUCTS_DB_PATH")
    return Path(override) if override else PROJECT_ROOT / "storage" / "products.db"


def knowledge_dir() -> Path:
    """知识语料目录。缺失时 AI 问答提示无资料，其余功能不受影响。"""
    override = _env_str("ZHIGOU_KNOWLEDGE_DIR")
    return Path(override) if override else PROJECT_ROOT / "data" / "knowledge"


# --------------------------------------------------------------------------
# 账号
# --------------------------------------------------------------------------

#: 初始管理员的凭据来源。
#:
#: 起作用的时机只有一次：**账号表为空时**。之后这两个变量改了也不生效——
#: 管理员已经建好了，改环境变量不会悄悄把别人变成管理员（任务 11.2）。
ADMIN_USERNAME_ENV: Final[str] = "ZHIGOU_ADMIN_USERNAME"
ADMIN_PASSWORD_ENV: Final[str] = "ZHIGOU_ADMIN_PASSWORD"

#: 未配置时生成的随机密码长度。够长，因为它是打字复制粘贴一次就改掉的东西。
ADMIN_RANDOM_PASSWORD_BYTES: Final[int] = 12


def admin_username() -> str:
    """配置里的管理员用户名。未配置返回空串。"""
    return _env_str(ADMIN_USERNAME_ENV)


def admin_password() -> str:
    """配置里的管理员密码。未配置返回空串——调用方据此决定是否随机生成。

    **不设默认值**：「没配置就用 admin/123456」这种兜底，等于给每个
    克隆这份代码的人发一个公开密码。
    """
    return _env_str(ADMIN_PASSWORD_ENV)


# --------------------------------------------------------------------------
# 知识检索参数
# --------------------------------------------------------------------------
#
# 这三个值都可以调，且**应该**在语料变化后重新校准：
# 权重与阈值共同决定「检索到什么」和「判定为检索不到」。

#: 文档类型系数。通用性问题（「怎么选」「有什么区别」）要命中选购指南，
#: 而不是某件具体商品——商品条目的字段罗列命中二元组多，不压一压会霸榜。
#:
#: 商品系数 **0.45 是实测校准出来的**（tasks 5.3）：在 8 个通用问题 +
#: 4 个具体商品查询上扫了一遍，0.55 与 0.50 时「机械键盘选什么轴」会被
#: 商品名里的「机械键盘」顶掉选购指南（7/8），0.45 及以下全部通过（8/8 + 4/4）。
#: 取**通过值里最高的那个**——系数越低商品条目越难被检索到，
#: 没必要压得比需要的更狠。
KNOWLEDGE_TYPE_WEIGHTS: Final[dict[str, float]] = {
    "category": 1.0,
    "service": 1.0,
    "product": 0.45,
}

#: 查询点名了某个品类时，该品类的资料额外加权。
#:
#: 为什么需要它：语料之间会有**无意的字面碰撞**——键盘选购指南里提到
#: 「在笔记本和平板之间切换」，于是问「笔记本多重适合带出门」时它反而
#: 排在笔记本电脑选购指南之前。用户既然点名了品类，那个品类的资料
#: 就该优先，这一条比纯词频匹配更贴近意图。
KNOWLEDGE_CATEGORY_BOOST: Final[float] = 1.6

#: 品牌加权系数。查询点名了品牌（「华为怎么样」「红米怎么样」）时，该品牌的
#: 商品条目额外加权。品牌词只有两三个字，BM25 天然分低——不加权的话，
#: 这类宽问题会被阈值挡成「检索不到」，而用户明明问到了点子上。
#:
#: 品类加权与品牌加权可以叠加，但品牌加权有品类约束：点名了「华为笔记本」时，
#: 华为的手机条目不吃这个加权——问的是电脑，不该把手机顶上来。
KNOWLEDGE_BRAND_BOOST: Final[float] = 3.0

#: 相关度阈值。最高分低于它即判定为「检索不到」。
#: 定高了会把「明明有资料」判成找不到，定低了会把弱相关结果当答案返回——
#: 后者的危害更大，所以取值偏保守。
KNOWLEDGE_MIN_SCORE: Final[float] = 3.0

#: 单次检索返回的最大条数。配合相对截断使用，把噪声挡在模型之外。
KNOWLEDGE_MAX_RESULTS: Final[int] = 3

#: 相对相关度截断系数。只保留得分不低于「最高分 × 系数」的命中。
#:
#: 为什么需要它：绝对阈值只能判断「有没有」，判断不了「准不准」——实测一次
#: 查询的第一名 8.57 分时，后面跟着一串 2.x / 1.x 的弱命中，它们都过了绝对
#: 阈值，一起喂给模型只会稀释答案。按「与第一名同一量级」取舍更贴近意图。
#:
#: 0.35 是按当前语料的实测分布取的：术语题（8.57 / 4.13）与商品查询
#: （4.35 / 2.09 / 2.00）都能保留第二条，而 2.x 的噪声被挡住。
#: 调高会更容易漏掉并列相关的第二篇资料，调低则截断失效。
KNOWLEDGE_RELATIVE_CUT: Final[float] = 0.35

#: 追问价格意图的词。命中后 AI 问答**不作答**，改为引导到商品筛选。
#:
#: 为什么必须挡住：检索按文本相关性找资料，**完全不理解数值约束**。
#: 原型实测——问「2000 元以内买什么手机」，检索返回的是一款远超预算的商品。
#: 这不是缺陷而是检索的本性，所以价格问题一律走结构化查询。
KNOWLEDGE_PRICE_INTENT_TERMS: Final[tuple[str, ...]] = (
    "多少钱",
    "价格",
    "价位",
    "预算",
    "便宜",
    "最贵",
    "最低价",
    "块钱",
    "元以内",
    "以内",
)

#: BM25 参数。k1 控制词频饱和，b 控制文档长度归一化强度。
KNOWLEDGE_BM25_K1: Final[float] = 1.5
KNOWLEDGE_BM25_B: Final[float] = 0.75


# --------------------------------------------------------------------------
# Agent 编排参数
# --------------------------------------------------------------------------

#: 一次编排最多几轮「模型请求工具 → 执行 → 回灌」。
#:
#: 5 轮够覆盖最长的一条路径：筛选 → 详情 → 比较 → 查资料 → 作答。
#: 设上限是为了防两件事——模型陷进循环反复调同一个工具，
#: 以及单次分析的耗时与 token 失控（每轮都是一次完整的模型请求）。
AGENT_MAX_ROUNDS: Final[int] = 5

#: 回灌给模型的单条工具结果上限（字符）。
#: 工具返回的结构化数据可能很大，截断的是**回灌**这一份；
#: 轨迹里的摘要另有更严格的截断。
AGENT_TOOL_RESULT_MAX_CHARS: Final[int] = 4000

#: 执行轨迹里单条摘要的上限（字符）。轨迹是给人看的，不是给机器看的。
AGENT_TRACE_SUMMARY_MAX_CHARS: Final[int] = 120


def display_path(path: Path | str) -> str:
    """把路径显示成相对项目根的短路径。

    不在项目目录内时返回绝对路径——**不能直接用 `relative_to`**，
    配置指向外部目录时它会抛 ValueError，把界面整个搞崩。
    """
    target = Path(path)
    try:
        return str(target.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(target)


# --------------------------------------------------------------------------
# 大模型（可选）配置
# --------------------------------------------------------------------------
#
# 全部通过函数读取而非模块级常量，这样测试可以 monkeypatch 环境变量，
# 也能在运行期切换模式而不必重启进程。

LLM_API_KEY_ENV: Final[str] = "ZHIGOU_LLM_API_KEY"
LLM_BASE_URL_ENV: Final[str] = "ZHIGOU_LLM_BASE_URL"
LLM_MODEL_ENV: Final[str] = "ZHIGOU_LLM_MODEL"
LLM_TIMEOUT_ENV: Final[str] = "ZHIGOU_LLM_TIMEOUT"
LLM_MAX_TOKENS_ENV: Final[str] = "ZHIGOU_LLM_MAX_TOKENS"

#: 默认端点与模型名**必须与 `.env.example` 登记的配置一致**。
#: 二者不一致时，漏配环境变量的部署会静默打向另一个服务商——不报错、
#: 只是失败，很难排查。`tests/test_config.py` 有断言锁死这层绑定，
#: 改这里必须同步改 `.env.example`，否则测试会失败。
DEFAULT_LLM_BASE_URL: Final[str] = "https://api.deepseek.com/v1"
DEFAULT_LLM_MODEL: Final[str] = "deepseek-flash"
DEFAULT_LLM_TIMEOUT_S: Final[float] = 60.0

#: 单次回复的 token 上限。
#: **推理模型的推理过程也计入这个额度**，给小了会出现「正文为空、
#: finish_reason=length」——所以默认值要比普通对话模型宽裕得多。
DEFAULT_LLM_MAX_TOKENS: Final[int] = 2000


def llm_api_key() -> str:
    """读取大模型 API 密钥。未配置时返回空字符串。"""
    return _env_str(LLM_API_KEY_ENV)


def llm_base_url() -> str:
    """读取大模型服务端点，默认指向 OpenAI 兼容地址。"""
    return _env_str(LLM_BASE_URL_ENV, DEFAULT_LLM_BASE_URL)


def llm_model() -> str:
    """读取模型名。"""
    return _env_str(LLM_MODEL_ENV, DEFAULT_LLM_MODEL)


def llm_timeout_s() -> float:
    """读取请求超时秒数。"""
    return _env_float(LLM_TIMEOUT_ENV, DEFAULT_LLM_TIMEOUT_S)


def llm_max_tokens() -> int:
    """读取单次回复的 token 上限。"""
    raw = _env_str(LLM_MAX_TOKENS_ENV)
    if not raw:
        return DEFAULT_LLM_MAX_TOKENS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_LLM_MAX_TOKENS
    return value if value > 0 else DEFAULT_LLM_MAX_TOKENS


def is_ai_configured() -> bool:
    """是否已配置可用的密钥。为假时应运行在本地演示模式。"""
    return bool(llm_api_key())


# --------------------------------------------------------------------------
# 商品类别
# --------------------------------------------------------------------------

#: 商品库实际覆盖的类别。**只有这两类电子产品**——每个类别要做 10 款真实型号，
#: 摊薄了每类只剩个位数，参数可比性和说服力都会垮掉。
#: 键盘与耳机曾在这一版里，因为品类聚焦（只演示笔记本电脑与手机）而被移除。
#: 用户提到表外的品类时由 `demand_parser.detect_unsupported_category`
#: 明确回「暂不支持」，而不是跨类别乱推一堆无关商品。
CATEGORY_LABELS: Final[dict[str, str]] = {
    "laptop": "笔记本电脑",
    "phone": "手机",
}


def category_label(category: str) -> str:
    """把类别英文键转成界面用的中文名，未知类别原样返回。"""
    return CATEGORY_LABELS.get(category, category)


# --------------------------------------------------------------------------
# 评分权重表（唯一权重来源）
# --------------------------------------------------------------------------
#
# 每个类别一张维度权重表，同一类别内权重之和必须为 1.0——
# tests/test_recommender.py 有断言守护这一点，漏配或改错会直接测试失败。
#
# 维度差异是有意为之：笔记本与手机都保留便携性，但需求与性价比的权重不同。

DIMENSION_LABELS: Final[dict[str, str]] = {
    "budget_fit": "预算匹配",
    "need_fit": "核心需求匹配",
    "performance_fit": "性能功能适配",
    "value": "性价比",
    "portability": "便携性",
}

#: 商品参数键 → 中文标签（单一来源）。
#: 评分理由、比较表列名、商品卡片都从这里取，避免三处各写一份而对不上。
SPEC_LABELS: Final[dict[str, str]] = {
    # 电子产品
    "cpu": "处理器",
    "cpu_tier": "处理器档位",
    "chip": "芯片",
    "chip_tier": "芯片档位",
    "ram_gb": "内存",
    "storage_gb": "存储",
    "screen_size": "屏幕尺寸",
    "weight_kg": "整机重量",
    "weight_g": "重量",
    "battery_h": "续航",
    "battery_mah": "电池容量",
    "camera_tier": "拍照档位",
    "has_dedicated_gpu": "独立显卡",
}

SCORING_WEIGHTS: Final[dict[str, dict[str, float]]] = {
    "laptop": {
        "budget_fit": 0.25,
        "need_fit": 0.25,
        "performance_fit": 0.25,
        "value": 0.15,
        "portability": 0.10,
    },
    "phone": {
        "budget_fit": 0.25,
        "need_fit": 0.30,
        "performance_fit": 0.25,
        "value": 0.10,
        "portability": 0.10,
    },
}

#: 评分的用户可见名称。需求明确：不得暗示这是真实市场口碑。
SCORE_DISPLAY_NAME: Final[str] = "系统匹配评分"

#: 商品默认选型上限与比较数量约束，界面与校验共用同一组常量。
#: 最小值是 2：两件「二选一」是最常见的比较场景（spec: 两件商品比较表生成）。
MIN_COMPARE_COUNT: Final[int] = 2
MAX_COMPARE_COUNT: Final[int] = 5
DEFAULT_RECOMMEND_LIMIT: Final[int] = 6

#: 超预算候选最多展示几条。**与 `DEFAULT_RECOMMEND_LIMIT` 相互独立**。
#:
#: 曾经两处共用同一个 `limit`，导致「10 件超预算只显示 6 件、界面还说成 6 件」——
#: 而 `limit` 的语义本来就是「预算内推荐条数上限」。截断本身可以接受
#: （无类别限制 + 低预算时超预算候选可能上百条），但**必须如实告知还有多少**。
MAX_OVER_BUDGET_SHOWN: Final[int] = 10


# --------------------------------------------------------------------------
# 环境体检（供启动时与诊断脚本使用）
# --------------------------------------------------------------------------


def describe_runtime() -> dict[str, object]:
    """返回当前运行配置摘要，**不含密钥明文**。"""
    return {
        "project_root": str(PROJECT_ROOT),
        "products_db_path": str(products_db_path()),
        "products_db_exists": products_db_path().is_file(),
        "seed_path": str(products_path()),
        "seed_exists": products_path().is_file(),
        "database_path": str(database_path()),
        "mode": "AI 增强模式" if is_ai_configured() else "本地演示模式",
        "llm_model": llm_model() if is_ai_configured() else None,
        "llm_base_url": llm_base_url() if is_ai_configured() else None,
        "llm_timeout_s": llm_timeout_s(),
        "llm_max_tokens": llm_max_tokens(),
    }
