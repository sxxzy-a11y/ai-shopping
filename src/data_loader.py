"""商品数据加载与校验。

设计要点（对应 design.md D3）：**容错优先于严格校验**。
一条坏记录不应该让整个演示失效，所以逐条校验、单条降级，
失败的那条变成「信息不完整商品」继续参与流程，缺失字段记入
`missing_fields`，由界面标注出来。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src import config, consistency
from src.errors import DataFileInvalid, DataFileMissing, EmptyCatalog

#: 一条商品记录必须具备的字段。缺任意一项即视为「信息不完整」。
REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "category",
    "price",
    "brand",
    "specs",
    "use_cases",
    "pros",
    "cons",
    "data_source",
    "updated_at",
)


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------


class Product(BaseModel):
    """一件商品。

    所有业务字段都允许为空——空值代表「数据里没有」，而不是「取默认值」。
    这一点很重要：需求明确要求缺数据时如实说缺失，不许猜测填充。
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str = ""
    category: str = ""
    price: float | None = None
    brand: str = ""
    specs: dict[str, Any] = Field(default_factory=dict)
    use_cases: list[str] = Field(default_factory=list)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    data_source: str = ""
    updated_at: str = ""

    @property
    def missing_fields(self) -> list[str]:
        """当前缺失的必填字段名。

        刻意做成**派生属性**而不是存储字段。存下来的列表会在数据被改动后
        失效——比如某处把 price 置空，列表里还留着「已完整」的旧结论；
        直接构造 Product（不经过加载器）时更是会谎报为完整。
        派生值永远和当前字段一致。
        """
        checks: dict[str, bool] = {
            "name": bool(self.name),
            "category": bool(self.category),
            "price": self.price is not None,
            "brand": bool(self.brand),
            "specs": bool(self.specs),
            "use_cases": bool(self.use_cases),
            "pros": bool(self.pros),
            "cons": bool(self.cons),
            "data_source": bool(self.data_source),
            "updated_at": bool(self.updated_at),
        }
        return [name for name, ok in checks.items() if not ok]

    @property
    def is_complete(self) -> bool:
        """是否所有必填字段都在。"""
        return not self.missing_fields

    @property
    def data_issues(self) -> list[consistency.Issue]:
        """当前记录**内部矛盾**的地方（字段都在、但互相打架）。

        与 `missing_fields` 的分工：那个管「字段缺失」，这个管「字段矛盾」。
        缺 `pros` 由前者报告，`pros` 说支持独显而参数写着 false 由后者报告。

        同样刻意做成**派生属性**而不是存储字段，理由与 `missing_fields` 一致：
        存下来的列表会在数据被改动后失效，直接构造 Product（不经过加载器）
        时更会谎报为「没有问题」。检测规则见 `src/consistency.py`。
        """
        return consistency.check_product(self)

    @property
    def has_data_issues(self) -> bool:
        """是否存在内部矛盾。界面据此决定要不要出「资料存疑」标记。"""
        return bool(self.data_issues)

    @property
    def category_label(self) -> str:
        """类别中文名。"""
        return config.category_label(self.category)

    @property
    def price_label(self) -> str:
        """参考价格的中文展示文本。"""
        return f"{self.price:.0f} 元" if self.price is not None else "价格未知"

    def spec(self, key: str, default: Any = None) -> Any:
        """安全读取一项核心参数，缺失时返回 default。"""
        return self.specs.get(key, default)

    def has_spec(self, key: str) -> bool:
        """该核心参数是否存在。评分器用它决定某个维度是否参与计算。"""
        return key in self.specs and self.specs[key] is not None


@dataclass(frozen=True)
class Catalog:
    """一次加载的结果：商品集合 + 数据集级元信息 + 加载过程中的问题记录。"""

    products: list[Product]
    dataset_name: str = ""
    disclaimer: str = ""
    dataset_updated_at: str = ""
    tier_note: str = ""
    issues: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.products)

    @property
    def incomplete_count(self) -> int:
        """信息不完整的商品数量。"""
        return sum(1 for p in self.products if not p.is_complete)

    def by_category(self, category: str) -> list[Product]:
        """取某一类别的全部商品。"""
        return [p for p in self.products if p.category == category]

    def present_categories(self) -> list[str]:
        """数据集中实际出现的类别，保持 config 中定义的顺序。"""
        found = {p.category for p in self.products}
        return [c for c in config.CATEGORY_LABELS if c in found]

    def brands(self) -> list[str]:
        """数据集中出现过的全部品牌，按名称排序。

        自然语言里的品牌偏好需要拿它来匹配——不靠硬编码品牌清单，
        数据文件里加了新品牌，解析器就自动认识。
        """
        return sorted({p.brand for p in self.products if p.brand})

    def brands_of(self, category: str) -> list[str]:
        """某一类别下的品牌。"""
        return sorted({p.brand for p in self.by_category(category) if p.brand})

    def get(self, product_id: str) -> Product | None:
        """按 ID 查商品，不存在返回 None。"""
        for product in self.products:
            if product.id == product_id:
                return product
        return None


