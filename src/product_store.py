"""商品仓储层：商品与价格记录的读写。

这一层让 `data_loader` 不必知道数据存在哪儿——它只管把拿到的记录构造成
`Product`。所以 `load_product_records()` 刻意返回**与原来 JSON 记录同形状的
字典**：`data_loader` 里逐条容错、缺字段降级、`Product` 构造那些逻辑
一行都不用改。

价格单独成表（`product_prices`），商品记录里的 `price` 是**从当前价格记录派生**
出来的。没有价格记录时该键为 `None`——沿用既有的「缺数据不猜」处理，
`scoring` 会把依赖价格的维度排除并注明。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src import config
from src.database import connect, init_product_db
from src.errors import ProductStoreReadError, ProductStoreWriteError, ZhigouError

logger = logging.getLogger("zhigou.store")

#: 商品核验状态（定义在 config，避免与 data_loader 之间成环）。
STATUS_VERIFIED = config.STATUS_VERIFIED
STATUS_UNVERIFIED = config.STATUS_UNVERIFIED

#: JSON 列——这几项按品类异构，存文本、读出时解析。
_JSON_COLUMNS = ("specs", "use_cases", "pros", "cons")

#: products 表的列顺序，写入时按它取值。
_PRODUCT_COLUMNS = (
    "product_id",
    "name",
    "brand",
    "category",
    "model",
    "specs",
    "use_cases",
    "pros",
    "cons",
    "data_source",
    "source_url",
    "image_url",
    "data_status",
    "updated_at",
    "is_active",
    "entered_by",
    "entered_at",
)


@dataclass(frozen=True)
class PriceRecord:
    """一条价格记录。"""

    price: float
    currency: str = "CNY"
    source_note: str = ""
    collected_at: str = ""
    verified_at: str | None = None

    @property
    def is_verified(self) -> bool:
        return bool(self.verified_at)


def _connect(path: Path | None):
    """打开**商品库**连接。

    `database.connect()` 不带路径时落到历史库。本模块是商品仓储层，
    处处都该指向 `products.db`——原先靠调用方每次都传路径来保证，
    漏传一次就会把商品表建进历史库（实测踩到过：一条「历史库损坏不该
    影响分析」的用例暴露了它）。
    """
    return connect(path if path is not None else config.products_db_path())


def _ensure_for_read(path: Path | None) -> None:
    """确保表结构就绪；失败时抛**商品库**的读异常。

    `init_db` 是通用的建表入口，它抛的是历史库的异常，文案会说
    「历史记录功能暂不可用」——**那是错的**：坏的是商品库。
    异常类型与文案要指向真正出问题的那一侧，否则用户按提示去查历史，
    而问题在商品数据上。
    """
    try:
        init_product_db(path)
    except ZhigouError as exc:
        raise ProductStoreReadError(detail=exc.detail) from exc


def _ensure_for_write(path: Path | None) -> None:
    """同上，用于写入路径。"""
    try:
        init_product_db(path)
    except ZhigouError as exc:
        raise ProductStoreWriteError(detail=exc.detail) from exc


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _dump(value: Any, *, default: str) -> str:
    """把结构化字段序列化成 JSON 文本。空值落到默认值。"""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        logger.warning("字段无法序列化，已用空值代替：%r", value)
        return default


def _load(text: Any, *, default: Any) -> Any:
    """解析 JSON 文本。坏数据降级成默认值，不整批失败。"""
    if text in (None, ""):
        return default
    if not isinstance(text, str):
        return text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("JSON 列解析失败，已用默认值代替：%.60s", text)
        return default


def _row_to_record(row: sqlite3.Row, price: PriceRecord | None) -> dict[str, Any]:
    """数据库行 → 与原来 JSON 记录同形状的字典。"""
    record: dict[str, Any] = {
        "id": row["product_id"],
        "name": row["name"],
        "brand": row["brand"],
        "category": row["category"],
        "model": row["model"] or "",
        "specs": _load(row["specs"], default={}),
        "use_cases": _load(row["use_cases"], default=[]),
        "pros": _load(row["pros"], default=[]),
        "cons": _load(row["cons"], default=[]),
        "data_source": row["data_source"],
        "source_url": row["source_url"] or "",
        "image_url": row["image_url"] or "",
        "data_status": row["data_status"] or STATUS_UNVERIFIED,
        "updated_at": row["updated_at"],
        # 老库补列时默认 1，所以这里对 NULL 也按「在售」处理。
        "is_active": bool(row["is_active"]) if row["is_active"] is not None else True,
        "entered_by": row["entered_by"] or "",
        "entered_at": row["entered_at"] or "",
        # 价格**派生自价格记录**：没有记录就是 None，交给「缺数据」那条路径处理。
        "price": price.price if price else None,
        "price_currency": price.currency if price else "",
        "price_source": price.source_note if price else "",
        "price_collected_at": price.collected_at if price else "",
        "price_verified_at": price.verified_at if price else "",
    }
    return record


# --------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------


def load_product_records(path: Path | None = None) -> list[dict[str, Any]]:
    """读出全部商品记录（含各自当前价格）。

    Returns:
        与原来 JSON 记录同形状的字典列表。价格缺失时为 `None`。

    Raises:
        ProductStoreReadError: 数据库打不开或读失败。
    """
    _ensure_for_read(path)
    try:
        with _connect(path) as connection:
            rows = connection.execute(
                "SELECT * FROM products ORDER BY product_id"
            ).fetchall()
            price_rows = connection.execute(
                "SELECT * FROM product_prices WHERE is_current = 1"
            ).fetchall()
    except sqlite3.Error as exc:
        raise ProductStoreReadError(
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    prices = {
        row["product_id"]: PriceRecord(
            price=row["price"],
            currency=row["currency"],
            source_note=row["source_note"],
            collected_at=row["collected_at"],
            verified_at=row["verified_at"],
        )
        for row in price_rows
    }
    return [_row_to_record(row, prices.get(row["product_id"])) for row in rows]


def load_dataset_meta(path: Path | None = None) -> dict[str, str]:
    """读数据集级元信息（免责声明、档位说明等）。"""
    _ensure_for_read(path)
    try:
        with _connect(path) as connection:
            rows = connection.execute("SELECT key, value FROM dataset_meta").fetchall()
    except sqlite3.Error as exc:
        raise ProductStoreReadError(detail=f"{type(exc).__name__}: {exc}") from exc
    return {row["key"]: row["value"] for row in rows}


def save_dataset_meta(meta: Mapping[str, Any], *, path: Path | None = None) -> None:
    """写数据集级元信息。空值也写——空也是一种事实（「没有声明」与「没写过」不是一回事）。"""
    rows = [(str(k), str(v or "")) for k, v in meta.items()]
    if not rows:
        return
    _ensure_for_write(path)
    try:
        with _connect(path) as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO dataset_meta (key, value) VALUES (?, ?)", rows
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise ProductStoreWriteError(detail=f"{type(exc).__name__}: {exc}") from exc


def count_products(path: Path | None = None) -> int:
    """库里有多少条商品。种子导入判断「库空不空」用它。"""
    _ensure_for_read(path)
    try:
        with _connect(path) as connection:
            row = connection.execute("SELECT COUNT(*) AS n FROM products").fetchone()
    except sqlite3.Error as exc:
        raise ProductStoreReadError(detail=f"{type(exc).__name__}: {exc}") from exc
    return int(row["n"]) if row else 0


def current_price(product_id: str, path: Path | None = None) -> PriceRecord | None:
    """取某商品的当前价格记录。没有记录返回 None。"""
    _ensure_for_read(path)
    try:
        with _connect(path) as connection:
            row = connection.execute(
                "SELECT * FROM product_prices WHERE product_id = ? AND is_current = 1",
                (product_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise ProductStoreReadError(detail=f"{type(exc).__name__}: {exc}") from exc

    if row is None:
        return None
    return PriceRecord(
        price=row["price"],
        currency=row["currency"],
        source_note=row["source_note"],
        collected_at=row["collected_at"],
        verified_at=row["verified_at"],
    )


# --------------------------------------------------------------------------
# 写入
# --------------------------------------------------------------------------


def _product_values(record: Mapping[str, Any], *, stamp: str) -> tuple[Any, ...]:
    specs = record.get("specs")
    # `is_active` 缺省为**在售**：命令行导入与种子数据都没有这个概念，
    # 不能因为字段没写就把商品判成下架。
    is_active = record.get("is_active")
    return (
        str(record.get("id") or ""),
        str(record.get("name") or ""),
        str(record.get("brand") or ""),
        str(record.get("category") or ""),
        str(record.get("model") or "") or None,
        _dump(specs, default="{}"),
        _dump(record.get("use_cases"), default="[]"),
        _dump(record.get("pros"), default="[]"),
        _dump(record.get("cons"), default="[]"),
        str(record.get("data_source") or ""),
        str(record.get("source_url") or "") or None,
        str(record.get("image_url") or "") or None,
        str(record.get("data_status") or STATUS_UNVERIFIED),
        str(record.get("updated_at") or stamp),
        1 if (is_active is None or is_active) else 0,
        str(record.get("entered_by") or "") or None,
        str(record.get("entered_at") or "") or None,
    )


def _current_price_rows(
    connection: sqlite3.Connection, product_ids: Sequence[str]
) -> dict[str, sqlite3.Row]:
    """一次查出这批商品的当前价格记录。

    逐条查的话，灌 112 条商品就是 112 次查询——种子导入每次测试都要跑一遍，
    这点开销会累积成可感知的测试变慢。
    """
    if not product_ids:
        return {}
    placeholders = ", ".join("?" for _ in product_ids)
    rows = connection.execute(
        f"SELECT * FROM product_prices WHERE is_current = 1 AND product_id IN ({placeholders})",
        list(product_ids),
    ).fetchall()
    return {row["product_id"]: row for row in rows}


def _write_price(
    connection: sqlite3.Connection,
    product_id: str,
    record: Mapping[str, Any],
    *,
    stamp: str,
    existing: sqlite3.Row | None = None,
) -> None:
    """写入价格记录。

    价格**变了**才新增一条并把旧的置为非当前——这样历史可追溯；
    价格没变则只更新现有当前记录的来源与采集时间，不制造无意义的历史。
    """
    raw = record.get("price")
    if raw is None or raw == "":
        return  # 没有价格就是没有价格记录，价格视为缺失

    try:
        price = float(raw)
    except (TypeError, ValueError):
        logger.warning("商品 %s 的价格无法解析，未写入价格记录：%r", product_id, raw)
        return

    currency = str(record.get("currency") or record.get("price_currency") or "CNY")
    source_note = str(record.get("price_source") or record.get("data_source") or "")
    collected_at = str(record.get("price_collected_at") or record.get("updated_at") or stamp)
    verified_at = record.get("price_verified_at") or record.get("verified_at") or None

    if existing is not None and float(existing["price"]) == price:
        connection.execute(
            """UPDATE product_prices
                  SET currency = ?, source_note = ?, collected_at = ?, verified_at = ?
                WHERE id = ?""",
            (currency, source_note, collected_at, verified_at, existing["id"]),
        )
        return

    if existing is not None:
        connection.execute(
            "UPDATE product_prices SET is_current = 0 WHERE product_id = ?",
            (product_id,),
        )

    connection.execute(
        """INSERT INTO product_prices
             (product_id, price, currency, source_note, collected_at, verified_at, is_current)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (product_id, price, currency, source_note, collected_at, verified_at),
    )


