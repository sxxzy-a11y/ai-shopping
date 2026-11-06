"""商品数据集与评测集的契约测试。

评分是纯规则的，规则的输入是数据。数据一旦出错（缺字段、价格非正、
品类拼错），评分**不会报错**，只会静默失真——比崩溃更难发现。

这个文件把「数据集必须长什么样」写成断言。接入外部商品源时先跑它：
失败说明数据不符合契约，别急着调评分。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_PATH = PROJECT_ROOT / "data" / "products.json"
CASES_PATH = PROJECT_ROOT / "data" / "evaluation" / "cases.json"

#: 商品记录必须具备的字段。`specs` 单独校验，因为它按品类不同而不同。
REQUIRED_FIELDS = ("id", "name", "category", "brand", "model", "price")

#: 品类必须与 `config.SCORING_WEIGHTS` 对齐——多出来的品类不会报错，
#: 只会在评分时找不到权重而被静默跳过。
KNOWN_CATEGORIES = {"laptop", "phone"}

DATA_STATUSES = {"verified", "unverified", "disputed"}


@pytest.fixture(scope="module")
def dataset() -> dict:
    return json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def products(dataset: dict) -> list[dict]:
    return dataset["products"]


@pytest.fixture(scope="module")
def cases() -> list[dict]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


# --------------------------------------------------------------------------
# 商品集
# --------------------------------------------------------------------------


def test_dataset_metadata_is_present(dataset):
    for key in ("dataset_name", "disclaimer", "updated_at", "products"):
        assert key in dataset, f"数据集缺少顶层字段 {key!r}"
    assert dataset["disclaimer"].strip(), "免责声明不能为空"
    assert dataset["updated_at"].strip(), "更新时间不能为空"


def test_product_ids_are_unique(products):
    ids = [product["id"] for product in products]
    duplicates = sorted({pid for pid in ids if ids.count(pid) > 1})

    assert not duplicates, f"商品 id 有重复：{duplicates}"


def test_every_product_has_required_fields(products):
    for product in products:
        missing = [
            key for key in REQUIRED_FIELDS if not str(product.get(key) or "").strip()
        ]
        assert not missing, f"{product.get('id')} 缺少字段 {missing}"


def test_categories_are_known(products):
    unknown = {product["category"] for product in products} - KNOWN_CATEGORIES

    assert not unknown, (
        f"出现未登记的品类 {sorted(unknown)}：`config.SCORING_WEIGHTS` 里没有它，"
        "评分会静默跳过这些商品"
    )


def test_prices_are_positive_numbers(products):
    for product in products:
        price = product["price"]
        assert isinstance(price, (int, float)) and not isinstance(price, bool), (
            f"{product['id']} 的价格不是数字：{price!r}"
        )
        assert price > 0, f"{product['id']} 的价格应大于 0，实际 {price}"


def test_sources_are_recorded(products):
    for product in products:
        url = str(product.get("source_url") or "")
        assert url.startswith("http"), (
            f"{product['id']} 的 source_url 不是 http(s)：{url!r}"
        )
        assert str(product.get("data_source") or "").strip(), (
            f"{product['id']} 缺少 data_source（来源说明）"
        )


def test_data_status_is_known(products):
    for product in products:
        status = product.get("data_status")
        assert status in DATA_STATUSES, (
            f"{product['id']} 的 data_status 不合法：{status!r}，"
            f"应为 {sorted(DATA_STATUSES)} 之一"
        )


def test_specs_are_non_empty_scalar_mappings(products):
    for product in products:
        specs = product.get("specs")
        assert isinstance(specs, dict) and specs, (
            f"{product['id']} 的 specs 应为非空对象"
        )
        for key, value in specs.items():
            assert isinstance(value, (str, int, float, bool)), (
                f"{product['id']} 的 specs[{key!r}] 应为标量，实际 {type(value).__name__}"
            )


def test_pros_and_cons_are_non_empty_lists(products):
    for product in products:
        for field in ("pros", "cons"):
            values = product.get(field)
            assert isinstance(values, list) and values, (
                f"{product['id']} 的 {field} 应为非空列表"
            )
            assert all(str(item).strip() for item in values), (
                f"{product['id']} 的 {field} 里有空项"
            )


# --------------------------------------------------------------------------
# 评测集
# --------------------------------------------------------------------------


def test_evaluation_case_ids_are_unique(cases):
    ids = [case["id"] for case in cases]
    duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})

    assert not duplicates, f"评测用例 id 有重复：{duplicates}"


def test_every_case_has_input_and_expectation(cases):
    for case in cases:
        assert str(case.get("id") or "").strip(), "用例缺少 id"
        assert str(case.get("category") or "").strip(), f"{case['id']} 缺少类别"
        assert str(case.get("input") or "").strip(), f"{case['id']} 缺少输入"
        assert isinstance(case.get("expected"), dict), (
            f"{case['id']} 的 expected 应为对象"
        )
        assert case["expected"], f"{case['id']} 的 expected 不能为空"
        assert str(case.get("origin") or "").strip(), (
            f"{case['id']} 缺少 origin（用例来源）"
        )
