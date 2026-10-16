"""单用户库 → 多用户库的升级测试。

对应变更 `add-login-and-user-roles` 的任务 2.10 与 2.11。

这个文件单独存在（而不是并进 `test_database.py`），是因为它测的是**一次性**的
升级路径：目标是「别人机器上那个装着真实历史的旧库，升级之后一条不丢」。
这类代码平时不跑，只在升级那一刻跑一次——所以更要拿真造的旧库去撞它。

### 造出来的旧库长什么样

按 `add-login-and-user-roles` 之前那一版的结构：

- `analysis_history` 有 `signature`，但**没有** `user_id`
- `idx_history_signature` 是**全局唯一**的 `(signature)` —— 串号缺陷的载体
- `favorites` 是 `product_id` 单列主键 —— 全站只能有一个人收藏某件商品
- `storage/settings.json` 是全局偏好

### 为什么断言里要盯着「老库有没有被就地改坏」

任务 2.7 要求整段迁移在**一个事务**里。2.11 那条用例就是冲着它去的：
故意让迁移中途抛错，然后断言**连 ALTER 加的那一列都退回去了**。
只断言「函数抛了异常」是不够的——那和一个改了一半、留下半迁移状态的实现
完全无法区分。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src import config, database, settings
from src.auth import ROLE_USER, User
from src.errors import HistoryWriteError

ALICE = User(username="alice", role=ROLE_USER)


@pytest.fixture
def db_path() -> Path:
    """历史库路径——**与环境变量指向同一个文件**。

    刻意覆盖 conftest 里那个 `db_path`：它是 `tmp_path/storage/zhigou.db`，
    而 `settings` 与 `database` 的默认路径走 `config.database_path()`
    （隔离夹具指到 `tmp_path/zhigou.db`）。两者不是同一个文件时，
    模板会被写到 A 库、而用例去 B 库查，失败原因极难看懂。
    """
    return config.database_path()

#: 升级前那一版的结构。
_OLD_SCHEMA = """
CREATE TABLE analysis_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT    NOT NULL,
    demand_summary TEXT    NOT NULL,
    top_product    TEXT    NOT NULL DEFAULT '',
    top_score      REAL,
    result_count   INTEGER NOT NULL DEFAULT 0,
    report_json    TEXT    NOT NULL,
    signature      TEXT
);

CREATE UNIQUE INDEX idx_history_signature
    ON analysis_history (signature)
    WHERE signature IS NOT NULL;

CREATE INDEX idx_history_created_at
    ON analysis_history (created_at DESC);