def save_products(
    records: Sequence[Mapping[str, Any]],
    *,
    path: Path | None = None,
    stamp: str | None = None,
) -> int:
    """批量写入商品与价格记录。**幂等**：按商品 ID 覆盖，重复执行不产生重复。

    Args:
        records: 与 JSON 记录同形状的字典，至少要有 `id`。
        path: 数据库路径，默认取项目配置。
        stamp: 缺 `updated_at` 时的兜底日期。

    Returns:
        实际写入的商品条数。

    Raises:
        ProductStoreWriteError: 写入失败。
    """
    moment = stamp or _now()
    rows: list[tuple[Any, ...]] = []
    skipped: list[str] = []
    for record in records:
        values = _product_values(record, stamp=moment)
        if not values[0]:
            skipped.append(str(record)[:60])
            continue
        rows.append(values)

    if skipped:
        logger.warning("有 %d 条记录缺少商品 ID，已跳过：%s", len(skipped), skipped[:3])

    placeholders = ", ".join("?" for _ in _PRODUCT_COLUMNS)
    columns = ", ".join(_PRODUCT_COLUMNS)
    # `INSERT OR REPLACE` 在 SQLite 里是**先删后插**——而 products 上开着外键级联，
    # 那一下会把该商品的价格记录一起删掉，价格历史永远累积不起来。
    # 改用 UPSERT：它走的是 UPDATE 路径，不触发级联。
    updates = ", ".join(
        f"{name} = excluded.{name}" for name in _PRODUCT_COLUMNS if name != "product_id"
    )
    upsert = (
        f"INSERT INTO products ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT(product_id) DO UPDATE SET {updates}"
    )

    _ensure_for_write(path)
    try:
        with _connect(path) as connection:
            connection.executemany(upsert, rows)
            ids = [str(r.get("id") or "") for r in records if r.get("id")]
            current = _current_price_rows(connection, ids)
            for record in records:
                product_id = str(record.get("id") or "")
                if product_id:
                    _write_price(
                        connection,
                        product_id,
                        record,
                        stamp=moment,
                        existing=current.get(product_id),
                    )
            connection.commit()
    except sqlite3.Error as exc:
        raise ProductStoreWriteError(
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    logger.info("商品写入完成：%d 条", len(rows))
    return len(rows)


def replace_all(
    records: Sequence[Mapping[str, Any]],
    *,
    path: Path | None = None,
    stamp: str | None = None,
) -> int:
    """清空后写入。价格记录随外键级联删除。用于 `--mode replace`。"""
    _ensure_for_write(path)
    try:
        with _connect(path) as connection:
            connection.execute("DELETE FROM products")
            connection.execute("DELETE FROM product_prices")
            connection.commit()
    except sqlite3.Error as exc:
        raise ProductStoreWriteError(detail=f"{type(exc).__name__}: {exc}") from exc
    return save_products(records, path=path, stamp=stamp)


def set_product_active(
    product_id: str, is_active: bool, *, path: Path | None = None
) -> bool:
    """上下架一件商品。返回是否真的改到了（商品不存在则为 False）。

    上下架只是把 `is_active` 翻过来，**不碰价格记录**——
    下架不是删除，重新上架时价格历史还得在。
    """
    _ensure_for_write(path)
    try:
        with _connect(path) as connection:
            cursor = connection.execute(
                "UPDATE products SET is_active = ? WHERE product_id = ?",
                (1 if is_active else 0, product_id),
            )
            connection.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as exc:
        raise ProductStoreWriteError(detail=f"{type(exc).__name__}: {exc}") from exc


def clear_products(path: Path | None = None) -> None:
    """清空商品、价格与元信息。测试与迁移脚本用。"""
    _ensure_for_write(path)
    try:
        with _connect(path) as connection:
            connection.execute("DELETE FROM products")
            connection.execute("DELETE FROM product_prices")
            connection.execute("DELETE FROM dataset_meta")
            connection.commit()
    except sqlite3.Error as exc:
        raise ProductStoreWriteError(detail=f"{type(exc).__name__}: {exc}") from exc


def seed_from_json(
    seed_path: Path | None = None, *, path: Path | None = None
) -> int:
    """把种子文件导入数据库。

    这是「开箱即用」与「单一数据源」之间的折中：只在**库为空**时调用一次。
    调用方负责判断库空不空——这里不做判断，免得两处各判一次、判出分歧。

    Raises:
        DataFileMissing: 种子文件不存在。
        DataFileInvalid: 种子文件不是合法 JSON。
    """
    from src.data_loader import read_seed
    from src.ingest import fill_derived_fields

    records, meta = read_seed(seed_path)
    # 种子里的记录已经是内部结构，但**派生字段仍要补**——否则
    # 「型号有没有」会取决于数据是种子导入的还是接入脚本写的。
    for record in records:
        if isinstance(record, dict):
            fill_derived_fields(record)
    save_dataset_meta(meta, path=path)
    return save_products(records, path=path)
