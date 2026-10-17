"""分类元数据与品牌字典的测试（变更 §9、§10）。

这个文件里最要紧的一组是最后那几条**不变式测试**：现有 5 处断言把分类键
钉死了（权重表、数据集覆盖、知识指南覆盖、导入映射、解析器类别），
分类元数据必须是「叠加层」而不是「把分类搬进数据库」，否则改一个展示名
就够打红一片。那几条用例存在的意义就是：**以后有人想把分类做成可增删的，
会先在这里撞墙**。
"""

from __future__ import annotations

import sqlite3

import pytest

from src import catalog_meta, config
from src.auth import ROLE_ADMIN, ROLE_USER, User
from src.database import connect
from src.errors import PermissionDenied, ProductStoreWriteError

ADMIN = User(username="root", role=ROLE_ADMIN)
REGULAR = User(username="lisi", role=ROLE_USER)


# --------------------------------------------------------------------------
# §9 分类元数据
# --------------------------------------------------------------------------


def test_categories_come_from_config_not_from_the_table(seeded_products):
    """全集永远是 `config.CATEGORY_LABELS`——表里一条记录都没有时也要列全。"""
    entries = catalog_meta.category_entries()

    assert [entry.key for entry in entries] == list(config.CATEGORY_LABELS)
    assert all(entry.is_active for entry in entries)


def test_display_label_and_order_can_be_changed(seeded_products):
    catalog_meta.set_category_meta(
        ADMIN, "laptop", display_label="笔记本·办公", sort_order=5
    )

    entries = catalog_meta.category_entries()
    laptop = next(entry for entry in entries if entry.key == "laptop")
    assert laptop.label == "笔记本·办公"
    assert laptop.custom_label is True
    # 排序生效：sort_order 大的排在后面
    assert entries[-1].key == "laptop"


def test_deactivating_a_category_hides_its_products(seeded_products):
    from src.recommender import recommend
    from src.demand_parser import Demand

    catalog_meta.set_category_meta(ADMIN, "laptop", is_active=False)

    assert "laptop" not in catalog_meta.active_categories()

    result = recommend(seeded_products, Demand(category="laptop", budget=20000))
    assert result.within_budget == []
    assert result.over_budget == []


def test_deactivating_only_filters_reads_and_leaves_rows_alone(seeded_products):
    """停用不改写任何商品记录——恢复只改元数据那一行。"""
    from src import product_store

    before = sorted(
        (record["id"], record["is_active"])
        for record in product_store.load_product_records()
    )

    catalog_meta.set_category_meta(ADMIN, "laptop", is_active=False)

    after = sorted(
        (record["id"], record["is_active"])
        for record in product_store.load_product_records()
    )
    assert before == after, "停用分类不该动商品自身的记录"


def test_deactivating_a_category_does_not_relist_a_delisted_product(seeded_products):
    """先手工下架 → 停用其分类 → 重新启用分类，该商品**仍处于下架**。

    **停用不是「批量上架/下架」。** 它只叠加一层可见性过滤，不碰商品自身的
    上架状态。否则取关一个分类时，会把管理员手工下架的商品一起放回货架——
    而恢复动作与下架动作本来是两件事。
    """
    from src import product_store
    from src.data_loader import load_catalog

    target = product_store.load_product_records()[0]
    product_store.set_product_active(target["id"], False)

    catalog_meta.set_category_meta(ADMIN, target["category"], is_active=False)
    catalog_meta.set_category_meta(ADMIN, target["category"], is_active=True)

    stored = next(
        record
        for record in product_store.load_product_records()
        if record["id"] == target["id"]
    )
    assert stored["is_active"] is False, "恢复分类不该把手工下架的商品上架"
    assert load_catalog().get(target["id"]).is_active is False


