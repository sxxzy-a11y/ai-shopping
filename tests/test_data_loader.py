"""商品数据层的测试。

覆盖 spec `product-catalog` 的全部 Scenario：
数据集规模与类别覆盖、演示数据溯源标注、文件缺失/非法/为空的容错、
数据与代码分离（此处体现为「改文件即生效」）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data_loader import load_catalog
from src.errors import DataFileInvalid, DataFileMissing, EmptyCatalog
from src import config


# --------------------------------------------------------------------------
# 数据集本身
# --------------------------------------------------------------------------


def test_dataset_has_at_least_20_products(catalog):
    assert len(catalog) >= 20


def test_dataset_covers_all_configured_categories(catalog):
    """数据集覆盖 config 里登记的全部类别，且不留空类别。"""
    assert set(catalog.present_categories()) == set(config.CATEGORY_LABELS)
    for category in config.CATEGORY_LABELS:
        assert catalog.by_category(category), f"{category} 类别没有商品"


def test_every_product_is_labelled_as_demo_data(catalog):
    """需求硬性要求：不得把模拟数据冒充成真实在售商品。"""
    for product in catalog.products:
        assert "演示" in product.data_source, f"{product.id} 的来源说明未标注演示数据"
        assert product.updated_at, f"{product.id} 缺少数据更新时间"


def test_dataset_itself_carries_a_disclaimer(catalog):
    assert "演示数据" in catalog.disclaimer


def test_products_have_unique_ids_and_vary_within_category(catalog):
    ids = [p.id for p in catalog.products]
    assert len(ids) == len(set(ids))

    for category in catalog.present_categories():
        items = catalog.by_category(category)
        # 价格档位要有区分度（允许两件同价，但不允许整个类别只有一两个价位）
        assert len({p.price for p in items}) >= 3, f"{category} 类别价格缺乏区分度"
        # 不允许出现「仅名称不同、其余完全一致」的重复条目
        fingerprints = [
            (p.price, p.brand, json.dumps(p.specs, sort_keys=True, ensure_ascii=False))
            for p in items
        ]
        assert len(set(fingerprints)) == len(fingerprints), f"{category} 存在重复条目"


def test_all_products_are_complete(catalog):
    """数据集自身应当是完整的；不完整只应出现在外部坏数据上。"""
    assert catalog.incomplete_count == 0
    assert catalog.issues == []


# --------------------------------------------------------------------------
# 种子导入（只在库为空时发生一次）
# --------------------------------------------------------------------------
#
# 商品数据现在存在数据库里，`data/products.json` 只在**库为空时导入一次**。
# 所以文件层的容错——缺失、非法、结构不对——都归到「首次导入」这条路径上。
#
# 库里已经有数据时不会再碰种子文件，因此这些失败只可能发生在第一次。


def _point_seed_at(monkeypatch, tmp_path: Path, payload) -> Path:
    """把种子文件指到临时目录。配合 conftest 给的临时空库用。"""
    seed = tmp_path / "products.json"
    seed.write_text(
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("ZHIGOU_PRODUCTS_PATH", str(seed))
    return seed


def test_missing_seed_raises_domain_error(tmp_path: Path, monkeypatch):
    """库为空且种子文件不存在——这时才该报「商品数据缺失」。"""
    monkeypatch.setenv("ZHIGOU_PRODUCTS_PATH", str(tmp_path / "does-not-exist.json"))
    with pytest.raises(DataFileMissing):
        load_catalog()


def test_invalid_seed_raises_domain_error(tmp_path: Path, monkeypatch):
    _point_seed_at(monkeypatch, tmp_path, "{ this is not json")
    with pytest.raises(DataFileInvalid):
        load_catalog()


def test_empty_seed_raises_empty_catalog(tmp_path: Path, monkeypatch):
    _point_seed_at(monkeypatch, tmp_path, {"products": []})
    with pytest.raises(EmptyCatalog):
        load_catalog()


def test_seed_with_non_array_products_raises(tmp_path: Path, monkeypatch):
    _point_seed_at(monkeypatch, tmp_path, {"products": "oops"})
    with pytest.raises(DataFileInvalid):
        load_catalog()


def test_bare_array_seed_is_accepted(tmp_path: Path, monkeypatch):
    """顶部结构允许是裸数组——导入流程产出的就是这种形式。"""
    _point_seed_at(monkeypatch, tmp_path, [{"id": "B1", "name": "裸数组"}])
    assert load_catalog().get("B1").name == "裸数组"


def test_seed_is_only_imported_once(tmp_path: Path, monkeypatch):
    """库里已有数据时不再导入种子——否则用户录入的商品会被示例数据盖掉。"""
    _point_seed_at(monkeypatch, tmp_path, [{"id": "SEED1", "name": "种子里"}])
    assert load_catalog().get("SEED1") is not None

    # 换一份「种子」，再加载：库非空，不该受影响
    _point_seed_at(monkeypatch, tmp_path, [{"id": "SEED2", "name": "另一份"}])
    catalog = load_catalog()
    assert catalog.get("SEED1") is not None
    assert catalog.get("SEED2") is None


# --------------------------------------------------------------------------
# 单条记录的降级（记录已在库中）
# --------------------------------------------------------------------------


def _seed_db(tmp_path: Path, records: list[dict]) -> Path:
    """把记录写进临时数据库，返回库路径。

    商品数据在库里，所以「坏记录」要造在库里，而不是造在文件里。
    """
    from src import product_store

    db = tmp_path / "products.db"
    product_store.save_products(records, path=db)
    return db


def test_record_missing_specs_is_degraded_not_rejected(tmp_path: Path):
    """一条缺字段的记录不应让整批加载失败——沿用既有的逐条容错。"""
    db = _seed_db(
        tmp_path,
        [
            {
                "id": "A1",
                "name": "完整品",
                "category": "laptop",
                "price": 3000,
                "brand": "甲",
                "specs": {"cpu_tier": 3},
                "use_cases": ["编程"],
                "pros": ["好"],
                "cons": ["坏"],
                "data_source": "演示数据",
                "updated_at": "2026-10-01",
            },
            {"id": "A2", "name": "残次品", "price": 2000},
        ],
    )
    result = load_catalog(db)

    assert len(result) == 2
    assert result.get("A1").is_complete is True

    broken = result.get("A2")
    assert broken.is_complete is False
    assert "specs" in broken.missing_fields
    assert "category" in broken.missing_fields
    assert result.incomplete_count == 1
    assert any("A2" in issue for issue in result.issues)


def test_unparseable_price_has_no_price_record(tmp_path: Path):
    """价格解析不出来时**不建价格记录**——记录里没有记录，价格就是缺失。"""
    from src import product_store

    db = _seed_db(
        tmp_path,
        [
            {
                "id": "P1",
                "name": "价格乱填",
                "category": "phone",
                "price": "三千块",
                "brand": "乙",
                "specs": {"chip_tier": 3},
                "use_cases": ["日常"],
                "pros": ["x"],
                "cons": ["y"],
                "data_source": "演示数据",
                "updated_at": "2026-10-01",
            }
        ],
    )
    assert product_store.current_price("P1", path=db) is None

    product = load_catalog(db).get("P1")
    assert product.price is None
    assert product.price_label == "价格未知"
    assert "price" in product.missing_fields


def test_negative_price_is_rejected_as_unusable(tmp_path: Path):
    """非正数价格在**构造商品时**被挡掉——价格记录可以存，但用的时候不认。"""
    db = _seed_db(tmp_path, [{"id": "P2", "name": "负价", "price": -100}])
    assert load_catalog(db).get("P2").price is None


# --------------------------------------------------------------------------
# 写入侧的门槛（由仓储层承担）
# --------------------------------------------------------------------------


def test_record_without_id_is_skipped_on_write(tmp_path: Path):
    """没有商品 ID 的记录在**写入时**就被跳过——库的主键不接受空 ID。

    这道门槛从加载层挪到了仓储层：以前是「读进来再丢掉」，
    现在是「压根不写进去」，更早也更彻底。
    """
    from src import product_store

    db = tmp_path / "products.db"
    written = product_store.save_products(
        [{"name": "没有 ID"}, {"id": "OK1", "name": "有 ID"}], path=db
    )

    assert written == 1
    assert product_store.count_products(db) == 1
    assert load_catalog(db).get("OK1") is not None


def test_duplicate_id_overwrites_instead_of_duplicating(tmp_path: Path):
    """同一个 ID 写两次是覆盖，不是新增——导入可重复执行而不会产生重复商品。

    唯一性由**主键**保证，比在加载层比对更可靠：那种约束是可以被绕过的，
    主键不行。
    """
    from src import product_store

    db = tmp_path / "products.db"
    product_store.save_products([{"id": "D1", "name": "甲"}], path=db)
    product_store.save_products([{"id": "D1", "name": "乙"}], path=db)

    assert product_store.count_products(db) == 1
    assert load_catalog(db).get("D1").name == "乙"


# --------------------------------------------------------------------------
# 改数据即刻生效
# --------------------------------------------------------------------------


def test_editing_the_database_changes_the_result(tmp_path: Path):
    """对应「修改数据即刻生效」——数据不在代码里，改数据源即可。

    数据源从文件换成了数据库，这条要求本身没变。
    """
    db = _seed_db(tmp_path, [{"id": "E1", "name": "原来的名字"}])
    assert load_catalog(db).get("E1").name == "原来的名字"

    _seed_db(tmp_path, [{"id": "E1", "name": "改过的名字"}])
    assert load_catalog(db).get("E1").name == "改过的名字"
