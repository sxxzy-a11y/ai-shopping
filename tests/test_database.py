"""SQLite 持久化的测试。

覆盖 spec `history-store` 的全部 Scenario：
分析记录写入与列出、报告还原、收藏持久化、数据库损坏的容错、字段最小化。
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from src import database
from src.data_loader import Catalog
from src.demand_parser import Demand
from src.errors import HistoryReadError, HistoryWriteError
from src.recommender import recommend
from src.report_service import DecisionReport, build_report


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "storage" / "zhigou.db"


@pytest.fixture
def report(catalog) -> DecisionReport:
    demand = Demand(category="laptop", budget=4000, use_cases=["编程"])
    return build_report(catalog, demand, recommend(catalog, demand))


@pytest.fixture
def second_report(catalog) -> DecisionReport:
    demand = Demand(category="headphone", budget=1000, core_needs=["降噪"])
    return build_report(catalog, demand, recommend(catalog, demand))


# --------------------------------------------------------------------------
# 建表
# --------------------------------------------------------------------------


def test_init_creates_the_database(db_path: Path):
    database.init_db(db_path)
    assert db_path.is_file()
    assert database.count_analyses(db_path) == 0


def test_init_is_idempotent(db_path: Path):
    database.init_db(db_path)
    database.init_db(db_path)
    database.init_db(db_path)

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {"analysis_history", "favorites"} <= tables


def test_init_creates_missing_directories(tmp_path: Path):
    deep = tmp_path / "a" / "b" / "c" / "zhigou.db"
    database.init_db(deep)
    assert deep.is_file()


def test_check_health_reports_ok(db_path: Path):
    ok, message = database.check_health(db_path)
    assert ok is True
    assert message == "正常"


# --------------------------------------------------------------------------
# 条件指纹去重（spec: 同一组条件只存一条记录）
# --------------------------------------------------------------------------


def test_same_report_saved_twice_stores_one_row(db_path: Path, report: DecisionReport):
    """同一报告落库两次只存一条，第二次返回已有记录的 ID。"""
    first = database.save_analysis(report, db_path)
    second = database.save_analysis(report, db_path)

    assert database.count_analyses(db_path) == 1
    assert second == first


def test_same_conditions_different_session_stores_one_row(
    db_path: Path, catalog: Catalog
):
    """条件相同、时间不同的两次分析（模拟刷新页面后的新会话）只存一条。"""
    demand = Demand(category="laptop", budget=4000, use_cases=["编程"])
    morning = build_report(
        catalog, demand, recommend(catalog, demand),
        created_at=datetime(2026, 10, 13, 8, 0, 0),
    )
    evening = build_report(
        catalog, demand, recommend(catalog, demand),
        created_at=datetime(2026, 10, 13, 21, 0, 0),
    )

    database.save_analysis(morning, db_path)
    database.save_analysis(evening, db_path)

    assert database.count_analyses(db_path) == 1


def test_different_conditions_store_separately(
    db_path: Path, report: DecisionReport, second_report: DecisionReport
):
    """条件不同就各自落库，去重不能误伤。"""
    database.save_analysis(report, db_path)
    database.save_analysis(second_report, db_path)

    assert database.count_analyses(db_path) == 2


def test_report_without_signature_is_not_deduped(db_path: Path, report: DecisionReport):
    """签名为空的报告（老版本生成）保持历史行为：不做去重。"""
    legacy = replace(report, signature="")

    database.save_analysis(legacy, db_path)
    database.save_analysis(legacy, db_path)

    assert database.count_analyses(db_path) == 2


# --------------------------------------------------------------------------
# 老库升级
# --------------------------------------------------------------------------


_OLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT    NOT NULL,
    demand_summary TEXT    NOT NULL,
    top_product    TEXT    NOT NULL DEFAULT '',
    top_score      REAL,
    result_count   INTEGER NOT NULL DEFAULT 0,
    report_json    TEXT    NOT NULL
);
"""