CREATE TABLE favorites (
    product_id TEXT PRIMARY KEY,
    added_at   TEXT NOT NULL
);
"""

#: 单用户时期那条著名的 12 条历史——升级后必须一条不少。
LEGACY_HISTORY_ROWS = 12
LEGACY_FAVORITES = [("LP001", "2026-10-14T10:00:00"), ("HP004", "2026-10-14T11:00:00")]


def _build_legacy_database(path: Path) -> None:
    """造一个单用户时期的库：12 条历史（其中两条签名相同？不——签名单列唯一）

    签名是**全局唯一**的，所以每条历史给一个互不相同的签名；
    这正是那份唯一索引的形态，也正是李四会拿到张三记录的原因。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(_OLD_SCHEMA)
        for index in range(LEGACY_HISTORY_ROWS):
            connection.execute(
                """
                INSERT INTO analysis_history
                    (created_at, demand_summary, top_product, top_score,
                     result_count, report_json, signature)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"2026-10-{10 + index:02d}T09:00:00",
                    f"第 {index + 1} 次分析 · 笔记本电脑",
                    "拓界 17 大屏创作本",
                    86.0,
                    6,
                    "{}",
                    f"legacy-signature-{index:02d}",
                ),
            )
        connection.executemany(
            "INSERT INTO favorites (product_id, added_at) VALUES (?, ?)",
            LEGACY_FAVORITES,
        )


def _columns(path: Path, table: str) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _count(path: Path, sql: str) -> int:
    with sqlite3.connect(path) as connection:
        return int(connection.execute(sql).fetchone()[0])


# --------------------------------------------------------------------------
# 2.10 升级之后：一条不丢，归属如实留空
# --------------------------------------------------------------------------


def test_legacy_history_survives_without_an_owner(db_path: Path):
    _build_legacy_database(db_path)

    database.init_db(db_path)

    assert _count(db_path, "SELECT COUNT(*) FROM analysis_history") == LEGACY_HISTORY_ROWS
    assert (
        _count(db_path, "SELECT COUNT(*) FROM analysis_history WHERE user_id IS NULL")
        == LEGACY_HISTORY_ROWS
    ), "遗留记录必须标为无归属，而不是被塞给某个账号"


def test_legacy_history_is_readable_after_upgrade(db_path: Path):
    _build_legacy_database(db_path)
    database.init_db(db_path)

    entries = database.list_analyses(path=db_path)
    assert len(entries) == LEGACY_HISTORY_ROWS
    assert all(entry.demand_summary.startswith("第 ") for entry in entries)


def test_legacy_favorites_are_carried_over_as_unowned(db_path: Path):
    """收藏被搬到新表里，`user_id` 置空——**不知道是谁的就不编一个归属**。"""
    _build_legacy_database(db_path)

    database.init_db(db_path)

    assert _columns(db_path, "favorites") == {"user_id", "product_id", "added_at"}
    assert _count(db_path, "SELECT COUNT(*) FROM favorites") == len(LEGACY_FAVORITES)
    assert (
        _count(db_path, "SELECT COUNT(*) FROM favorites WHERE user_id IS NULL")
        == len(LEGACY_FAVORITES)
    )

    # 它们不出现在任何人的收藏列表里，但也不是被删掉了
    assert database.list_favorites(ALICE.username, db_path) == []
    assert database.count_unowned_favorites(db_path) == len(LEGACY_FAVORITES)


def test_new_favorites_work_after_the_rebuild(db_path: Path):
    """重建之后新表要能正常用——主键对了，重复收藏才是幂等的。"""
    _build_legacy_database(db_path)
    database.init_db(db_path)

    database.add_favorite(ALICE.username, "LP001", db_path)
    database.add_favorite(ALICE.username, "LP001", db_path)

    assert database.list_favorites(ALICE.username, db_path).__len__() == 1
    # 遗留的那条 LP001 与自己这条并存，互不影响
    assert _count(db_path, "SELECT COUNT(*) FROM favorites WHERE product_id = 'LP001'") == 2


def test_signature_index_is_rebuilt_per_user(db_path: Path):
    """旧的全局唯一索引必须被换掉。

    不换的话串号缺陷原样留着：李四提交与张三相同的条件，
    去重查询会命中张三那条，把别人的报告当成自己的交出去。
    """
    _build_legacy_database(db_path)

    database.init_db(db_path)

    with sqlite3.connect(db_path) as connection:
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_history_signature'"
        ).fetchone()[0]

    assert "user_id" in sql, f"签名索引没有带上用户维度：{sql}"


def test_two_users_can_save_the_same_signature_after_upgrade(db_path: Path, report):
    """升级之后，相同的条件在两个用户名下各存一条，各自读到自己那条。"""
    _build_legacy_database(db_path)
    database.init_db(db_path)

    database.save_analysis(report, db_path, user_id="alice")
    database.save_analysis(report, db_path, user_id="bob")

    assert _count(
        db_path, "SELECT COUNT(*) FROM analysis_history WHERE user_id IS NOT NULL"
    ) == 2
    assert database.find_analysis_by_signature(report.signature, "alice", db_path) != (
        database.find_analysis_by_signature(report.signature, "bob", db_path)
    )


def test_migration_leaves_a_backup_behind(db_path: Path):
    """任务 2.8：迁移前自动备份。备份是「迁完之后后悔」的退路。"""
    _build_legacy_database(db_path)

    database.init_db(db_path)

    backups = list(db_path.parent.glob(f"{db_path.name}.bak-*"))
    assert len(backups) == 1, f"没有留下备份：{list(db_path.parent.iterdir())}"

    # 备份里的还是旧形态——它是升级前的快照
    assert "user_id" not in _columns(backups[0], "analysis_history")


def test_second_startup_does_not_make_another_backup(db_path: Path):
    """已经升级过的库不该每次启动都备份一遍，否则一天下来全是 .bak 文件。"""
    _build_legacy_database(db_path)
    database.init_db(db_path)
    database.init_db(db_path)

    assert len(list(db_path.parent.glob(f"{db_path.name}.bak-*"))) == 1


def test_migration_is_idempotent(db_path: Path):
    """重复执行不改变结果——`_migrate` 每次建表都会跑一遍，必须幂等。"""
    _build_legacy_database(db_path)

    database.init_db(db_path)
    database.init_db(db_path)
    database.init_db(db_path)

    assert _count(db_path, "SELECT COUNT(*) FROM analysis_history") == LEGACY_HISTORY_ROWS
    assert _count(db_path, "SELECT COUNT(*) FROM favorites") == len(LEGACY_FAVORITES)


def test_legacy_settings_file_becomes_the_new_user_template(db_path: Path, tmp_path: Path):
    """任务 2.9：那份全局偏好成为新用户的初始值，原文件改名保留。"""
    legacy_file = tmp_path / "settings.json"
    legacy_file.write_text(
        json.dumps({"price_priority": "value", "show_over_budget": False}),
        encoding="utf-8",
    )
    _build_legacy_database(db_path)

    database.init_db(db_path)
    settings.adopt_legacy_settings_file(legacy_file)

    assert not legacy_file.exists()
    assert (tmp_path / "settings.json.bak").is_file()

    fresh = settings.load_preferences(ALICE, path=db_path)
    assert fresh.price_priority == "value"
    assert fresh.show_over_budget is False


def test_a_fresh_database_gets_no_backup(tmp_path: Path):
    """全新安装没有东西可备——不能因为「users 表不存在」就当成待迁移的老库。"""
    fresh = tmp_path / "brand-new.db"

    database.init_db(fresh)

    assert list(tmp_path.glob("*.bak-*")) == []


def test_product_database_is_not_treated_as_a_legacy_history_database(tmp_path: Path):
    """商品库同样没有 users 表，但它什么都不用迁，更不该被备份。

    判据要是写成「没有 users 表就是要迁移」，每个商品库都会被误伤。
    """
    products_db = tmp_path / "products.db"
    database.init_product_db(products_db)

    database.init_product_db(products_db)

    assert list(tmp_path.glob("*.bak-*")) == []


# --------------------------------------------------------------------------
# 2.11 迁移中途失败：老库必须原样不动
# --------------------------------------------------------------------------


def test_failed_migration_rolls_everything_back(db_path: Path, monkeypatch):
    """迁移在**单个事务**里：中间任何一步失败，整个升级都不留下痕迹。

    只断言「抛了异常」是不够的——那与一个改了一半、留下半迁移状态的实现
    无法区分。所以这里连 **ALTER 加的那一列**都要断言退回去了。
    """
    _build_legacy_database(db_path)

    def explode(connection):
        raise sqlite3.OperationalError("模拟迁移中途失败")

    monkeypatch.setattr(database, "_rebuild_favorites", explode)

    with pytest.raises(HistoryWriteError):
        database.init_db(db_path)

    # 表形状退回原样
    assert "user_id" not in _columns(db_path, "analysis_history"), "补的列没有回滚"
    assert _columns(db_path, "favorites") == {"product_id", "added_at"}, "收藏表被改了一半"

    # 数据一条不少
    assert _count(db_path, "SELECT COUNT(*) FROM analysis_history") == LEGACY_HISTORY_ROWS
    assert _count(db_path, "SELECT COUNT(*) FROM favorites") == len(LEGACY_FAVORITES)


def test_database_stays_usable_after_a_failed_migration(db_path: Path, monkeypatch):
    """失败之后再启动一次要能正常升级——失败不是不可恢复状态。"""
    _build_legacy_database(db_path)

    real = database._rebuild_favorites

    def explode_once(connection):
        raise sqlite3.OperationalError("只在第一次失败")

    monkeypatch.setattr(database, "_rebuild_favorites", explode_once)
    with pytest.raises(HistoryWriteError):
        database.init_db(db_path)

    monkeypatch.setattr(database, "_rebuild_favorites", real)
    database.init_db(db_path)

    assert _count(db_path, "SELECT COUNT(*) FROM analysis_history") == LEGACY_HISTORY_ROWS
    assert "user_id" in _columns(db_path, "analysis_history")
    assert _columns(db_path, "favorites") == {"user_id", "product_id", "added_at"}
