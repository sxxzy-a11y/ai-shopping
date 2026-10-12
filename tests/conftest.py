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

from src.data_loader import Catalog, Product, load_catalog  # noqa: E402
from src.demand_parser import Demand  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """把偏好设置文件指到临时目录。

    没有这道隔离，设置页的测试会写到开发机真实的 storage/settings.json，
    后面所有测试都会读到那些残留偏好——这个坑真的踩过一次。
    """
    monkeypatch.setenv("ZHIGOU_SETTINGS_PATH", str(tmp_path / "settings.json"))


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    """真实数据集 data/products.json，整个测试会话只加载一次。"""
    return load_catalog()


@pytest.fixture
def student_laptop_demand() -> Demand:
    """需求文档里给的那个原始例子（预算 3000 的笔记本）。"""
    return Demand(
        raw_text="大学生，预算 3000，主要用于 Python 编程、日常学习和偶尔玩游戏，看重性能和性价比，不希望太重",
        category="laptop",
        budget=3000,
        use_cases=["编程", "学习", "游戏"],
        core_needs=["性能", "性价比"],
        compromises=["可以重一点"],
    )


@pytest.fixture
def wide_budget_laptop_demand() -> Demand:
    """预算放宽到 8000，让全部笔记本都进入预算内，便于检验排序逻辑。"""
    return Demand(
        category="laptop",
        budget=8000,
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
