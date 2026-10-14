"""多商品横向比较。

设计要点
--------
- 缺失字段标成「信息缺失」，**不留空、也不用别的商品的值填充**。
- 每个差异维度打标记（`varies`），界面据此高亮，用户能一眼看到对比要点。
- 不导入 pandas：比较结果先用普通数据结构表达，界面层要转 DataFrame 自己转。
  这样这一层可以脱离任何可视化依赖做单元测试。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src import config
from src.data_loader import Product
from src.demand_parser import Demand
from src.errors import TooFewForComparison, TooManyForComparison

#: 缺失值的统一占位文案。
MISSING_TEXT = "信息缺失"

#: 各类别核心参数的展示顺序。
_PARAM_ORDER: dict[str, list[str]] = {
    "laptop": [
        "cpu", "cpu_tier", "ram_gb", "storage_gb",
        "screen_size", "weight_kg", "battery_h", "has_dedicated_gpu",
    ],
    "phone": [
        "chip", "chip_tier", "ram_gb", "storage_gb",
        "screen_size", "weight_g", "battery_mah", "camera_tier",
    ],
    "headphone": [
        "driver_mm", "connection", "battery_h", "weight_g",
        "noise_cancelling", "audio_tier",
    ],
    "keyboard": [
        "layout", "switch_type", "connection", "weight_g",
        "wireless", "hot_swappable", "noise_level",
    ],
    "appliance": [
        "capacity_l", "energy_grade", "power_w", "noise_db",
        "warranty_years", "durability_tier",
    ],
    "apparel": [
        "material", "comfort_tier", "breathability_tier",
        "durability_tier", "weight_g",
    ],
    "furniture": [
        "material", "width_cm", "load_kg", "weight_kg",
        "durability_tier", "warranty_years", "assembly_required",
    ],
    "sports": [
        "material", "weight_g", "cushion_tier",
        "durability_tier", "waterproof",
    ],
    "personal_care": [
        "power_w", "battery_h", "noise_db", "suit_for", "durability_tier",
    ],
    "baby": [
        "material", "age_min_months", "weight_kg",
        "safety_cert", "foldable", "durability_tier",
    ],
}

#: 参数的中文标签来自 config.SPEC_LABELS（单一来源），避免与评分理由、
#: 商品卡片各写一份而对不上。
_PARAM_LABELS: dict[str, str] = config.SPEC_LABELS

_PARAM_UNITS: dict[str, str] = {
    "ram_gb": "GB",
    "storage_gb": "GB",
    "screen_size": "英寸",
    "weight_kg": "kg",
    "battery_h": "小时",
    "weight_g": "g",
    "battery_mah": "mAh",
    "driver_mm": "mm",
    "capacity_l": "L",
    "power_w": "W",
    "noise_db": "dB",
    "warranty_years": "年",
    "width_cm": "cm",
    "load_kg": "kg",
    "age_min_months": "个月",
}

#: 布尔型参数的中文呈现。
_PARAM_BOOL: dict[str, tuple[str, str]] = {
    "has_dedicated_gpu": ("有", "无"),
    "noise_cancelling": ("支持", "不支持"),
    "wireless": ("支持", "不支持"),
    "hot_swappable": ("支持", "不支持"),
    "assembly_required": ("需自行组装", "免组装"),
    "waterproof": ("支持", "不支持"),
    "safety_cert": ("已认证", "未认证"),
    "foldable": ("可折叠", "不可折叠"),
}

#: 档位型参数，标注满分便于理解量纲。
_PARAM_TIER: dict[str, int] = {
    "cpu_tier": 5,
    "chip_tier": 5,
    "camera_tier": 5,
    "audio_tier": 5,
    "noise_level": 5,
    "energy_grade": 5,
    "durability_tier": 5,
    "comfort_tier": 5,
    "breathability_tier": 5,
    "cushion_tier": 5,
}


# --------------------------------------------------------------------------
# 结果类型
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ComparisonRow:
    """比较表中的一行。"""

    label: str
    values: list[str]
    missing: list[bool]
    #: 各商品在该维度上是否取值不同。界面据此高亮差异项。
    varies: bool

    def display(self, index: int) -> str:
        """取第 index 件商品在该行的展示文本。"""
        return self.values[index]


@dataclass(frozen=True)
class ComparisonTable:
    """完整的比较结果。"""

    products: list[Product]
    rows: list[ComparisonRow]

    def __len__(self) -> int:
        return len(self.products)

    @property
    def headers(self) -> list[str]:
        """表头：商品名。"""
        return [p.name or p.id for p in self.products]

    @property
    def missing_cells(self) -> int:
        """缺失单元格数量，界面据此决定是否提示数据完整度。"""
        return sum(sum(1 for flag in row.missing if flag) for row in self.rows)

    def to_records(self) -> list[dict[str, str]]:
        """转成「每行一个 dict」的结构，方便界面层转 DataFrame。"""
        return [
            {"比较维度": row.label, **dict(zip(self.headers, row.values, strict=True))}
            for row in self.rows
        ]


# --------------------------------------------------------------------------
# 单元格格式化
# --------------------------------------------------------------------------


def format_param(key: str, value) -> str:
    """把一项核心参数格式化成中文展示文本。"""
    if key in _PARAM_BOOL:
        yes, no = _PARAM_BOOL[key]
        return yes if value else no

    if key in _PARAM_TIER and isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}/{_PARAM_TIER[key]}"

    unit = _PARAM_UNITS.get(key, "")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value}{unit}"


def _budget_cell(product: Product, demand: Demand) -> str:
    """预算匹配单元格。未设定预算时明确写「未设定预算」。"""
    if demand.budget is None:
        return "未设定预算"
    if product.price is None:
        return MISSING_TEXT
    if product.price <= demand.budget:
        return "预算内"
    return f"超出预算 {product.price - demand.budget:.0f} 元"


def _ordered_param_keys(products: Sequence[Product]) -> list[str]:
    """按类别顺序取并集，保证同一类别内参数顺序稳定。"""
    keys: list[str] = []
    for product in products:
        for key in _PARAM_ORDER.get(product.category, sorted(product.specs)):
            if key not in keys:
                keys.append(key)
    # 类别表里没登记、但数据里实际存在的参数，补在后面，按名称排序保证稳定
    extra = sorted({k for p in products for k in p.specs} - set(keys))
    return [*keys, *extra]


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------


def compare(
    products: Sequence[Product],
    demand: Demand | None = None,
) -> ComparisonTable:
    """生成多商品比较表。

    Args:
        products: 参与比较的商品，数量须在
            `config.MIN_COMPARE_COUNT` 与 `config.MAX_COMPARE_COUNT` 之间。
        demand: 用户需求。用于计算预算匹配列；省略时该列显示「未设定预算」。

    Raises:
        TooFewForComparison: 少于 2 件。
        TooManyForComparison: 超过上限。
        ValueError: 传入了重复的商品 ID。
    """
    items = list(products)
    if len(items) < config.MIN_COMPARE_COUNT:
        raise TooFewForComparison(
            f"请至少选择 {config.MIN_COMPARE_COUNT} 件商品进行比较，当前只有 {len(items)} 件。"
        )
    if len(items) > config.MAX_COMPARE_COUNT:
        raise TooManyForComparison(
            f"最多同时比较 {config.MAX_COMPARE_COUNT} 件商品，当前选了 {len(items)} 件。"
        )

    ids = [p.id for p in items]
    if len(set(ids)) != len(ids):
        raise ValueError("比较列表中出现了重复的商品")

    effective_demand = demand if demand is not None else Demand()
    rows: list[ComparisonRow] = []

    def add_row(label: str, values: list[str], missing: list[bool]) -> None:
        rows.append(
            ComparisonRow(
                label=label,
                values=values,
                missing=missing,
                varies=len(set(values)) > 1,
            )
        )

    # --- 价格 ---
    add_row(
        "参考价格",
        [p.price_label for p in items],
        [p.price is None for p in items],
    )

    # --- 品牌 ---
    add_row("品牌", [p.brand or MISSING_TEXT for p in items], [not p.brand for p in items])

    # --- 核心参数 ---
    for key in _ordered_param_keys(items):
        if not any(p.has_spec(key) for p in items):
            continue  # 所有商品都没有这项，整行没意义
        values: list[str] = []
        missing: list[bool] = []
        for product in items:
            if product.has_spec(key):
                values.append(format_param(key, product.spec(key)))
                missing.append(False)
            else:
                values.append(MISSING_TEXT)
                missing.append(True)
        add_row(_PARAM_LABELS.get(key, key), values, missing)

    # --- 适用场景 ---
    add_row(
        "适用场景",
        ["、".join(p.use_cases) or MISSING_TEXT for p in items],
        [not p.use_cases for p in items],
    )

    # --- 优点 / 缺点 ---
    for label, attribute in (("优点", "pros"), ("缺点", "cons")):
        values = []
        missing = []
        for product in items:
            entries = getattr(product, attribute)
            values.append("；".join(entries) if entries else MISSING_TEXT)
            missing.append(not entries)
        add_row(label, values, missing)

    # --- 预算匹配 ---
    add_row(
        "预算匹配",
        [_budget_cell(p, effective_demand) for p in items],
        [p.price is None for p in items],
    )

    # --- 数据来源（比较结果同样要能溯源）---
    add_row(
        "数据来源",
        [p.data_source or MISSING_TEXT for p in items],
        [not p.data_source for p in items],
    )

    return ComparisonTable(products=items, rows=rows)
