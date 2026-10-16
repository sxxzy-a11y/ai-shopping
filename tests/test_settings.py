"""偏好设置的读写与合并规则测试。

偏好现在**按用户存在数据库里**（`user_preferences` 表）。相关的不变量有三条：

1. 读写只管自己那个用户——甲设了「价格优先」，乙的分析不能被带着走
2. 「新用户初始模板」只影响**没有记录**的用户，且不会被写进库
3. 单用户时期的 `settings.json` 要能被收编成模板，且**先写模板再改名**

最后两条仍是合并规则的关键：偏好**只补空缺、不覆盖用户当次的输入**。
这条顺序搞反了，用户每次手填的内容都会被设置页里的旧偏好盖掉，
而且没有任何报错——属于最难发现的一类问题。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import database, settings
from src.auth import ROLE_USER, User
from src.demand_parser import Demand
from src.errors import PermissionDenied
from src.settings import UserPreferences

ALICE = User(username="alice", role=ROLE_USER)
BOB = User(username="bob", role=ROLE_USER)


# --------------------------------------------------------------------------
# 读写（按用户）
# --------------------------------------------------------------------------


def test_user_without_a_record_gets_defaults():
    prefs = settings.load_preferences(ALICE)

    assert prefs.ai_enhanced is True
    assert prefs.price_priority == "none"
    assert prefs.auto_apply is True


def test_logged_out_gets_defaults_without_touching_the_database():
    """未登录不该读库——读了也不知道该读谁的，而默认值永远可用。"""
    assert settings.load_preferences(None) == settings.default_preferences()


def test_round_trip():
    original = UserPreferences(
        price_priority="performance",
        show_over_budget=False,
        auto_apply=True,
    )

    settings.save_preferences(ALICE, original)
    assert settings.load_preferences(ALICE) == original


def test_preferences_are_isolated_between_users():
    """**本变更最要紧的一条**：一个人的设置不能作用在另一个人身上。

    旧实现是一份全局的 `settings.json`——甲设了「性能优先」，
    乙提交同样的需求，拿到的是按甲的偏好算出来的推荐。这不报错，
    只是把别人的偏好当成自己的。
    """
    settings.save_preferences(ALICE, UserPreferences(price_priority="performance"))
    settings.save_preferences(BOB, UserPreferences(price_priority="value"))

    assert settings.load_preferences(ALICE).price_priority == "performance"
    assert settings.load_preferences(BOB).price_priority == "value"


def test_one_users_save_does_not_touch_another():
    settings.save_preferences(BOB, UserPreferences(price_priority="value"))

    alice_before = settings.load_preferences(ALICE)
    settings.save_preferences(ALICE, UserPreferences(price_priority="performance"))

    assert settings.load_preferences(BOB).price_priority == "value"
    assert alice_before.price_priority == "none"


def test_saving_without_a_user_is_refused():
    """偏好必须有归属。静默丢掉一次「保存」比报错更糟。"""
    with pytest.raises(PermissionDenied):
        settings.save_preferences(None, UserPreferences())


@pytest.mark.parametrize(
    "content", ["{ not json", "[]", '"a string"', '{"price_priority": "不存在的取向"}']
)
def test_corrupt_stored_json_falls_back_to_defaults(content: str):
    """库里那段 JSON 坏了不该让整个应用起不来——偏好只影响便利性。"""
    settings.save_preferences(ALICE, UserPreferences())
    with database.connect() as connection:
        connection.execute(
            "UPDATE user_preferences SET prefs_json = ? WHERE user_id = ?",
            (content, ALICE.username),
        )
        connection.commit()

    assert settings.load_preferences(ALICE).price_priority == "none"


def test_unknown_keys_in_stored_json_are_ignored():
    """旧版本留下的 `brand_preferences` / `focus_areas` 不该让解析失败。"""
    settings.save_preferences(ALICE, UserPreferences())
    with database.connect() as connection:
        connection.execute(
            "UPDATE user_preferences SET prefs_json = ? WHERE user_id = ?",
            (json.dumps({"brand_preferences": ["轻羽"], "ai_enhanced": False}), ALICE.username),
        )
        connection.commit()

    prefs = settings.load_preferences(ALICE)
    assert prefs.ai_enhanced is False
    assert not hasattr(prefs, "brand_preferences") or prefs.brand_preferences == []


# --------------------------------------------------------------------------
# 单用户时期的 settings.json → 新用户初始模板
# --------------------------------------------------------------------------


def test_legacy_settings_file_becomes_the_template(tmp_path: Path):
    """单用户时期那份偏好成为**新用户的初始值**，且原文件改名保留。

    不把它归给初始管理员——那份偏好是谁设的我们并不知道，
    编一个归属不如让它成为默认值（design D6）。
    """
    legacy = tmp_path / "settings.json"
    legacy.write_text(
        json.dumps({"price_priority": "value", "show_over_budget": False}),
        encoding="utf-8",
    )

    backup = settings.adopt_legacy_settings_file(legacy)

    assert backup == tmp_path / "settings.json.bak"
    assert backup.is_file(), "原文件必须改名保留，不能删掉"
    assert not legacy.exists()

    # 新用户（库里没有任何记录）拿到的是模板里的值
    fresh = settings.load_preferences(ALICE, path=None)
    assert fresh.price_priority == "value"
    assert fresh.show_over_budget is False


def test_adopting_the_legacy_file_twice_is_harmless(tmp_path: Path):
    """幂等：文件已经改过名了，第二次什么都不做。"""
    legacy = tmp_path / "settings.json"
    legacy.write_text('{"price_priority": "value"}', encoding="utf-8")

    settings.adopt_legacy_settings_file(legacy)
    assert settings.adopt_legacy_settings_file(legacy) is None


def test_adopting_a_corrupt_legacy_file_yields_default_template(tmp_path: Path):
    """坏掉的旧文件也要能被收编——否则它会永远躺在那里，没人处理。"""
    legacy = tmp_path / "settings.json"
    legacy.write_text("{ 这不是 json", encoding="utf-8")

    settings.adopt_legacy_settings_file(legacy)

    assert (tmp_path / "settings.json.bak").is_file()
    assert settings.load_preferences(ALICE).price_priority == "none"


def test_template_does_not_override_an_existing_users_record():
    """模板只管新用户。已经有记录的用户不该被模板改写。"""
    settings.save_preferences(ALICE, UserPreferences(price_priority="performance"))
    database.write_template_json(json.dumps({"price_priority": "value"}))

    assert settings.load_preferences(ALICE).price_priority == "performance"


def test_reading_a_new_user_does_not_write_a_row():
    """读偏好不留副作用——没保存过就是没保存过。"""
    assert settings.load_preferences(ALICE).price_priority == "none"
    assert database.read_preferences_json(ALICE.username) is None


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


def test_ai_enhanced_defaults_to_on_and_can_be_turned_off():
    prefs = UserPreferences()
    assert prefs.ai_enhanced is True
    assert UserPreferences(ai_enhanced=False).ai_enhanced is False


# --------------------------------------------------------------------------
# 合并规则（关键）
# --------------------------------------------------------------------------


def test_preferences_fill_in_what_the_user_did_not_specify():
    prefs = UserPreferences(price_priority="value")
    demand = Demand(category="laptop", budget=3000)

    merged = settings.apply_preferences(prefs, demand)

    assert "性价比" in merged.core_needs
    assert merged.brand_preferences == [], "品牌偏好设置项已移除，不再注入品牌"


def test_user_input_wins_over_preferences():
    """核心不变量：偏好只补空缺，不覆盖用户这次填的内容。"""
    prefs = UserPreferences(price_priority="performance")
    demand = Demand(
        category="laptop",
        budget=3000,
        core_needs=["续航"],
    )

    merged = settings.apply_preferences(prefs, demand)

    assert "续航" in merged.core_needs, "用户已填的核心需求必须保留"
    assert "性能" in merged.core_needs, "偏好里没有冲突的核心需求应当补进来"


def test_auto_apply_off_leaves_the_demand_untouched():
    prefs = UserPreferences(auto_apply=False, price_priority="value")
    demand = Demand(category="laptop", budget=3000)

    merged = settings.apply_preferences(prefs, demand)

    assert merged is demand or merged == demand
    assert merged.core_needs == []


def test_merging_marks_the_source():
    merged = settings.apply_preferences(UserPreferences(), Demand(category="laptop"))
    assert merged.source == "merged"


def test_merging_does_not_mutate_the_original():
    demand = Demand(category="laptop", core_needs=["续航"])
    settings.apply_preferences(UserPreferences(price_priority="value"), demand)

    assert demand.core_needs == ["续航"], "原需求对象被就地改掉了"
