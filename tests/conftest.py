"""pytest 共享夹具。

把项目根加入 sys.path，让测试可以直接 `from src.xxx import ...`，
不要求开发机先 pip install 本项目。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import config  # noqa: E402
from src.data_loader import Catalog, Product, load_catalog  # noqa: E402
from src.demand_parser import Demand  # noqa: E402
from src.recommender import recommend  # noqa: E402
from src.report_service import DecisionReport, build_report  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_local_state(tmp_path, monkeypatch):
    """把偏好设置与数据库都指到临时目录。

    没有这道隔离，界面测试会写到开发机真实的 storage/settings.json 和
    storage/zhigou.db，后面所有测试都会读到残留状态——这个坑真的踩过一次
    （设置文件那次），数据库这边是同一个问题，所以一次隔离干净。
    """
    monkeypatch.setenv("ZHIGOU_SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setenv("ZHIGOU_DB_PATH", str(tmp_path / "zhigou.db"))
    # 商品库与历史库分开，测试也要把它隔离到临时目录，
    # 否则测试会往开发机的真实商品库里写。
    monkeypatch.setenv("ZHIGOU_PRODUCTS_DB_PATH", str(tmp_path / "products.db"))

    # 断掉密钥，保证测试**永远不会**真的调外部 API。
    # 开发机上 .env 里放着真密钥，这一步不做的话，跑测试就会消耗额度、
    # 而且测试结果会依赖网络——两头都不该发生。
    monkeypatch.delenv(config.LLM_API_KEY_ENV, raising=False)

    # 管理员凭据同理：开发机上 .env 里可能配着它们，留着会让
    # 「初始管理员」那组用例的结果随开发机的配置而变。
    monkeypatch.delenv(config.ADMIN_USERNAME_ENV, raising=False)
    monkeypatch.delenv(config.ADMIN_PASSWORD_ENV, raising=False)


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    """真实数据集 data/products.json，整个测试会话只加载一次。"""
    return load_catalog()


@pytest.fixture
def db_path(tmp_path) -> Path:
    """历史库文件路径。

    隔离夹具已经把 `ZHIGOU_DB_PATH` 指到临时目录，这里给个显式路径，
    是让用例可以直连同一个文件做 SQL 级断言（例如核对表结构）。

    放在 conftest 而不是某个测试文件里：历史读写、迁移升级两个文件都要用它，
    各定义一份迟早会漂。
    """
    return tmp_path / "storage" / "zhigou.db"


@pytest.fixture
def report(catalog) -> DecisionReport:
    """一份完整报告。历史的写入、去重、越权用例都以它为素材。"""
    demand = Demand(category="laptop", budget=4000, use_cases=["编程"])
    return build_report(catalog, demand, recommend(catalog, demand))


@pytest.fixture
def seeded_products(catalog) -> Catalog:
    """保证**本次用例自己的**商品库里已经有数据。

    为什么需要它：`catalog` 是会话级夹具，它在**第一个**用例的临时目录里
    把种子导入了一次；而隔离夹具给每个用例的 `ZHIGOU_PRODUCTS_DB_PATH`
    都是全新的空库。后面那些用例若直接读商品库（而不是用 `catalog` 对象），
    读到的是空库——报出来是 `list index out of range` 这种看不懂的错。

    需要「改商品库」的用例一律用它，而不是 `catalog`。
    """
    from src import product_store

    if product_store.count_products() == 0:
        product_store.seed_from_json()
    return catalog


@pytest.fixture
def student_laptop_demand(catalog) -> Demand:
    """学生本场景：预算卡在候选中间，预算内与超预算两侧都非空。

    预算**由数据集算出来**，不再写死。需求文档给的原始例子是「预算 3000」，
    但真实数据里最便宜的笔记本要 3519 元——照抄那个数字，全部候选都会落到
    超预算一侧，「预算内」相关的断言于是集体失去意义，而测试仍然是绿的。
    原始例句保留在 `raw_text` 里作为出处，金额随数据集走，两者不打架。
    """
    prices = sorted(p.price for p in catalog.by_category("laptop") if p.price)
    budget = prices[len(prices) // 2]
    return Demand(
        raw_text=(
            f"大学生，预算 {budget:.0f}，主要用于 Python 编程、日常学习和偶尔玩游戏，"
            f"看重性能和性价比，不希望太重"
        ),
        category="laptop",
        budget=budget,
        use_cases=["编程", "学习", "游戏"],
        core_needs=["性能", "性价比"],
        compromises=["可以重一点"],
    )


@pytest.fixture
def wide_budget_laptop_demand(catalog) -> Demand:
    """预算给到「比最贵的还高一点」，让全部笔记本进入预算内，便于检验排序。"""
    prices = [p.price for p in catalog.by_category("laptop") if p.price]
    return Demand(
        category="laptop",
        budget=max(prices) + 1,
        use_cases=["编程", "游戏"],
        core_needs=["性能"],
    )


@pytest.fixture
def minimal_laptop() -> Product:
    """一件字段齐全但没有任何可选参数的笔记本，用于检验缺参降级。"""
    return Product(
        id="TEST-LP",
        name="测试用笔记本",
        category="laptop",
        price=3000,
        brand="测试品牌",
        data_source="演示数据 · 测试夹具",
        updated_at="2026-10-01",
    )
