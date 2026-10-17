"""分类与品牌的元数据，以及由它决定的**可见性过滤**（变更 §8.10 / §9 / §10）。

两个关键设计（见 design D9–D11）：

**分类键集合不可增删。** 界面只维护既有分类的展示名、排序与启用状态；
真正的键集合仍然由 `config.CATEGORY_LABELS` 定义。理由是新增一个分类
要同时配评分权重、参数档位与知识指南，那是代码与语料的工作量——
做成界面按钮只会让系统进入「配置不完整」的状态，推荐缺权重、问答缺资料，
而且不报错，只是结果悄悄变差。现有 5 处断言把分类键钉死了，也都靠这一点成立。

**停用是读取时过滤，不写商品行。** 否则恢复时无法区分「管理员当初手工下架的」
与「因分类停用而被下架的」——`is_active` 一个字段承担两种原因，取关分类时
要么误上架、要么漏恢复。

一处必须小心的实现细节：这个过滤**不得进入 `Catalog.present_categories`**。
`test_acceptance.py` 断言 `present_categories() == set(config.CATEGORY_LABELS)`，
过滤一旦下沉到那里，停用一个分类就会直接把它打红。所以过滤发生在
`visible_catalog()` 造的**副本**上，`Catalog` 本身照旧如实反映数据里有什么。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from src import config
from src.auth import User, require_admin
from src.data_loader import Catalog, Product
from src.errors import ProductStoreReadError, ProductStoreWriteError, ZhigouError


@contextmanager
def _connection(path: Path | None):
    """打开商品库连接。

    **`database` 必须延迟导入。** 它经 `report_service` 间接引到 `recommender`，
    而 `recommender` 又要引本模块（可见性过滤）——模块级导入立刻成环，
    报的还是「partially initialized module」这种看不懂的错。
    本项目已有的两处成环也是这么解的（`state.py` 里引 `settings`）。

    另：不带路径时落到**商品库**。`connect()` 自己的默认值是历史库，
    本模块是商品域的东西，走默认值就会去读历史库——历史库坏了的时候，
    表现是「分析也用不了了」，而分析其实跟它没关系。
    """
    from src import database

    target = path if path is not None else config.products_db_path()
    with database.connect(target) as connection:
        yield connection

@dataclass(frozen=True)
class CategoryEntry:
    """一个分类在界面上的一条记录：键 + 生效后的元数据。"""

    key: str
    label: str
    sort_order: int
    is_active: bool
    #: 展示名是否被管理员改过（界面上标一下，免得看不出默认值是哪来的）
    custom_label: bool = False


@dataclass(frozen=True)
class BrandEntry:
    brand_name: str
    display_name: str
    sort_order: int
    is_active: bool
    #: 库里有没有这个品牌的商品。字典里登记了但没有商品的品牌会标出来——
    #: 那种品牌**不会被解析器认识**，界面上要说清楚。
    product_count: int = 0


def _ensure(path: Path | None) -> None:
    """建表就绪。表结构定义在 `database._SCHEMA_PRODUCTS`（单一来源），
    这里只负责触发建表，并把异常翻成**商品库**的读异常。"""
    from src import database

    try:
        database.init_product_db(path)
    except ZhigouError as exc:
        raise ProductStoreReadError(detail=exc.detail) from exc


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# 分类元数据
# --------------------------------------------------------------------------


def category_entries(path: Path | None = None) -> list[CategoryEntry]:
    """列出全部分类。

    **全集来自 `config.CATEGORY_LABELS`，不是来自表。** 表里只放覆盖项。
    表里出现 config 不认识的键会被忽略（并记一条日志）——那说明有人在
    数据库里手工塞了东西，或者某个分类从代码里下线了。
    """
    _ensure(path)
    with _connection(path) as connection:
        rows = {
            row["category_key"]: row
            for row in connection.execute("SELECT * FROM category_meta")
        }

    entries: list[CategoryEntry] = []
    for index, (key, default_label) in enumerate(config.CATEGORY_LABELS.items()):
        row = rows.get(key)
        if row is None:
            entries.append(CategoryEntry(key, default_label, index, True, False))
            continue
        custom = bool(row["display_label"])
        entries.append(
            CategoryEntry(
                key=key,
                label=(row["display_label"] or default_label),
                sort_order=row["sort_order"] if row["sort_order"] is not None else index,
                is_active=bool(row["is_active"]),
                custom_label=custom,
            )
        )

    # 数据库里新增的分类（不在 config 中）也要出现在列表里
    for key, row in rows.items():
        if key in config.CATEGORY_LABELS:
            continue
        entries.append(
            CategoryEntry(
                key=key,
                label=row["display_label"] or key,
                sort_order=row["sort_order"] if row["sort_order"] is not None else 100,
                is_active=bool(row["is_active"]),
                custom_label=True,
            )
        )

    return sorted(entries, key=lambda entry: (entry.sort_order, entry.key))


def dynamic_categories(path: Path | None = None) -> list[tuple[str, str]]:
    """数据库里新增的分类（不在代码常量中的那些），供 config 合并。"""
    _ensure(path)
    with _connection(path) as connection:
        rows = connection.execute(
            "SELECT category_key, display_label FROM category_meta"
        ).fetchall()
    return [
        (row["category_key"], row["display_label"] or row["category_key"])
        for row in rows
        if row["category_key"] not in config.CATEGORY_LABELS
    ]


def set_category_meta(
    viewer: User | None,
    key: str,
    *,
    display_label: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
    path: Path | None = None,
) -> None:
    """改一个分类的元数据；`key` 不在既有分类里时视为**新增分类**。

    新增分类至少要给展示名；评分使用 `config.DEFAULT_CATEGORY_WEIGHTS`，
    知识指南与参数档位可以后续再补——不会因此拒绝创建。
    """
    require_admin(viewer)
    is_new = key not in config.CATEGORY_LABELS
    if is_new:
        import re as _re

        if not _re.fullmatch(r"[a-z][a-z0-9_]{1,23}", key or ""):
            raise ProductStoreWriteError(
                "分类键要用小写字母开头，只含小写字母、数字与下划线（2–24 位）。",
                detail=f"key={key}",
            )
        if not (display_label or "").strip():
            raise ProductStoreWriteError(
                "新增分类必须填写展示名。", detail=f"key={key}"
            )

    _ensure(path)
    current = next(
        (entry for entry in category_entries(path) if entry.key == key), None
    )
    label = display_label if display_label is not None else (
        current.label if current and current.custom_label else None
    )
    order = sort_order if sort_order is not None else (
        current.sort_order if current else 0
    )
    active = is_active if is_active is not None else (current.is_active if current else True)

    try:
        with _connection(path) as connection:
            connection.execute(
                """
                INSERT INTO category_meta
                    (category_key, display_label, sort_order, is_active, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(category_key) DO UPDATE SET
                    display_label = excluded.display_label,
                    sort_order    = excluded.sort_order,
                    is_active     = excluded.is_active,
                    updated_by    = excluded.updated_by,
                    updated_at    = excluded.updated_at
                """,
                (
                    key,
                    label or None,
                    int(order),
                    1 if active else 0,
                    viewer.username if viewer else None,
                    _now(),
                ),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise ProductStoreWriteError(detail=f"{type(exc).__name__}: {exc}") from exc


def active_categories(path: Path | None = None) -> list[str]:
    """启用的分类键，按元数据排序。**界面上的分类筛选器用它。**"""
    return [entry.key for entry in category_entries(path) if entry.is_active]


# --------------------------------------------------------------------------
# 品牌字典
# --------------------------------------------------------------------------


def sync_brands(
    products: list[Product] | None = None, *, path: Path | None = None
) -> int:
    """把商品库里出现的品牌补进字典。**已存在的不动它的元数据。**

    这条同步保证了「字典里永远找得到商品用的品牌」，于是界面上录入商品时
    的品牌候选不会缺项。反过来字典**不约束**解析——需求解析仍以商品为准
    （design D11），所以字典里多出来的品牌不会让系统「认识」它。
    """
    _ensure(path)
    if products is None:
        from src import product_store

        products = [p for p in product_store.load_product_records(path) if p.get("brand")]
        names = sorted({str(p.get("brand")) for p in products if p.get("brand")})
    else:
        names = sorted({p.brand for p in products if p.brand})

    if not names:
        return 0

    try:
        with _connection(path) as connection:
            # `DO NOTHING`：已存在的品牌保留原有展示名与排序。
            connection.executemany(
                """
                INSERT INTO brand_meta (brand_name, display_name, sort_order, is_active)
                VALUES (?, NULL, 0, 1)
                ON CONFLICT(brand_name) DO NOTHING
                """,
                [(name,) for name in names],
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise ProductStoreWriteError(detail=f"{type(exc).__name__}: {exc}") from exc
    return len(names)


def brand_entries(
    products: list[Product] | None = None, *, path: Path | None = None
) -> list[BrandEntry]:
    """列出品牌字典。**先同步再读**，所以新品牌不会漏。"""
    sync_brands(products, path=path)

    counts: dict[str, int] = {}
    for product in products or []:
        if product.brand:
            counts[product.brand] = counts.get(product.brand, 0) + 1

    _ensure(path)
    with _connection(path) as connection:
        rows = connection.execute("SELECT * FROM brand_meta").fetchall()

    entries = [
        BrandEntry(
            brand_name=row["brand_name"],
            display_name=row["display_name"] or row["brand_name"],
            sort_order=row["sort_order"] or 0,
            is_active=bool(row["is_active"]),
            product_count=counts.get(row["brand_name"], 0),
        )
        for row in rows
    ]
    return sorted(entries, key=lambda entry: (entry.sort_order, entry.brand_name))


def set_brand_meta(
    viewer: User | None,
    brand_name: str,
    *,
    display_name: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
    path: Path | None = None,
) -> None:
    """改一个品牌的元数据；品牌不在字典里时视为**新增品牌**。"""
    require_admin(viewer)
    _ensure(path)

    name = (brand_name or "").strip()
    if not name:
        raise ProductStoreWriteError("品牌名不能为空。", detail="brand_name")

    with _connection(path) as connection:
        row = connection.execute(
            "SELECT * FROM brand_meta WHERE brand_name = ?", (name,)
        ).fetchone()

    if row is None:
        if not (display_name or "").strip():
            raise ProductStoreWriteError(
                "新增品牌必须填写展示名。", detail=name
            )
        try:
            with _connection(path) as connection:
                connection.execute(
                    """
                    INSERT INTO brand_meta
                        (brand_name, display_name, sort_order, is_active)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        name,
                        display_name.strip(),
                        int(sort_order or 0),
                        1 if (is_active is None or is_active) else 0,
                    ),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise ProductStoreWriteError(detail=f"{type(exc).__name__}: {exc}") from exc
        return

    label = display_name if display_name is not None else row["display_name"]
    order = sort_order if sort_order is not None else (row["sort_order"] or 0)
    active = is_active if is_active is not None else bool(row["is_active"])

    try:
        with _connection(path) as connection:
            connection.execute(
                """
                UPDATE brand_meta
                   SET display_name = ?, sort_order = ?, is_active = ?
                 WHERE brand_name = ?
                """,
                (label, int(order), 1 if active else 0, name),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise ProductStoreWriteError(detail=f"{type(exc).__name__}: {exc}") from exc


# --------------------------------------------------------------------------
# 可见性过滤（读取时叠加，不写商品行）
# --------------------------------------------------------------------------


def _hidden_categories(path: Path | None = None) -> set[str]:
    return {entry.key for entry in category_entries(path) if not entry.is_active}


def _hidden_brands(products: list[Product], path: Path | None) -> set[str]:
    # `brand_entries` 内部先同步再读，所以字典一定覆盖了这批商品的全部品牌
    return {
        entry.brand_name
        for entry in brand_entries(products, path=path)
        if not entry.is_active
    }


def visible_products(
    catalog: Catalog, *, path: Path | None = None
) -> list[Product]:
    """能被搜索与推荐到的商品。

    三件事叠加：商品自身在售、所属分类启用、品牌启用。
    **不改写任何商品记录**——恢复只改元数据那一行。

    **`is_active` 取自传入的 `Catalog` 快照，分类与品牌的启用状态则实时
    读库。** 这不是疏漏：`Catalog` 是「商品集合」的快照，界面侧靠
    `state.get_catalog()` 的缓存键（含商品库文件 mtime）保证它在库被改过
    之后会重新加载——管理员一下架，mtime 变了，下一次渲染就是新的。
    自己在这里再查一次库只会掩盖「快照过期」这件事，而不是解决它。
    """
    hidden_categories = _hidden_categories(path)
    hidden_brands = _hidden_brands(catalog.products, path)
    return [
        product
        for product in catalog.products
        if product.is_active
        and product.category not in hidden_categories
        and product.brand not in hidden_brands
    ]


def visible_catalog(catalog: Catalog, *, path: Path | None = None) -> Catalog:
    """过滤后的**副本**。

    返回副本而不是改 `catalog`：`Catalog` 本身要如实反映数据里有什么，
    `present_categories()` 还压着断言。过滤只影响「谁参与搜索与推荐」。
    """
    return replace(catalog, products=visible_products(catalog, path=path))


def active_brands(
    catalog: Catalog, category: str | None = None, *, path: Path | None = None
) -> list[str]:
    """启用的品牌，可按分类收窄。**界面上的品牌筛选器用它。**"""
    products = [
        product
        for product in catalog.products
        if category is None or product.category == category
    ]
    hidden = {entry.brand_name for entry in brand_entries(products, path=path) if not entry.is_active}
    return sorted({p.brand for p in products if p.brand and p.brand not in hidden})
