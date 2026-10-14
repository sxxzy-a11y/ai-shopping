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
    """商品数据文件路径。"""
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

DEFAULT_LLM_BASE_URL: Final[str] = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL: Final[str] = "gpt-4o-mini"
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

CATEGORY_LABELS: Final[dict[str, str]] = {
    "laptop": "笔记本电脑",
    "phone": "手机",
    "headphone": "耳机",
    "keyboard": "键盘",
    "appliance": "家用电器",
    "apparel": "服饰鞋包",
    "furniture": "家居家具",
    "sports": "运动户外",
    "personal_care": "个护美妆",
    "baby": "母婴用品",
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
# 维度差异是有意为之：笔记本与手机看重便携性，耳机与键盘则没有这个维度。

DIMENSION_LABELS: Final[dict[str, str]] = {
    "budget_fit": "预算匹配",
    "need_fit": "核心需求匹配",
    "performance_fit": "性能功能适配",
    "value": "性价比",
    "portability": "便携性",
    "durability": "耐用性",
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
    "driver_mm": "驱动单元",
    "connection": "连接方式",
    "noise_cancelling": "主动降噪",
    "audio_tier": "音质档位",
    "layout": "键位布局",
    "switch_type": "轴体",
    "wireless": "无线",
    "hot_swappable": "热插拔",
    "noise_level": "噪音等级",
    "has_dedicated_gpu": "独立显卡",
    # 家用电器
    "capacity_l": "容量",
    "energy_grade": "能效等级",
    "power_w": "功率",
    "noise_db": "噪音",
    "warranty_years": "质保年限",
    # 服饰鞋包 / 家居家具 / 运动户外
    "material": "材质",
    "comfort_tier": "舒适档位",
    "breathability_tier": "透气档位",
    "width_cm": "宽度",
    "load_kg": "承重",
    "assembly_required": "组装方式",
    "cushion_tier": "缓冲档位",
    "waterproof": "防水",
    # 个护美妆
    "suit_for": "适用对象",
    # 母婴用品
    "age_min_months": "适用起始月龄",
    "safety_cert": "安全认证",
    "foldable": "折叠",
    # 通用
    "durability_tier": "耐用档位",
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
    "headphone": {
        "budget_fit": 0.30,
        "need_fit": 0.30,
        "performance_fit": 0.25,
        "value": 0.15,
    },
    "keyboard": {
        "budget_fit": 0.30,
        "need_fit": 0.25,
        "performance_fit": 0.30,
        "value": 0.15,
    },
    # 以下为非电子品类。维度按品类调整：家电/服饰/母婴以「耐用性」衡量寿命，
    # 家具把耐用权重提到 0.20（大件更看重用得住），个护美妆不设耐用与便携。
    "appliance": {
        "budget_fit": 0.25,
        "need_fit": 0.30,
        "performance_fit": 0.20,
        "value": 0.15,
        "durability": 0.10,
    },
    "apparel": {
        "budget_fit": 0.25,
        "need_fit": 0.30,
        "performance_fit": 0.20,
        "value": 0.15,
        "durability": 0.10,
    },
    "furniture": {
        "budget_fit": 0.25,
        "need_fit": 0.25,
        "performance_fit": 0.20,
        "value": 0.10,
        "durability": 0.20,
    },
    "sports": {
        "budget_fit": 0.25,
        "need_fit": 0.30,
        "performance_fit": 0.20,
        "value": 0.10,
        "durability": 0.15,
    },
    "personal_care": {
        "budget_fit": 0.25,
        "need_fit": 0.30,
        "performance_fit": 0.25,
        "value": 0.20,
    },
    "baby": {
        "budget_fit": 0.25,
        "need_fit": 0.30,
        "performance_fit": 0.20,
        "value": 0.10,
        "durability": 0.15,
    },
}

#: 评分的用户可见名称。需求明确：不得暗示这是真实市场口碑。
SCORE_DISPLAY_NAME: Final[str] = "系统匹配评分"

#: 商品默认选型上限与比较数量约束，界面与校验共用同一组常量。
#: 最小值是 2：两件「二选一」是最常见的比较场景（spec: 两件商品比较表生成）。
MIN_COMPARE_COUNT: Final[int] = 2
MAX_COMPARE_COUNT: Final[int] = 5
DEFAULT_RECOMMEND_LIMIT: Final[int] = 6


# --------------------------------------------------------------------------
# 环境体检（供启动时与诊断脚本使用）
# --------------------------------------------------------------------------


def describe_runtime() -> dict[str, object]:
    """返回当前运行配置摘要，**不含密钥明文**。"""
    return {
        "project_root": str(PROJECT_ROOT),
        "products_path": str(products_path()),
        "products_exists": products_path().is_file(),
        "database_path": str(database_path()),
        "mode": "AI 增强模式" if is_ai_configured() else "本地演示模式",
        "llm_model": llm_model() if is_ai_configured() else None,
        "llm_base_url": llm_base_url() if is_ai_configured() else None,
        "llm_timeout_s": llm_timeout_s(),
        "llm_max_tokens": llm_max_tokens(),
    }
