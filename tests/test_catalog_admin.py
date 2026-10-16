"""商品维护的写入口测试（变更 §8.13–8.19）。

这一层是「界面输入 → 商品库」的关卡，所以断言集中在两件事：
**该拒的拒掉、不该改的不改**。前者防的是脏数据进库，后者防的是
「管理员改一个参数，顺手把来源与核验状态抹了」。
"""

from __future__ import annotations

import pytest

from src import catalog_admin, config, product_store
from src.auth import ROLE_ADMIN, ROLE_USER, User
from src.errors import (
    InvalidImageUrl,
    InvalidSpec,
    PermissionDenied,
    ProductValidationFailed,
)

ADMIN = User(username="root", role=ROLE_ADMIN)
REGULAR = User(username="lisi", role=ROLE_USER)


def _new_product(**overrides) -> dict:
    record = {
        "id": "NEW-LP-001",
        "name": "测试用轻薄本",
        "category": "laptop",
        "brand": "测试品牌",
        "model": "T-100",
        "price": 4999.0,
        "specs": {"cpu_tier": 3, "ram_gb": 16, "weight_kg": 1.4},
        "use_cases": ["办公"],
        "pros": ["轻"],
        "cons": ["接口少"],
        "image_url": "https://example.com/a.jpg",
    }
    record.update(overrides)
    return record


# --------------------------------------------------------------------------
# 8.13 / 8.3 新增：一律未核验、记录录入者
# --------------------------------------------------------------------------


def test_new_product_is_unverified_and_records_its_enterer(seeded_products):
    created = catalog_admin.create_product(ADMIN, _new_product())

    assert created["data_status"] == config.STATUS_UNVERIFIED
    assert created["data_source"] == catalog_admin.ENTRY_DATA_SOURCE
    assert created["entered_by"] == "root"
    assert created["entered_at"]

    stored = next(
        record
        for record in product_store.load_product_records()
        if record["id"] == "NEW-LP-001"
    )
    assert stored["data_status"] == config.STATUS_UNVERIFIED
    assert stored["entered_by"] == "root"


def test_new_product_joins_the_catalog(seeded_products):
    """spec：新增的商品可被搜索、评分，与其他商品同等参与推荐。"""
    from src.data_loader import load_catalog

    catalog_admin.create_product(ADMIN, _new_product())

    reloaded = load_catalog()
    assert reloaded.get("NEW-LP-001") is not None


def test_new_product_participates_in_recommendation(seeded_products):
    """验收 15.6：管理员新增的商品**立刻参与推荐**，与既有商品同等。"""
    from src.data_loader import load_catalog
    from src.demand_parser import Demand
    from src.recommender import recommend

    catalog_admin.create_product(
        ADMIN,
        _new_product(specs={"cpu_tier": 4, "ram_gb": 16, "weight_kg": 1.3}),
    )

    demand = Demand(category="laptop", budget=20000)
    result = recommend(load_catalog(), demand)
    shown = {item.product.id for item in result.within_budget + result.over_budget}

    assert "NEW-LP-001" in shown, "新增的商品应当参与推荐，而不是只能被查到"


def test_regular_user_cannot_create_a_product(seeded_products):
    with pytest.raises(PermissionDenied):
        catalog_admin.create_product(REGULAR, _new_product())

    assert not any(
        record["id"] == "NEW-LP-001" for record in product_store.load_product_records()
    )


# --------------------------------------------------------------------------
# 8.14 非法数据被拦下
# --------------------------------------------------------------------------


def test_tier_out_of_range_is_rejected(seeded_products):
    with pytest.raises(InvalidSpec):
        catalog_admin.create_product(
            ADMIN, _new_product(specs={"cpu_tier": 9})
        )


def test_unknown_spec_key_is_rejected(seeded_products):
    """写错参数名不能被静默接受——那会让这件商品在比较表里缺一行，
    而没人知道为什么。"""
    with pytest.raises(InvalidSpec) as caught:
        catalog_admin.create_product(ADMIN, _new_product(specs={"cpu_tierr": 3}))

    assert "不属于该分类" in caught.value.user_message


def test_numeric_spec_outside_its_range_is_rejected(seeded_products):
    with pytest.raises(InvalidSpec):
        catalog_admin.create_product(ADMIN, _new_product(specs={"ram_gb": 512}))


def test_missing_required_fields_are_rejected(seeded_products):
    with pytest.raises(ProductValidationFailed):
        catalog_admin.create_product(ADMIN, _new_product(name=""))


def test_contradictory_data_is_rejected(seeded_products):
    """界面录入的商品**矛盾就拒收**（而库里已有数据的矛盾只做标记）。

    用的是一致性规则 R3：同一条描述不能既是优点又是缺点。
    """
    with pytest.raises(ProductValidationFailed) as caught:
        catalog_admin.create_product(
            ADMIN, _new_product(pros=["接口少"], cons=["接口少"])
        )

    assert "优点与缺点" in caught.value.user_message

    assert not any(
        record["id"] == "NEW-LP-001" for record in product_store.load_product_records()
    )


# --------------------------------------------------------------------------
# 8.15 图片地址
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "/local/path.png", "example.com/a.jpg"])
def test_image_url_must_be_http(bad):
    with pytest.raises(InvalidImageUrl):
        catalog_admin.validate_image_url(bad)


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_image_url_means_no_image(blank):
    """纯空白按「没有图片」处理。

    `_thumb` 早先只判空不判空白，一个 `"   "` 渲染出了指向当前页面的 `<img>`。
    """
    assert catalog_admin.validate_image_url(blank) == ""


def test_image_url_is_trimmed():
    assert (
        catalog_admin.validate_image_url("  https://example.com/x.png  ")
        == "https://example.com/x.png"
    )


