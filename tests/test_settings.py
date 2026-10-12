"""偏好设置的读写与合并规则测试。

重点在最后两条：偏好**只补空缺、不覆盖用户当次的输入**。
这条顺序搞反了，用户每次手填的内容都会被设置页里的旧偏好盖掉，
而且没有任何报错——属于最难发现的一类问题。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import settings
from src.demand_parser import Demand
from src.settings import UserPreferences


# --------------------------------------------------------------------------
# 读写
# --------------------------------------------------------------------------


def test_missing_file_returns_defaults(tmp_path: Path):
    prefs = settings.load_preferences(tmp_path / "nope.json")

    assert prefs.brand_preferences == []
    assert prefs.price_priority == "none"
    assert prefs.auto_apply is True


@pytest.mark.parametrize(
    "content", ["{ not json", "[]", '"a string"', '{"price_priority": "不存在的取向"}']
)
def test_corrupt_or_wrong_shape_falls_back_to_defaults(tmp_path: Path, content: str):
    """设置文件坏了不该让整个应用起不来——它只影响便利性，不影响正确性。"""
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")

    prefs = settings.load_preferences(path)
    assert prefs.price_priority == "none"


def test_round_trip(tmp_path: Path):
    path = tmp_path / "settings.json"
    original = UserPreferences(
        brand_preferences=["轻羽", "静默"],
        price_priority="performance",
        focus_areas=["便携", "续航"],
        show_over_budget=False,
        auto_apply=True,
    )

    settings.save_preferences(original, path)
    assert settings.load_preferences(path) == original


def test_save_creates_missing_directories(tmp_path: Path):
    path = tmp_path / "deep" / "nested" / "settings.json"
    settings.save_preferences(UserPreferences(), path)
    assert path.is_file()


def test_save_does_not_leave_a_temp_file_behind(tmp_path: Path):
    path = tmp_path / "settings.json"
    settings.save_preferences(UserPreferences(), path)

    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "settings.json"]
    assert leftovers == [], f"留下了临时文件：{leftovers}"


# --------------------------------------------------------------------------
# 偏好折算
# --------------------------------------------------------------------------


def test_effective_core_needs_follows_price_priority():
    assert "性价比" in UserPreferences(price_priority="value").effective_core_needs()
    assert "性能" in UserPreferences(price_priority="performance").effective_core_needs()


def test_default_preferences_inject_nothing():
    """全新安装时不该替用户做任何决定。

    之前 price_priority 默认 "value"，导致从没打开过设置页的用户，
    每次分析都会被自动塞进一个「性价比」核心需求。
    """
    assert UserPreferences().effective_core_needs() == []
    assert UserPreferences(price_priority="none").effective_core_needs() == []


def test_brand_first_priority_adds_no_scoring_need():
    """品牌优先影响的是筛选范围，不是评分维度——品牌本身不是一个评分项。"""
    assert UserPreferences(price_priority="brand").effective_core_needs() == []


def test_focus_areas_are_included_without_duplicates():
    prefs = UserPreferences(price_priority="value", focus_areas=["性价比", "便携"])
    needs = prefs.effective_core_needs()

    assert needs.count("性价比") == 1
    assert "便携" in needs


# --------------------------------------------------------------------------
# 合并规则（关键）
# --------------------------------------------------------------------------


def test_preferences_fill_in_what_the_user_did_not_specify():
    prefs = UserPreferences(brand_preferences=["轻羽"], focus_areas=["便携"])
    demand = Demand(category="laptop", budget=3000)

    merged = settings.apply_preferences(prefs, demand)

    assert merged.brand_preferences == ["轻羽"]
    assert "便携" in merged.core_needs


def test_user_input_wins_over_preferences():
    """核心不变量：偏好只补空缺，不覆盖用户这次填的内容。"""
    prefs = UserPreferences(brand_preferences=["轻羽", "静默"], price_priority="performance")
    demand = Demand(
        category="laptop",
        budget=3000,
        brand_preferences=["墨砚"],
        core_needs=["续航"],
    )

    merged = settings.apply_preferences(prefs, demand)

    assert merged.brand_preferences == ["墨砚"], "用户手填的品牌被偏好盖掉了"
    assert "续航" in merged.core_needs
    assert "性能" in merged.core_needs, "偏好里没有冲突的核心需求应当补进来"


def test_auto_apply_off_leaves_the_demand_untouched():
    prefs = UserPreferences(auto_apply=False, brand_preferences=["轻羽"], focus_areas=["便携"])
    demand = Demand(category="laptop", budget=3000)

    merged = settings.apply_preferences(prefs, demand)

    assert merged is demand or merged == demand
    assert merged.brand_preferences == []
    assert merged.core_needs == []


def test_merging_marks_the_source():
    merged = settings.apply_preferences(UserPreferences(), Demand(category="laptop"))
    assert merged.source == "merged"


def test_merging_does_not_mutate_the_original():
    demand = Demand(category="laptop", core_needs=["续航"])
    settings.apply_preferences(UserPreferences(focus_areas=["便携"]), demand)

    assert demand.core_needs == ["续航"], "原需求对象被就地改掉了"