def test_deactivation_does_not_change_the_category_key_set(seeded_products):
    """**本变更最关键的一条约束。**

    `config.CATEGORY_LABELS` 是代码里的常量，元数据表只是覆盖层。
    这条断言要是失败，说明有人把分类做成了可增删的数据。
    """
    catalog_meta.set_category_meta(ADMIN, "phone", is_active=False)

    assert set(config.CATEGORY_LABELS) == {"laptop", "phone"}


def test_present_categories_still_reflects_the_data(seeded_products):
    """**这条是给 `test_acceptance` 那条断言上的保险。**

    过滤一旦下沉到 `Catalog.present_categories`，停用一个分类就会把
    「每个分类键都必须有商品」那条断言打红。所以过滤只能发生在
    `visible_catalog()` 造的副本上。
    """
    from src.data_loader import load_catalog

    catalog_meta.set_category_meta(ADMIN, "laptop", is_active=False)

    fresh = load_catalog()
    assert set(fresh.present_categories()) == set(config.CATEGORY_LABELS)

    visible = catalog_meta.visible_catalog(fresh)
    assert "laptop" not in visible.present_categories()


def test_database_only_category_key_is_listed(seeded_products):
    """通过界面新增的分类会出现在列表里（标签回退为键名）。"""
    catalog_meta.set_category_meta(ADMIN, "toaster", display_label="烤箱")

    entries = catalog_meta.category_entries()
    keys = [entry.key for entry in entries]
    assert "toaster" in keys
    assert next(entry.label for entry in entries if entry.key == "toaster") == "烤箱"


def test_adding_a_new_category_key_requires_a_label(seeded_products):
    """新增分类允许，但必须给展示名，键名也要合法。"""
    with pytest.raises(ProductStoreWriteError) as caught:
        catalog_meta.set_category_meta(ADMIN, "toaster")
    assert "展示名" in caught.value.user_message

    with pytest.raises(ProductStoreWriteError):
        catalog_meta.set_category_meta(ADMIN, "Bad Key!", display_label="坏键")

    catalog_meta.set_category_meta(ADMIN, "toaster", display_label="烤箱")
    assert "toaster" in [entry.key for entry in catalog_meta.category_entries()]


def test_regular_user_cannot_change_category_meta(seeded_products):
    with pytest.raises(PermissionDenied):
        catalog_meta.set_category_meta(REGULAR, "laptop", is_active=False)

    assert "laptop" in catalog_meta.active_categories()


# --------------------------------------------------------------------------
# §10 品牌字典
# --------------------------------------------------------------------------


def test_brand_dictionary_syncs_from_the_products(seeded_products):
    """字典随商品库自动同步：商品里出现的品牌一定在字典里。"""
    entries = catalog_meta.brand_entries(seeded_products.products)

    listed = {entry.brand_name for entry in entries}
    from_products = {p.brand for p in seeded_products.products if p.brand}
    assert from_products <= listed


def test_sync_does_not_overwrite_existing_metadata(seeded_products):
    catalog_meta.brand_entries(seeded_products.products)
    first = next(iter(seeded_products.brands()))

    catalog_meta.set_brand_meta(ADMIN, first, display_name="改过的展示名", sort_order=9)
    catalog_meta.sync_brands(seeded_products.products)

    entry = next(
        item
        for item in catalog_meta.brand_entries(seeded_products.products)
        if item.brand_name == first
    )
    assert entry.display_name == "改过的展示名"
    assert entry.sort_order == 9


def test_deactivating_a_brand_hides_its_products(seeded_products):
    """spec：停用后该品牌的商品不再出现在搜索与推荐中。"""
    from src.demand_parser import Demand
    from src.recommender import recommend

    brand = "轻羽" if "轻羽" in seeded_products.brands() else seeded_products.brands()[0]
    catalog_meta.brand_entries(seeded_products.products)  # 先同步
    catalog_meta.set_brand_meta(ADMIN, brand, is_active=False)

    result = recommend(seeded_products, Demand(category="laptop", budget=20000))
    shown = {item.product.brand for item in result.within_budget + result.over_budget}
    assert brand not in shown


