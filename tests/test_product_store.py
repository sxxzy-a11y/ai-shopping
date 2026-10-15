"""商品仓储层的测试。

商品数据从 JSON 文件搬进 SQLite 之后，这一层成了**写入门槛的所在**：
没有 ID 的记录不写、重复 ID 覆盖而不新增、价格单独成记录。

这个文件盯四件事：

1. 商品记录的读写与**幂等**（导入可重复执行）
2. **价格记录**：改价保留历史、同价不造历史、无记录即无价格
3. 数据集级元信息不随种子文件消失
4. **不伪造来源**：字段可空，且空就是空
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import config, database, product_store
from src.errors import ProductStoreReadError


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "products.db"


def _product(pid: str, **overrides) -> dict:
    base = {
        "id": pid,
        "name": f"商品{pid}",
        "brand": "测试品牌",
        "category": "laptop",
        "price": 3000,
        "specs": {"cpu_tier": 3},
        "use_cases": ["办公"],
        "pros": ["优点"],
        "cons": ["缺点"],
        "data_source": "演示数据 · 测试夹具",
        "updated_at": "2026-01-01",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# 表结构
# --------------------------------------------------------------------------


def test_schema_creates_the_product_tables(db: Path):
    database.init_db(db)
    with database.connect(db) as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {"products", "product_prices", "dataset_meta"} <= names


def test_foreign_keys_are_enabled(db: Path):
    """SQLite 默认不启用外键，要逐连接打开——否则级联删除只是摆设。"""
    database.init_db(db)
    with database.connect(db) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_deleting_a_product_cascades_to_its_prices(db: Path):
    product_store.save_products([_product("A1")], path=db)
    with database.connect(db) as connection:
        connection.execute("DELETE FROM products WHERE product_id = 'A1'")
        connection.commit()
        remaining = connection.execute("SELECT COUNT(*) n FROM product_prices").fetchone()
    assert remaining["n"] == 0


# --------------------------------------------------------------------------
# 商品的读写与幂等
# --------------------------------------------------------------------------


def test_saved_product_can_be_read_back(db: Path):
    product_store.save_products([_product("A1")], path=db)
    records = product_store.load_product_records(db)

    assert len(records) == 1
    record = records[0]
    assert record["id"] == "A1"
    assert record["price"] == 3000
    assert record["specs"] == {"cpu_tier": 3}
    assert record["use_cases"] == ["办公"]


def test_saving_twice_overwrites_instead_of_duplicating(db: Path):
    """导入可重复执行——唯一性由主键保证，比在加载层比对更可靠。"""
    product_store.save_products([_product("A1", name="旧名")], path=db)
    product_store.save_products([_product("A1", name="新名")], path=db)

    assert product_store.count_products(db) == 1
    assert product_store.load_product_records(db)[0]["name"] == "新名"


def test_records_without_id_are_skipped(db: Path):
    written = product_store.save_products(
        [{"name": "没有 ID"}, _product("OK1")], path=db
    )
    assert written == 1
    assert product_store.count_products(db) == 1


def test_replace_all_clears_previous_products(db: Path):
    product_store.save_products([_product("A1"), _product("A2")], path=db)
    product_store.replace_all([_product("B1")], path=db)

    ids = {record["id"] for record in product_store.load_product_records(db)}
    assert ids == {"B1"}


def test_empty_database_reads_as_empty_list(db: Path):
    assert product_store.load_product_records(db) == []
    assert product_store.count_products(db) == 0


def test_broken_json_column_degrades_instead_of_raising(db: Path):
    """JSON 列坏了只降级该字段——与文件时代「逐条容错」的立场一致。"""
    product_store.save_products([_product("A1")], path=db)
    with database.connect(db) as connection:
        connection.execute("UPDATE products SET specs = '不是 JSON' WHERE product_id = 'A1'")
        connection.commit()

    record = product_store.load_product_records(db)[0]
    assert record["specs"] == {}


def test_corrupt_database_raises_domain_error(tmp_path: Path):
    broken = tmp_path / "broken.db"
    broken.write_text("这不是一个 SQLite 文件", encoding="utf-8")
    with pytest.raises(ProductStoreReadError):
        product_store.load_product_records(broken)


# --------------------------------------------------------------------------
# 价格记录
# --------------------------------------------------------------------------


def test_price_record_carries_source_and_time(db: Path):
    product_store.save_products(
        [
            _product(
                "A1",
                price=399,
                price_source="某平台公开价目",
                price_collected_at="2026-03-01",
            )
        ],
        path=db,
    )
    record = product_store.current_price("A1", path=db)

    assert record is not None
    assert record.price == 399
    assert record.source_note == "某平台公开价目"
    assert record.collected_at == "2026-03-01"
    assert record.is_verified is False


def test_changing_the_price_keeps_the_old_record(db: Path):
    """价格变了就新增一条、旧的置为非当前——**历史不丢**。

    价格是最需要核实的字段，直接覆盖会让「以前多少钱」永远查不到。
    """
    product_store.save_products([_product("A1", price=100)], path=db)
    product_store.save_products([_product("A1", price=120)], path=db)

    with database.connect(db) as connection:
        rows = connection.execute(
            "SELECT price, is_current FROM product_prices ORDER BY id"
        ).fetchall()

    assert [(row["price"], row["is_current"]) for row in rows] == [(100.0, 0), (120.0, 1)]
    assert product_store.current_price("A1", path=db).price == 120


def test_saving_the_same_price_does_not_add_history(db: Path):
    """价格没变就不制造无意义的历史记录。"""
    product_store.save_products([_product("A1", price=100)], path=db)
    product_store.save_products([_product("A1", price=100)], path=db)

    with database.connect(db) as connection:
        count = connection.execute("SELECT COUNT(*) n FROM product_prices").fetchone()
    assert count["n"] == 1


def test_product_without_price_has_no_price_record(db: Path):
    """没有价格就是没有价格记录——**不是记成 0**。"""
    product_store.save_products([_product("A1", price=None)], path=db)

    assert product_store.current_price("A1", path=db) is None
    assert product_store.load_product_records(db)[0]["price"] is None


def test_unparseable_price_is_not_stored(db: Path):
    product_store.save_products([_product("A1", price="三千块")], path=db)
    assert product_store.current_price("A1", path=db) is None


# --------------------------------------------------------------------------
# 数据集元信息
# --------------------------------------------------------------------------


def test_dataset_meta_round_trip(db: Path):
    product_store.save_dataset_meta(
        {"disclaimer": "这是演示数据", "spec_tier_note": "档位是自定分级"}, path=db
    )
    meta = product_store.load_dataset_meta(db)

    assert meta["disclaimer"] == "这是演示数据"
    assert meta["spec_tier_note"] == "档位是自定分级"


def test_dataset_meta_survives_without_the_seed_file(db: Path):
    """元信息存在库里，**种子文件删掉之后免责声明不能跟着消失**。"""
    product_store.save_dataset_meta({"disclaimer": "演示数据，不得作为购买依据"}, path=db)
    product_store.save_products([_product("A1")], path=db)

    # 模拟种子文件已不在——元信息仍应从库里读得到
    assert "演示数据" in product_store.load_dataset_meta(db)["disclaimer"]


# --------------------------------------------------------------------------
# 不伪造来源（这个变更最容易被误读的地方）
# --------------------------------------------------------------------------


def test_source_fields_may_be_empty_and_stay_empty(db: Path):
    """型号与来源链接允许为空。空就是空——**不填占位文本**。

    「字段有了」不等于「来源有了」。这批数据全是自造的，
    来源就该是空的，核验状态就该是未核验。
    """
    product_store.save_products(
        [_product("A1", model="", source_url="", data_status=config.STATUS_UNVERIFIED)],
        path=db,
    )
    record = product_store.load_product_records(db)[0]

    assert record["model"] == ""
    assert record["source_url"] == ""
    assert record["data_status"] == config.STATUS_UNVERIFIED


def test_verified_status_is_preserved(db: Path):
    """反过来，真标了已核验的也要如实保留——不能一律压成未核验。"""
    product_store.save_products(
        [_product("A1", data_status=config.STATUS_VERIFIED)], path=db
    )
    assert product_store.load_product_records(db)[0]["data_status"] == "verified"


# --------------------------------------------------------------------------
# 种子导入
# --------------------------------------------------------------------------


def test_seed_import_writes_products_and_meta(db: Path, tmp_path: Path):
    import json

    seed = tmp_path / "products.json"
    seed.write_text(
        json.dumps(
            {
                "disclaimer": "演示数据",
                "products": [_product("S1")],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    product_store.seed_from_json(seed, path=db)

    assert product_store.count_products(db) == 1
    assert product_store.load_dataset_meta(db)["disclaimer"] == "演示数据"


def test_seed_missing_raises_domain_error(tmp_path: Path, db: Path):
    from src.errors import DataFileMissing

    with pytest.raises(DataFileMissing):
        product_store.seed_from_json(tmp_path / "nope.json", path=db)


def test_seed_import_also_derives_the_model(db: Path, tmp_path: Path):
    """**两条入口都要派生型号**——种子导入与接入脚本。

    这个不一致实际发生过：迁移脚本派生了型号、自动种子没有，于是
    「型号有没有」取决于数据是怎么进来的。那种不一致最难查——
    数据看着都对，只是有一部分悄悄少了字段。
    """
    import json

    seed = tmp_path / "products.json"
    seed.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "id": "S1",
                        "name": "轻羽 AirBook 14",
                        "brand": "轻羽",
                        "category": "laptop",
                        "price": 3299,
                        "updated_at": "2026-01-01",
                    },
                    {
                        "id": "S2",
                        "name": "织风 纯棉 T恤",
                        "brand": "织风",
                        "category": "apparel",
                        "price": 79,
                        "updated_at": "2026-01-01",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    product_store.seed_from_json(seed, path=db)

    records = {r["id"]: r for r in product_store.load_product_records(db)}
    assert records["S1"]["model"] == "AirBook 14"
    assert records["S2"]["model"] == "", "没有型号概念的品类要留空"


# --------------------------------------------------------------------------
# 建表要按库的范围来
# --------------------------------------------------------------------------


def _table_names(path: Path) -> set[str]:
    import sqlite3

    with sqlite3.connect(path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }


def test_product_database_has_only_product_tables(tmp_path: Path):
    """商品库里**不该有历史表**。

    建表函数一度把知道的表全建在任何一个碰到的库文件上，于是两个库
    都装着彼此的数据——拆库白拆了，而且那份重复数据是过期的，
    谁打开那个文件都会被误导。
    """
    db = tmp_path / "products.db"
    product_store.save_products([_product("A1")], path=db)

    names = _table_names(db)
    assert {"products", "product_prices", "dataset_meta"} <= names
    assert "analysis_history" not in names
    assert "favorites" not in names


def test_history_database_has_only_history_tables(tmp_path: Path):
    from src import database as db_module

    db = tmp_path / "zhigou.db"
    db_module.init_history_db(db)

    names = _table_names(db)
    assert {"analysis_history", "favorites"} <= names
    assert "products" not in names, "历史库里不该出现商品表"
    assert "product_prices" not in names
