"""外部数据接入（src/ingest.py 与 scripts/fetch_products.py）的测试。

覆盖：价格/档位/类目解析、记录归一、写前严格校验、合并策略，
以及 CSV 通道的端到端流程（含写盘与加载器冒烟验证）。
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from src import ingest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import fetch_products  # noqa: E402


# --------------------------------------------------------------------------
# 解析工具
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("￥2,999.00", 2999.0),
        ("2999元", 2999.0),
        (3999, 3999.0),
        (" 129.9 ", 129.9),
        ("暂无报价", None),
        (0, None),
        (None, None),
        (True, None),
    ],
)
def test_parse_price(raw, expected):
    assert ingest.parse_price(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("一级", 5), ("一级能效", 5), ("三级", 3), ("3级", 3), (4, 4), ("高效", None)],
)
def test_parse_energy_grade(raw, expected):
    assert ingest.parse_energy_grade(raw) == expected


def test_to_tier_supports_chinese_and_other_scales():
    assert ingest.to_tier("三星") == 3
    assert ingest.to_tier(3) == 3
    # 满分 10 分制折算到 1–5
    assert ingest.to_tier(8, scale_max=10) == 4
    assert ingest.to_tier("未知") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("笔记本电脑", "laptop"),
        ("手机", "phone"),
        ("某个没见过的类目", None),
        (None, None),
    ],
)
def test_normalize_category(raw, expected):
    assert ingest.normalize_category(raw) == expected


@pytest.mark.parametrize("raw", ["家用电器", "冰箱", "母婴用品", "家具", "键盘", "耳机"])
def test_category_map_drops_names_the_catalog_no_longer_covers(raw):
    """随品类收缩退出的类目名不再有映射。

    留着它们不是「多留一手」：那批商品会带着一个没有权重表、没有中文名的
    类别键进库，评分时静默缺维度、界面上显示英文键名——一路不报错。
    """
    assert ingest.normalize_category(raw) is None


def test_category_map_targets_are_the_catalog_categories():
    """类目映射的**目标**必须与商品库类别完全一致。"""
    from src import config

    assert set(ingest.DEFAULT_CATEGORY_MAP.values()) == set(config.CATEGORY_LABELS)


def test_spec_aliases_target_known_specs():
    """参数别名的**目标键**必须都能在 `config.SPEC_LABELS` 里找到中文名。

    别名指向一个没有标签的键，导入时不报错，只是那项参数在界面上
    永远显示原始键名——所以要在这里拦下。
    """
    from src import config

    unknown = set(ingest.SPEC_ALIASES.values()) - set(config.SPEC_LABELS)
    assert unknown == set(), f"这些别名指向了没有中文标签的参数：{sorted(unknown)}"


def test_tier_keys_cover_every_tier_shaped_spec():
    """凡是以 `_tier` 结尾的参数都必须是档位键。

    漏一个的后果是静默的：那个参数不再走 1–5 校验，平台的「九星」
    或者 `True` 会直接进库，评分时被当成一个大数值参与计算。
    """
    from src import config

    tier_shaped = {key for key in config.SPEC_LABELS if key.endswith("_tier")}
    assert tier_shaped <= set(ingest.TIER_KEYS)


def test_spec_aliases_accept_every_chinese_spec_label():
    """每个中文标签都要能被导入时认出来。

    平台导出的是中文参数名，认不出就原样入库——参数在比较表里显示成
    「驱动单元」而另一个商品显示成「driver_mm」，两列对不上，看着像数据缺失。
    """
    from src import config

    for key, label in config.SPEC_LABELS.items():
        assert ingest.SPEC_ALIASES.get(label) == key, label


def test_normalize_category_accepts_custom_mapping():
    mapping = {"Ergonomic Keyboards": "keyboard"}
    assert ingest.normalize_category("ergonomic keyboards", mapping) == "keyboard"


# --------------------------------------------------------------------------
# 记录归一
# --------------------------------------------------------------------------


def test_normalize_record_maps_platform_fields_and_stamps_source():
    raw = {
        "商品ID": "P-1001",
        "标题": "某品牌 轻薄笔记本 14",
        "商品类目": "笔记本电脑",
        "价格": "￥2,999.00",
        "店铺": "某店铺",
        "参数": '{"处理器档位": "四星", "内存": 16, "存储": 512, "未知参数": "x"}',
        "适用场景": "办公、学习",
        "优点": "轻便、续航久",
        "缺点": "接口少",
    }

    record, issues = ingest.normalize_record(
        raw, source_label="来自测试平台", today=date(2026, 10, 14)
    )

    assert issues == []
    assert record is not None
    assert record["id"] == "P-1001"
    assert record["category"] == "laptop"
    assert record["price"] == 2999.0
    assert record["brand"] == "某店铺"
    assert record["specs"]["cpu_tier"] == 4, "「四星」应折算成档位 4"
    assert record["specs"]["ram_gb"] == 16
    assert record["specs"]["storage_gb"] == 512
    assert "未知参数" in record["specs"], "未登记的键原样保留"
    assert record["use_cases"] == ["办公", "学习"]
    assert record["pros"] == ["轻便", "续航久"]
    assert record["data_source"] == "来自测试平台 · 抓取于 2026-10-14"
    assert record["updated_at"] == "2026-10-14"


def test_normalize_record_accepts_semicolon_specs_text():
    raw = {"id": "P1", "name": "x", "category": "手机", "price": 2000,
           "参数": "拍照档位: 三星; 电池容量: 5000; 未知键: 52"}

    record, _ = ingest.normalize_record(raw, source_label="测试")

    assert record is not None
    assert record["specs"]["camera_tier"] == 3, "「三星」应折算成档位 3"
    assert record["specs"]["battery_mah"] == "5000", "非档位项原样存文本"
    assert record["specs"]["未知键"] == "52", "未登记的键原样保留"


def test_normalize_record_without_id_is_skipped():
    record, issues = ingest.normalize_record({"标题": "没有 id"}, source_label="测试")
    assert record is None
    assert any("id" in issue for issue in issues)


def test_normalize_record_reports_but_keeps_bad_price():
    """价格解析失败要报问题；具体是否整批失败由校验层决定。"""
    raw = {"id": "P2", "name": "y", "category": "家电", "price": "面议"}
    record, issues = ingest.normalize_record(raw, source_label="测试")

    assert record is not None and record["price"] is None
    assert any("价格" in issue for issue in issues)


# --------------------------------------------------------------------------
# 写前校验
# --------------------------------------------------------------------------


def _valid_product(**overrides) -> dict:
    product = {
        "id": "OK1",
        "name": "正常商品",
        "category": "laptop",
        "price": 999.0,
        "brand": "品牌",
        "specs": {"cpu_tier": 4},
        "use_cases": ["办公"],
        "pros": ["轻便"],
        "cons": ["略重"],
        "data_source": "来自测试 · 抓取于 2026-10-14",
        "updated_at": "2026-10-14",
    }
    product.update(overrides)
    return product


def test_validate_products_accepts_valid_record():
    assert ingest.validate_products([_valid_product()]) == []


@pytest.mark.parametrize(
    ("overrides", "keyword"),
    [
        ({"id": ""}, "id"),
        ({"name": ""}, "名称"),
        ({"category": "unknown_key"}, "未在 config"),
        ({"price": None}, "价格"),
        ({"price": -1}, "价格"),
        ({"specs": {"cpu_tier": 9}}, "档位"),
        ({"specs": {"cpu_tier": True}}, "档位"),
        ({"pros": "不是列表"}, "pros"),
        ({"data_source": ""}, "来源"),
    ],
)
def test_validate_products_reports_problem(overrides, keyword):
    issues = ingest.validate_products([_valid_product(**overrides)])
    assert any(keyword in issue for issue in issues), issues


def test_validate_products_detects_duplicate_ids():
    issues = ingest.validate_products([_valid_product(), _valid_product()])
    assert any("重复" in issue for issue in issues)


# --------------------------------------------------------------------------
# 合并策略
# --------------------------------------------------------------------------


def test_merge_replaces_in_place_and_appends_new_at_end():
    existing = [
        {"id": "A", "price": 1},
        {"id": "B", "price": 2},
        {"id": "C", "price": 3},
    ]
    incoming = [{"id": "B", "price": 20}, {"id": "D", "price": 4}]

    merged = ingest.merge_products(existing, incoming, mode="merge")

    assert [item["id"] for item in merged] == ["A", "B", "C", "D"]
    assert merged[1]["price"] == 20, "同 id 应被新数据覆盖"
    assert merged[0]["price"] == 1, "未抓到的老商品应保留"


def test_replace_drops_untouched_products():
    existing = [{"id": "A"}]
    incoming = [{"id": "B"}]

    merged = ingest.merge_products(existing, incoming, mode="replace")

    assert [item["id"] for item in merged] == ["B"]


def test_merge_rejects_unknown_mode():
    with pytest.raises(ValueError):
        ingest.merge_products([], [], mode="upsert")


# --------------------------------------------------------------------------
# CSV 通道端到端（不联网）
# --------------------------------------------------------------------------


def test_csv_pipeline_end_to_end(tmp_path: Path):
    csv_path = tmp_path / "export.csv"
    fetch_products.write_csv_template(csv_path)

    # `--out` 现在是**数据库**路径——商品数据落库，不再写 JSON 文件
    out_path = tmp_path / "products.db"
    exit_code = fetch_products.main(
        [
            "--source", "csv",
            "--input", str(csv_path),
            "--out", str(out_path),
            "--source-label", "来自测试平台",
        ]
    )

    assert exit_code == 0

    from src import product_store

    records = product_store.load_product_records(out_path)
    assert len(records) == 1
    product = records[0]
    assert product["id"] == "EX0001"
    assert product["category"] == "laptop"
    assert product["specs"]["cpu_tier"] == 3
    assert product["specs"]["ram_gb"] == 16
    assert product["image_url"].endswith("EX0001.jpg"), "模板里的图片列要一路带到库里"
    # 数据集级说明落在 dataset_meta 表里，与商品记录分开存
    assert product_store.load_dataset_meta(out_path)["source"] == "来自测试平台"


def test_csv_pipeline_dry_run_writes_nothing(tmp_path: Path):
    csv_path = tmp_path / "export.csv"
    fetch_products.write_csv_template(csv_path)
    out_path = tmp_path / "products.db"

    exit_code = fetch_products.main(
        ["--source", "csv", "--input", str(csv_path),
         "--out", str(out_path), "--dry-run"]
    )

    assert exit_code == 0
    assert not out_path.exists()


def test_csv_pipeline_blocks_invalid_data(tmp_path: Path, capsys):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(
        "商品ID,标题,商品类目,价格\nX1,没有价格的商品,家用电器,面议\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "products.db"

    exit_code = fetch_products.main(
        ["--source", "csv", "--input", str(csv_path), "--out", str(out_path)]
    )

    assert exit_code == 1, "校验不过必须拒绝写入"
    assert not out_path.exists(), "校验不过时不该建库"
    assert "未写入" in capsys.readouterr().out


# --------------------------------------------------------------------------
# 型号派生（变更 migrate-products-to-sqlite）
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, brand, expected",
    [
        ("轻羽 AirBook 14", "轻羽", "AirBook 14"),
        ("锋刃 X15 游戏本", "锋刃", "X15"),
        ("键语 K87 机械键盘", "键语", "K87"),
        ("清澜 冰箱 BCD-318", "清澜", "BCD-318"),
        ("磐石 A5", "磐石", "A5"),
        ("清水 Note 12", "清水", "Note 12"),
    ],
)
def test_model_is_derived_when_the_name_has_one(name, brand, expected):
    assert ingest.derive_model(name, brand) == expected


@pytest.mark.parametrize(
    "name, brand",
    [
        # 全中文——这类品类本来就没有型号概念
        ("云梯 可折叠婴儿车", "云梯"),
        ("木言 人体工学椅 网布款", "木言"),
        ("沐光 负离子吹风机", "沐光"),
        # 含拉丁字母但不含数字——「T恤」不是型号
        ("织风 纯棉 T恤", "织风"),
        ("乐章 Studio", "乐章"),
    ],
)
def test_model_is_empty_when_there_is_none(name, brand):
    """**宁可留空也不造错。** 一个错的型号比没有型号更糟——它会被当成事实展示。

    判据是「剩下的部分必须含阿拉伯数字」：这条挡住的正是「纯棉 T恤」这类
    含字母但不是型号的情况。
    """
    assert ingest.derive_model(name, brand) == ""


def test_derive_model_handles_missing_input():
    assert ingest.derive_model("", "") == ""
    assert ingest.derive_model("没有品牌前缀的型号 X1", "") == "没有品牌前缀的型号 X1".replace("没有品牌前缀的型号 ", "")


def test_every_derived_model_contains_a_digit(catalog):
    """全量核对：派生出来的型号**一律含数字**——规则不允许例外。"""
    for product in catalog.products[:20]:
        model = ingest.derive_model(product.name, product.brand)
        if model:
            assert any(ch.isdigit() for ch in model), f"{product.id} 派生出无数字的型号：{model}"