def test_deactivating_a_brand_leaves_product_records_alone(seeded_products):
    from src import product_store

    brand = seeded_products.brands()[0]
    catalog_meta.brand_entries(seeded_products.products)
    before = [
        (record["id"], record["brand"]) for record in product_store.load_product_records()
    ]

    catalog_meta.set_brand_meta(ADMIN, brand, is_active=False)

    after = [
        (record["id"], record["brand"]) for record in product_store.load_product_records()
    ]
    assert before == after


def test_brand_not_in_the_dictionary_cannot_be_edited(seeded_products):
    """字典里没有的品牌改不了——它必须先出现在某个商品上。"""
    with pytest.raises(ProductStoreWriteError):
        catalog_meta.set_brand_meta(ADMIN, "凭空发明的品牌", is_active=False)


def test_a_brand_with_no_products_does_not_make_the_parser_know_it(seeded_products):
    """**解析仍以商品数据为准**，字典不反向约束解析（design D11）。

    在字典里登记一个商品库里没有的品牌，不会让系统「认识」它——
    界面上也写明了这一点，免得管理员登记完发现解析还是识别不出。
    """
    catalog_meta.brand_entries(seeded_products.products)
    with connect(config.products_db_path()) as connection:
        connection.execute(
            "INSERT INTO brand_meta (brand_name, is_active) VALUES (?, 1)",
            ("凭空发明的品牌",),
        )
        connection.commit()

    known = set(seeded_products.brands())
    assert "凭空发明的品牌" not in known, "商品库里没有，解析就不该认识它"

    from src.demand_parser import parse_demand

    demand = parse_demand("想买一台凭空发明的品牌的笔记本", known_brands=known)
    assert demand.brand_preferences == []


def test_display_name_change_does_not_touch_product_records(seeded_products):
    from src import product_store

    brand = seeded_products.brands()[0]
    catalog_meta.brand_entries(seeded_products.products)

    catalog_meta.set_brand_meta(ADMIN, brand, display_name="另一种写法")

    stored = {record["brand"] for record in product_store.load_product_records()}
    assert brand in stored, "商品记录里的品牌写法不该被展示名改掉"


def test_regular_user_cannot_change_brand_meta(seeded_products):
    brand = seeded_products.brands()[0]
    catalog_meta.brand_entries(seeded_products.products)

    with pytest.raises(PermissionDenied):
        catalog_meta.set_brand_meta(REGULAR, brand, is_active=False)


# --------------------------------------------------------------------------
# 既有不变式：分类元数据落地之后，这 5 条必须仍然成立
# --------------------------------------------------------------------------


def test_existing_category_invariants_still_hold(seeded_products):
    """把 5 处断言在此复述一遍，作为「分类仍是代码资产」的护栏。

    元数据表可以被任意改动，这些关系一条都不能松。
    """
    from src import ingest, scoring

    catalog_meta.set_category_meta(ADMIN, "laptop", is_active=False, display_label="改过")

    assert set(scoring._SPEC_RANGES) <= set(config.CATEGORY_LABELS)
    assert set(config.SCORING_WEIGHTS) == set(config.CATEGORY_LABELS)
    assert set(ingest.DEFAULT_CATEGORY_MAP.values()) == set(config.CATEGORY_LABELS)
    assert set(seeded_products.present_categories()) == set(config.CATEGORY_LABELS)

    from src.knowledge.corpus import build_corpus

    docs = build_corpus(config.knowledge_dir(), seeded_products.products)
    covered = {doc.category for doc in docs if doc.category}
    assert set(config.CATEGORY_LABELS) <= covered, "每个分类都得有知识指南"


def test_meta_tables_live_in_the_product_database(seeded_products):
    """分类与品牌是**商品域**的数据，表建在商品库上，不是历史库。

    建错库会让那个文件看起来装着不属于它的东西——这个坑项目里踩过一次。
    """
    with sqlite3.connect(config.products_db_path()) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert {"category_meta", "brand_meta"} <= tables