# --------------------------------------------------------------------------
# 8.16 / 8.5 修改：不覆盖来源与核验状态
# --------------------------------------------------------------------------


def test_update_does_not_overwrite_provenance(seeded_products):
    """spec：修改既有商品的参数，来源说明与核验状态保持原样。

    这条正是「界面录入不等于核验」的落地——改一个参数不该把一条带真实
    来源的数据变成「管理员界面录入」。
    """
    target = product_store.load_product_records()[0]
    original_source = target["data_source"]
    original_status = target["data_status"]

    catalog_admin.update_product(ADMIN, target["id"], {"name": "改过的名字"})

    after = next(
        record
        for record in product_store.load_product_records()
        if record["id"] == target["id"]
    )
    assert after["name"] == "改过的名字"
    assert after["data_source"] == original_source
    assert after["data_status"] == original_status
    assert after["entered_by"] == ""  # 本来就不是界面录入的


def test_update_cannot_promote_a_product_to_verified(seeded_products):
    """`data_status` 不在可改字段里——给界面留了这个入口，等于让人
    自己把没核实过的数据标成已核验。"""
    target = product_store.load_product_records()[0]

    catalog_admin.update_product(
        ADMIN, target["id"], {"data_status": config.STATUS_VERIFIED, "name": "x"}
    )

    after = next(
        record
        for record in product_store.load_product_records()
        if record["id"] == target["id"]
    )
    assert after["data_status"] == config.STATUS_UNVERIFIED


def test_update_keeps_image_and_details_editable(seeded_products):
    target = product_store.load_product_records()[0]

    catalog_admin.update_product(
        ADMIN,
        target["id"],
        {
            "image_url": "https://example.com/new.png",
            "pros": ["改过的亮点"],
            "cons": ["改过的不足"],
            "use_cases": ["改过的场景"],
        },
    )

    after = next(
        record
        for record in product_store.load_product_records()
        if record["id"] == target["id"]
    )
    assert after["image_url"] == "https://example.com/new.png"
    assert after["pros"] == ["改过的亮点"]
    assert after["cons"] == ["改过的不足"]
    assert after["use_cases"] == ["改过的场景"]


# --------------------------------------------------------------------------
# 8.18 改价保留历史
# --------------------------------------------------------------------------


def test_changing_the_price_keeps_the_old_record(seeded_products):
    target = next(
        record for record in product_store.load_product_records() if record["price"]
    )
    old_price = target["price"]

    catalog_admin.update_product(ADMIN, target["id"], {"price": old_price + 500})

    current = product_store.current_price(target["id"])
    assert current is not None and current.price == old_price + 500

    from src.database import connect

    with connect(config.products_db_path()) as connection:
        rows = connection.execute(
            "SELECT price, is_current FROM product_prices WHERE product_id = ? ORDER BY id",
            (target["id"],),
        ).fetchall()

    assert len(rows) >= 2, "改价必须新增一条价格记录，而不是覆盖"
    assert rows[-1]["is_current"] == 1
    assert any(row["price"] == old_price for row in rows), "旧价格记录丢了"


# --------------------------------------------------------------------------
# 8.19 上下架
# --------------------------------------------------------------------------


def test_delisted_product_leaves_the_recommendation(seeded_products):
    """spec：下架商品不再出现在搜索与推荐中，历史记录里的引用仍可读。

    下架后要**重新加载数据集**再断言——`Catalog` 是快照，商品库被改过之后
    界面靠缓存键（含库文件 mtime）自动重载，这里照做一遍。
    """
    from src.data_loader import load_catalog
    from src.demand_parser import Demand
    from src.recommender import recommend

    demand = Demand(category="laptop", budget=20000)
    before = recommend(seeded_products, demand)
    assert before.within_budget, "先确认这个条件下本来有推荐"

    victim = before.within_budget[0].product.id
    catalog_admin.set_active(ADMIN, victim, False)

    after = recommend(load_catalog(), demand)
    assert victim not in {item.product.id for item in after.within_budget}


def test_relisting_restores_the_product(seeded_products):
    from src.demand_parser import Demand
    from src.recommender import recommend

    demand = Demand(category="laptop", budget=20000)
    victim = recommend(seeded_products, demand).within_budget[0].product.id

    catalog_admin.set_active(ADMIN, victim, False)
    catalog_admin.set_active(ADMIN, victim, True)

    after = recommend(seeded_products, demand)
    assert victim in {item.product.id for item in after.within_budget}


def test_delisting_does_not_touch_the_price_records(seeded_products):
    """下架不是删除：重新上架时价格历史还得在。"""
    target = next(
        record for record in product_store.load_product_records() if record["price"]
    )

    catalog_admin.set_active(ADMIN, target["id"], False)

    assert product_store.current_price(target["id"]) is not None


def test_history_referencing_a_delisted_product_is_still_readable(catalog, report):
    """spec：下架商品的**历史记录引用仍可读**。"""
    from src import database

    entry_id = database.save_analysis(report, user_id="alice")
    product_id = report.recommendations[0].product_id

    catalog_admin.set_active(ADMIN, product_id, False)

    restored = database.get_analysis(
        entry_id, viewer=User(username="alice", role=ROLE_USER)
    )
    assert restored is not None
    assert product_id in {item.product_id for item in restored.recommendations}


def test_regular_user_cannot_delist_a_product(seeded_products):
    target = product_store.load_product_records()[0]

    with pytest.raises(PermissionDenied):
        catalog_admin.set_active(REGULAR, target["id"], False)

    after = next(
        record
        for record in product_store.load_product_records()
        if record["id"] == target["id"]
    )
    assert after["is_active"] is True
