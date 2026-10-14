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
# 容错
# --------------------------------------------------------------------------


def test_missing_file_raises_domain_error(tmp_path: Path):
    with pytest.raises(DataFileMissing):
        load_catalog(tmp_path / "does-not-exist.json")


def test_invalid_json_raises_domain_error(tmp_path: Path):
    bad = tmp_path / "products.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(DataFileInvalid):
        load_catalog(bad)


def test_empty_product_list_raises_empty_catalog(tmp_path: Path):
    empty = tmp_path / "products.json"
    empty.write_text(json.dumps({"products": []}), encoding="utf-8")
    with pytest.raises(EmptyCatalog):
        load_catalog(empty)


def test_non_array_products_field_raises(tmp_path: Path):
    bad = tmp_path / "products.json"
    bad.write_text(json.dumps({"products": "oops"}), encoding="utf-8")
    with pytest.raises(DataFileInvalid):
        load_catalog(bad)


# --------------------------------------------------------------------------
# 单条记录的降级
# --------------------------------------------------------------------------


def _write(tmp_path: Path, payload) -> Path:
    target = tmp_path / "products.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return target


def test_record_missing_specs_is_degraded_not_rejected(tmp_path: Path):
    """一条缺 spec 的记录不应让整批加载失败。"""
    path = _write(
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
    result = load_catalog(path)

    assert len(result) == 2
    assert result.get("A1").is_complete is True

    broken = result.get("A2")
    assert broken.is_complete is False
    assert "specs" in broken.missing_fields
    assert "category" in broken.missing_fields
    assert result.incomplete_count == 1
    assert any("A2" in issue for issue in result.issues)


def test_unparseable_price_counts_as_missing(tmp_path: Path):
    path = _write(
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
    product = load_catalog(path).get("P1")

    assert product.price is None
    assert product.price_label == "价格未知"
    assert "price" in product.missing_fields


def test_negative_price_is_rejected_as_unusable(tmp_path: Path):
    path = _write(tmp_path, [{"id": "P2", "name": "负价", "price": -100}])
    product = load_catalog(path).get("P2")
    assert product.price is None


def test_record_without_id_is_skipped(tmp_path: Path):
    path = _write(tmp_path, [{"name": "没有 ID"}, {"id": "OK1", "name": "有 ID"}])
    result = load_catalog(path)

    assert len(result) == 1
    assert result.products[0].id == "OK1"
    assert any("缺少 id" in issue for issue in result.issues)


def test_duplicate_id_is_skipped(tmp_path: Path):
    path = _write(
        tmp_path,
        [{"id": "D1", "name": "甲"}, {"id": "D1", "name": "乙"}],
    )
    result = load_catalog(path)

    assert len(result) == 1
    assert result.products[0].name == "甲"
    assert any("重复" in issue for issue in result.issues)


def test_bare_array_top_level_is_accepted(tmp_path: Path):
    path = _write(tmp_path, [{"id": "B1", "name": "裸数组"}])
    assert load_catalog(path).get("B1").name == "裸数组"


def test_editing_the_file_changes_the_result(tmp_path: Path):
    """对应「修改数据文件即刻生效」——数据不在代码里，改文件即可。"""
    original = _write(tmp_path, [{"id": "E1", "name": "原来的名字"}])
    assert load_catalog(original).get("E1").name == "原来的名字"

    original.write_text(
        json.dumps([{"id": "E1", "name": "改过的名字"}], ensure_ascii=False),
        encoding="utf-8",
    )
    assert load_catalog(original).get("E1").name == "改过的名字"