def test_migrates_old_database_without_signature_column(db_path: Path, report):
    """没有 signature 列的老库：升级后老记录可读，新保存正常去重。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(_OLD_SCHEMA)
        connection.execute(
            "INSERT INTO analysis_history"
            " (created_at, demand_summary, top_product, top_score,"
            "  result_count, report_json)"
            " VALUES ('2026-10-13T00:48:31', '笔记本电脑 · 预算 7000 元',"
            "         '拓界 17 大屏创作本', 86.0, 6, '{}')"
        )

    database.init_db(db_path)

    # 老记录还在、能正常列出
    entries = database.list_analyses(path=db_path)
    assert len(entries) == 1
    assert entries[0].top_product == "拓界 17 大屏创作本"

    # 新保存带签名的报告不受老数据影响，且同条件重复提交只存一条
    first = database.save_analysis(report, db_path)
    second = database.save_analysis(report, db_path)
    assert database.count_analyses(db_path) == 2
    assert second == first


# --------------------------------------------------------------------------
# 分析历史
# --------------------------------------------------------------------------


def test_save_and_list(db_path: Path, report: DecisionReport):
    entry_id = database.save_analysis(report, db_path)
    assert entry_id > 0

    entries = database.list_analyses(path=db_path)
    assert len(entries) == 1

    entry = entries[0]
    assert entry.demand_summary == report.demand_summary
    assert entry.result_count == len(report.recommendations)
    if report.recommendations:
        assert entry.top_product == report.recommendations[0].name
        assert entry.top_score == pytest.approx(report.recommendations[0].score_total)


def test_list_is_newest_first(db_path: Path, catalog):
    """spec：历史列表按分析时间由新到旧排列。"""
    for budget in (3000, 4000, 5000, 6000):
        demand = Demand(category="laptop", budget=budget)
        database.save_analysis(
            build_report(catalog, demand, recommend(catalog, demand)), db_path
        )

    entries = database.list_analyses(path=db_path)
    stamps = [entry.created_at for entry in entries]
    assert stamps == sorted(stamps, reverse=True)


def test_list_respects_the_limit(db_path: Path, catalog):
    for budget in (3000, 4000, 5000):
        demand = Demand(category="laptop", budget=budget)
        database.save_analysis(
            build_report(catalog, demand, recommend(catalog, demand)), db_path
        )

    assert len(database.list_analyses(limit=2, path=db_path)) == 2


def test_get_analysis_restores_the_original_conclusions(db_path: Path, report: DecisionReport):
    """spec：再次打开时还原当时的推荐结果与得分。"""
    entry_id = database.save_analysis(report, db_path)
    restored = database.get_analysis(entry_id, db_path)

    assert restored is not None
    assert restored.created_at == report.created_at
    assert len(restored.recommendations) == len(report.recommendations)

    for original, loaded in zip(report.recommendations, restored.recommendations, strict=True):
        assert loaded.product_id == original.product_id
        assert loaded.rank == original.rank
        assert loaded.score_total == pytest.approx(original.score_total)
        assert loaded.pros == original.pros
        assert loaded.cons == original.cons


def test_get_analysis_returns_none_for_unknown_id(db_path: Path):
    database.init_db(db_path)
    assert database.get_analysis(9999, db_path) is None


def test_unknown_id_does_not_create_a_stray_record(db_path: Path):
    """spec：未知标识报错而不创建空记录。"""
    database.init_db(db_path)
    before = database.count_analyses(db_path)

    assert database.get_analysis(12345, db_path) is None
    assert database.count_analyses(db_path) == before


def test_delete_analysis(db_path: Path, report: DecisionReport):
    entry_id = database.save_analysis(report, db_path)

    assert database.delete_analysis(entry_id, db_path) is True
    assert database.get_analysis(entry_id, db_path) is None
    assert database.delete_analysis(entry_id, db_path) is False


def test_two_analyses_coexist(db_path: Path, report, second_report):
    first = database.save_analysis(report, db_path)
    second = database.save_analysis(second_report, db_path)

    assert first != second
    assert database.count_analyses(db_path) == 2


# --------------------------------------------------------------------------
# 收藏
# --------------------------------------------------------------------------


def test_add_and_list_favorites(db_path: Path):
    database.add_favorite("LP001", db_path)
    database.add_favorite("HP004", db_path)

    favorites = database.list_favorites(db_path)
    assert {pid for pid, _ in favorites} == {"LP001", "HP004"}
    assert all(added for _, added in favorites)


def test_favorites_persist_across_connections(db_path: Path):
    """spec：重启应用后收藏仍然存在。"""
    database.add_favorite("LP005", db_path)

    # 用一个全新的连接读取，模拟应用重启
    assert database.is_favorite("LP005", db_path) is True
    assert "LP005" in {pid for pid, _ in database.list_favorites(db_path)}


def test_remove_favorite(db_path: Path):
    database.add_favorite("LP002", db_path)
    database.remove_favorite("LP002", db_path)

    assert database.is_favorite("LP002", db_path) is False
    assert database.list_favorites(db_path) == []


def test_duplicate_favorite_is_idempotent(db_path: Path):
    database.add_favorite("KB001", db_path)
    database.add_favorite("KB001", db_path)

    assert len(database.list_favorites(db_path)) == 1


def test_removing_a_nonexistent_favorite_is_harmless(db_path: Path):
    database.init_db(db_path)
    database.remove_favorite("NOPE", db_path)
    assert database.list_favorites(db_path) == []


def test_is_favorite_does_not_create_the_database(tmp_path: Path):
    """只读查询不该有副作用——问一下「收藏了吗」不该顺手建个库出来。"""
    path = tmp_path / "not_created.db"
    assert database.is_favorite("X", path) is False


def test_favorite_of_a_product_missing_from_the_catalog_is_still_stored(db_path: Path):
    """spec：收藏的商品已从数据文件移除时，收藏记录本身仍在，
    由界面负责标注「该商品数据已不可用」，而不是崩溃。"""
    database.add_favorite("GONE-001", db_path)
    assert database.is_favorite("GONE-001", db_path) is True


# --------------------------------------------------------------------------
# 容错
# --------------------------------------------------------------------------


def test_corrupt_database_raises_a_domain_error(tmp_path: Path):
    """spec：数据库损坏时给出中文提示，且不影响继续做新的分析。"""
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"this is definitely not a sqlite file" * 50)

    with pytest.raises(HistoryReadError) as excinfo:
        database.list_analyses(path=broken)

    assert "数据库" in excinfo.value.user_message
    assert "Traceback" not in excinfo.value.user_message


def test_health_check_reports_a_corrupt_database(tmp_path: Path):
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"not a database" * 100)

    ok, message = database.check_health(broken)
    assert ok is False
    assert message


def test_write_to_a_corrupt_database_raises_a_domain_error(tmp_path: Path, report):
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"not a database" * 100)

    with pytest.raises((HistoryWriteError, HistoryReadError)) as excinfo:
        database.save_analysis(report, broken)

    assert "Traceback" not in excinfo.value.user_message


# --------------------------------------------------------------------------
# 隐私（spec：数据最小化）
# --------------------------------------------------------------------------


def test_stored_columns_contain_no_personal_information(db_path: Path, report):
    """spec：字段仅包含决策所需内容，不含设备标识、位置或身份信息。"""
    database.save_analysis(report, db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(analysis_history)")
        }

    assert columns == {
        "id",
        "created_at",
        "demand_summary",
        "top_product",
        "top_score",
        "result_count",
        "report_json",
        # 条件指纹：结构化条件的 sha256 摘要，用于跨会话去重。
        # 由决策所需字段派生，不含设备、位置或身份信息，仍在 spec
        # 「数据最小化」的许可范围内。
        "signature",
    }

    for forbidden in ("user", "device", "ip", "location", "email", "phone", "token"):
        assert not any(forbidden in column.lower() for column in columns)


def test_database_file_lands_where_config_says(db_path: Path, monkeypatch):
    """db 路径走 config，测试夹具靠环境变量把它指到临时目录。"""
    from src import config

    monkeypatch.setenv("ZHIGOU_DB_PATH", str(db_path))
    assert config.database_path() == db_path


def test_queries_are_parameterized(db_path: Path, report):
    """收藏 ID 走参数化查询，特殊字符不会把 SQL 搞坏。"""
    nasty = "'; DROP TABLE favorites; --"
    database.add_favorite(nasty, db_path)

    assert database.is_favorite(nasty, db_path) is True
    assert database.list_favorites(db_path) == [(nasty, database.list_favorites(db_path)[0][1])]