# --------------------------------------------------------------------------
# 字段宽容转换
# --------------------------------------------------------------------------
#
# 每个转换函数都不抛异常：拿到不合预期的类型时返回安全值，
# 由调用方记录到 missing_fields。


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _coerce_price(value: Any) -> float | None:
    """把价格转成正浮点数。非数值、非正数一律视为不可用。"""
    if isinstance(value, bool):  # bool 是 int 的子类，需先挡掉
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _coerce_str_list(value: Any) -> list[str]:
    """转成字符串列表。容忍单个字符串（会被当成只有一项）。"""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [text for item in value if (text := _coerce_text(item))]
    return []


def _coerce_specs(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _build_product(record: Any) -> Product | None:
    """把一条原始记录转成 Product。

    返回 None 表示这条记录连 ID 都没有，无法被引用，只能整条跳过。
    """
    if not isinstance(record, dict):
        return None

    product_id = _coerce_text(record.get("id"))
    if not product_id:
        return None

    # 逐项转换都是宽容的：拿到不合预期的类型就落到安全值，
    # 由 Product.missing_fields 这个派生属性实时判定哪些字段算缺失。
    # 注意判定依据是「转换后是否为空」而不是「原始键是否存在」——
    # price 填了 "abc" 这种情况同样属于数据不可用。
    return Product(
        id=product_id,
        name=_coerce_text(record.get("name")),
        category=_coerce_text(record.get("category")),
        price=_coerce_price(record.get("price")),
        brand=_coerce_text(record.get("brand")),
        specs=_coerce_specs(record.get("specs")),
        use_cases=_coerce_str_list(record.get("use_cases")),
        pros=_coerce_str_list(record.get("pros")),
        cons=_coerce_str_list(record.get("cons")),
        data_source=_coerce_text(record.get("data_source")),
        updated_at=_coerce_text(record.get("updated_at")),
    )


# --------------------------------------------------------------------------
# 加载入口
# --------------------------------------------------------------------------


def _read_raw(path: Path) -> Any:
    """读文件并解析 JSON，把两类失败翻译成领域异常。"""
    if not path.is_file():
        raise DataFileMissing(
            f"商品数据文件不存在：{path}。请确认 data/products.json 是否就位。",
            detail=str(path),
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise DataFileInvalid(
            f"商品数据文件解析失败：{path.name}。请检查该文件是否为合法 JSON。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def _extract_records(raw: Any) -> tuple[list[Any], dict[str, Any]]:
    """兼容两种顶层结构：裸数组，或带元信息的 {"products": [...]}。"""
    if isinstance(raw, list):
        return raw, {}
    if isinstance(raw, dict):
        records = raw.get("products", [])
        if not isinstance(records, list):
            raise DataFileInvalid(
                "商品数据文件的 products 字段应为数组。",
                detail=f"got {type(records).__name__}",
            )
        return records, raw
    raise DataFileInvalid(
        "商品数据文件的顶层结构应为数组或包含 products 数组的对象。",
        detail=f"got {type(raw).__name__}",
    )


def load_catalog(path: Path | None = None) -> Catalog:
    """加载商品数据集。

    Raises:
        DataFileMissing: 文件不存在。
        DataFileInvalid: 内容不是合法 JSON，或顶层结构不符合约定。
        EmptyCatalog: 文件合法但没有任何可用商品。
    """
    target = Path(path) if path is not None else config.products_path()
    raw = _read_raw(target)
    records, meta = _extract_records(raw)

    products: list[Product] = []
    issues: list[str] = []
    seen_ids: set[str] = set()

    for index, record in enumerate(records):
        product = _build_product(record)
        if product is None:
            issues.append(f"第 {index + 1} 条记录缺少 id，已跳过")
            continue
        if product.id in seen_ids:
            issues.append(f"商品 id 重复：{product.id}（第 {index + 1} 条），已跳过")
            continue
        seen_ids.add(product.id)
        if not product.is_complete:
            issues.append(
                f"商品 {product.id}（{product.name or '未命名'}）缺少字段："
                f"{'、'.join(product.missing_fields)}"
            )
        products.append(product)

    if not products:
        raise EmptyCatalog(
            f"商品数据文件中没有可用的商品记录：{target}。",
            detail=f"{len(records)} 条原始记录，全部不可用",
        )

    return Catalog(
        products=products,
        dataset_name=_coerce_text(meta.get("dataset_name")),
        disclaimer=_coerce_text(meta.get("disclaimer")),
        dataset_updated_at=_coerce_text(meta.get("updated_at")),
        tier_note=_coerce_text(meta.get("spec_tier_note")),
        issues=issues,
    )
