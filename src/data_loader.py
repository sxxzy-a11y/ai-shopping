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
    #: 型号。**可空**——服装、家具这类品类本来就没有型号概念，
    #: 给一件 T 恤编个型号是造数据。空值如实表达「这个信息不存在」。
    model: str = ""
    #: 逐条的原始资料链接。自造数据没有真实来源，因此为空。
    source_url: str = ""
    #: 核验状态：verified / unverified。默认未核验——没核实过就不该说是已核实。
    data_status: str = "unverified"
    #: 价格的来源与采集时间（来自价格记录）。价格是单独记录的，这几项随之而来。
    price_source: str = ""
    price_collected_at: str = ""

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
    def is_verified(self) -> bool:
        """该记录是否已核验。"""
        return self.data_status == "verified"

    @property
    def status_label(self) -> str:
        """核验状态的中文名，界面直接展示。"""
        return "已核验" if self.is_verified else "未核验"

    @property
    def has_source_url(self) -> bool:
        return bool(self.source_url.strip())

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
        # 溯源字段：型号、来源链接、核验状态，以及价格记录带来的来源与时间。
        # 空值一律落到空串——「没填」与「填了空」在展示上是一回事。
        model=_coerce_text(record.get("model")),
        source_url=_coerce_text(record.get("source_url")),
        data_status=_coerce_text(record.get("data_status")) or config.STATUS_UNVERIFIED,
        price_source=_coerce_text(record.get("price_source")),
        price_collected_at=_coerce_text(record.get("price_collected_at")),
    )


# --------------------------------------------------------------------------
# 加载入口
# --------------------------------------------------------------------------


def read_seed(path: Path | None = None) -> tuple[list[Any], dict[str, Any]]:
    """读种子数据文件，返回 (记录列表, 数据集元信息)。

    商品数据已改存数据库，这个文件**只在库为空时导入一次**。
    所以它的错误文案也变了：文件缺失意味着「库空且没有种子可用」，
    而不是「商品数据不见了」。

    Raises:
        DataFileMissing: 文件不存在。
        DataFileInvalid: 内容不是合法 JSON，或顶层结构不符合约定。
    """
    target = Path(path) if path is not None else config.products_path()
    if not target.is_file():
        raise DataFileMissing(
            f"商品库为空，且找不到种子数据文件：{target}。"
            f"请确认 data/products.json 是否就位。",
            detail=str(target),
        )
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise DataFileInvalid(
            f"种子数据文件解析失败：{target.name}。请检查该文件是否为合法 JSON。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc
    return _extract_records(raw)


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
        "商品数据的顶层结构应为数组或包含 products 数组的对象。",
        detail=f"got {type(raw).__name__}",
    )


#: 数据集级元信息的字段名 → 数据库里的键。
_META_KEYS = {
    "dataset_name": "dataset_name",
    "disclaimer": "disclaimer",
    "updated_at": "updated_at",
    "spec_tier_note": "spec_tier_note",
}


def load_catalog(path: Path | None = None) -> Catalog:
    """加载商品目录。

    Args:
        path: **数据库**文件路径。省略时取项目配置的数据库。
            注意语义变化：此前这个参数指的是商品 JSON 文件，
            数据入数据库后商品数据与历史共用同一个库。

    数据来自数据库。**库为空时自动导入种子数据**（`data/products.json`）——
    这是「开箱即用」与「单一数据源」之间的折中：没有它，用户克隆下来
    必须先跑一个迁移命令才能启动应用。

    库里已有商品时**不导入、不覆盖**：用户的录入永远优先于种子。

    Raises:
        DataFileMissing: 库为空且种子文件不存在。
        DataFileInvalid: 种子文件非法（只可能发生在首次导入时）。
        EmptyCatalog: 库与种子里都没有可用商品。
        ProductStoreReadError: 数据库损坏。
    """
    from src import product_store

    db_path = Path(path) if path is not None else config.products_db_path()

    records = product_store.load_product_records(db_path)
    if not records:
        # 空库 → 导入种子。种子缺失时 DataFileMissing 自然抛出，
        # 文案已经改成「库为空且找不到种子文件」。
        product_store.seed_from_json(config.products_path(), path=db_path)
        records = product_store.load_product_records(db_path)

    meta = product_store.load_dataset_meta(db_path)

    products: list[Product] = []
    issues: list[str] = []

    # 这里不再查重：商品表的主键已经保证 ID 唯一，仓储层也在写入时为无 ID 的
    # 记录把关。加载层的重复检查成了不可达代码，留着只会让人以为还有另一条
    # 可能出错的路径。
    for index, record in enumerate(records):
        product = _build_product(record)
        if product is None:
            issues.append(f"第 {index + 1} 条记录缺少 id，已跳过")
            continue
        if not product.is_complete:
            issues.append(
                f"商品 {product.id}（{product.name or '未命名'}）缺少字段："
                f"{'、'.join(product.missing_fields)}"
            )
        products.append(product)

    if not products:
        raise EmptyCatalog(
            "商品库中没有可用的商品记录，请先导入商品数据。",
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
