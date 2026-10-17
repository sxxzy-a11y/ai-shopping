"""SQLite 持久化：分析历史、收藏与商品数据。

有两个库文件，**各自只建自己那部分表**：

- 历史库 `storage/zhigou.db`：分析历史、收藏
- 商品库 `storage/products.db`：商品、价格记录、数据集元信息

分成两个文件是为了让损坏变成局部的：共用一个文件时，文件一坏商品与历史
会同时读不出来，整个应用直接不可用。

设计要点（design.md D7）
-----------------------
- 用标准库 `sqlite3`，不引 ORM。表只有两张，ORM 的抽象成本大于收益。
- **报告整段以 JSON 存储**。这是刻意的：需求要求「从历史再次打开时还原
  当时的结论，而不是按当前数据重算」。只要存的是快照，商品数据后来怎么变
  都不影响历史报告。
- 列表页要用的几个字段（摘要、首选、分数）另外开列，避免每次列表都解析 JSON。
- 所有失败都翻译成领域异常，由界面统一转中文提示。
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from src import config
from src.auth import (
    ROLE_ADMIN,
    ROLE_USER,
    User,
    hash_password,
    is_admin,
    require_admin,
    validate_password,
)
from src.errors import (
    CannotDeleteSelf,
    HistoryReadError,
    HistoryWriteError,
    LastAdminProtected,
    UsernameTaken,
    ZhigouError,
)
from src.report_service import DecisionReport, now_local

#: 历史库的表结构：账号、分析历史、收藏、按用户的偏好。
_SCHEMA_HISTORY = """
-- 账号表。字段刻意只有这些：用户名、角色、状态、凭据、创建时间。
-- 没有邮箱/手机号/姓名——本应用不需要它们，收了也只是白拿用户信息。
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    role          TEXT    NOT NULL DEFAULT 'user',
    is_active     INTEGER NOT NULL DEFAULT 1,
    password_hash TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS analysis_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT    NOT NULL,
    demand_summary TEXT    NOT NULL,
    top_product    TEXT    NOT NULL DEFAULT '',
    top_score      REAL,
    result_count   INTEGER NOT NULL DEFAULT 0,
    report_json    TEXT    NOT NULL,
    signature      TEXT,
    -- 可空：单用户时期留下的记录没有归属，如实标成 NULL，
    -- 不硬塞给某个账号（design D4）。
    user_id        TEXT
);

CREATE INDEX IF NOT EXISTS idx_history_created_at
    ON analysis_history (created_at DESC);

-- 收藏：主键带上用户维度。旧形态是 `product_id` 单列主键，
-- 那意味着**全站只能有一个人收藏某件商品**——第二个人点收藏是覆盖第一个人那条。
-- SQLite 改不了主键，所以老库走「建新表→搬→删旧→改名」（design D5）。
CREATE TABLE IF NOT EXISTS favorites (
    -- 可空仅对**遗留收藏**有意义：不知道是谁的，就不编一个归属。
    user_id    TEXT,
    product_id TEXT NOT NULL,
    added_at   TEXT NOT NULL,
    PRIMARY KEY (user_id, product_id)
);

-- 按用户存的偏好。原来是一份全局的 storage/settings.json——
-- 那意味着李四的分析会被张三的偏好影响（design D6）。
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id    TEXT PRIMARY KEY,
    prefs_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT ''
);

-- 单用户时期那份 settings.json 的归宿：作为**新用户的初始偏好模板**。
-- 它是数据集级的东西（不属于任何账号），所以单独一行存着。
-- 不把它归给初始管理员——那是编造归属（design D6）。
CREATE TABLE IF NOT EXISTS preference_template (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    prefs_json TEXT NOT NULL DEFAULT '{}'
);
"""

#: 商品库的表结构。**只建在与商品相关的库文件里**——
#: 建在历史库上会让那个文件看起来也装着商品数据，误导打开它的人。
_SCHEMA_PRODUCTS = """
-- 商品主表：**运行时的唯一商品数据源**。
-- `data/products.json` 只在库为空时作为种子导入一次，之后不再参与运行时读取。
-- specs / use_cases / pros / cons 存 JSON 文本：它们的键按品类异构
-- （笔记本有 cpu_tier，服饰有 comfort_tier），消费方本来就按 dict 读，
-- 拆成 EAV 需要三张表加一次重组，收益为零。
CREATE TABLE IF NOT EXISTS products (
    product_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    brand        TEXT NOT NULL DEFAULT '',
    category     TEXT NOT NULL DEFAULT '',
    model        TEXT,                                -- 可空：服装家具没有型号概念
    specs        TEXT NOT NULL DEFAULT '{}',
    use_cases    TEXT NOT NULL DEFAULT '[]',
    pros         TEXT NOT NULL DEFAULT '[]',
    cons         TEXT NOT NULL DEFAULT '[]',
    data_source  TEXT NOT NULL DEFAULT '',
    source_url   TEXT,                                -- 可空：取不到来源就留空
    image_url    TEXT,                                -- 可空：外链图片，挂了由界面回落图标
    data_status  TEXT NOT NULL DEFAULT 'unverified',  -- verified / unverified
    updated_at   TEXT NOT NULL DEFAULT '',
    -- 是否在售。下架的商品不参与搜索与推荐，但**历史记录里的引用仍可读**——
    -- 下架不等于删除，已经做过的分析报告不该因为商品下架就打不开。
    is_active    INTEGER NOT NULL DEFAULT 1,
    -- 由哪个管理员在界面上录入、什么时候录的。**可空**：
    -- 命令行导入与种子数据都没有「录入者」这个概念，留空才是如实的。
    entered_by   TEXT,
    entered_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products (category);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products (brand);

-- 价格记录：价格**单独成表**并带来源与采集时间。
-- 它是最需要核实的字段，却曾经只是商品表上一个无来源、无时效的孤立数值。
-- 商品当前价格取自 is_current = 1 的那条；没有记录时价格视为缺失，
-- 不默认符合预算（与「缺数据不猜」的既有立场一致）。
CREATE TABLE IF NOT EXISTS product_prices (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   TEXT NOT NULL,
    price        REAL NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'CNY',
    source_note  TEXT NOT NULL DEFAULT '',
    collected_at TEXT NOT NULL DEFAULT '',
    verified_at  TEXT,
    is_current   INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_prices_current
    ON product_prices (product_id, is_current);

-- 数据集级元信息：免责声明、档位说明这类整批数据共有的说明。
-- 单独存表而不是挂在某条商品上，是因为它属于**数据集**而不是商品；
-- 也不能留在种子文件里——种子删掉之后免责声明不能跟着消失。
CREATE TABLE IF NOT EXISTS dataset_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

-- 分类元数据。**只放既有分类的覆盖项**，全集永远是 config.CATEGORY_LABELS——
-- 分类键不可增删（见 design D9：新增分类要配权重、档位与知识指南，
-- 那是代码与语料的工作量，不是一次点击）。
CREATE TABLE IF NOT EXISTS category_meta (
    category_key  TEXT PRIMARY KEY,
    display_label TEXT,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    is_active     INTEGER NOT NULL DEFAULT 1,
    updated_by    TEXT,
    updated_at    TEXT
);

-- 品牌字典。键是**商品里的写法**，与商品表对得上。
-- 由 `catalog_meta.sync_brands()` 从商品自动补齐，管理员只改元数据。
CREATE TABLE IF NOT EXISTS brand_meta (
    brand_name   TEXT PRIMARY KEY,
    display_name TEXT,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    is_active     INTEGER NOT NULL DEFAULT 1,
    entered_by   TEXT,
    entered_at   TEXT
);
"""

#: 同一组条件只存一条的唯一索引——**按用户**。
#:
#: 旧的索引是全局 `(signature)` 唯一，那会闹出一个很隐蔽的错：
#: 李四提交与张三完全相同的条件时，去重查询会命中张三那条，
#: `save_analysis` 于是把**张三记录的 ID 返回给李四**——不报错、不崩溃，
#: 只是把别人的报告当成自己的交出去（design D4）。
#:
#: 部分索引条件同时要求 `user_id` 非空：SQLite 把 UNIQUE 索引里的 NULL
#: 视为互不相等，所以遗留记录（两列都是 NULL）既不会互相冲突，
#: 也不会挡住新用户的同名签名——它们就此退出去重体系，正是想要的。
_SIGNATURE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_history_signature
    ON analysis_history (user_id, signature)
    WHERE signature IS NOT NULL AND user_id IS NOT NULL;
"""

#: 按用户查历史的索引。
#:
#: **刻意不放在 `_SCHEMA_HISTORY` 里。** 建表脚本先于补列执行，而老库的
#: `analysis_history` 还没有 `user_id` 列——`CREATE TABLE IF NOT EXISTS` 对已存在的表
#: 是空操作，紧接着的这条 `CREATE INDEX ... (user_id, ...)` 就会以
#: `no such column: user_id` 失败，把整个升级卡死。索引必须在补列**之后**建。
_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_history_user
    ON analysis_history (user_id, created_at DESC);
"""


@dataclass(frozen=True)
class HistoryEntry:
    """历史列表里的一行。只含列表展示需要的字段，不带完整报告。"""

    id: int
    created_at: str
    demand_summary: str
    top_product: str
    top_score: float | None
    result_count: int
    #: 归属账号。单用户时期的遗留记录为空——**如实留空，不编一个归属**。
    user_id: str | None = None

    @property
    def created_at_label(self) -> str:
        """把 ISO 时间串显示成 `2026-10-12 21:30`。"""
        text = self.created_at.replace("T", " ")
        return text[:16]

    @property
    def score_label(self) -> str:
        return f"{self.top_score:.0f} 分" if self.top_score is not None else "无推荐"

    @property
    def owner_label(self) -> str:
        """归属展示名。全站概览直接用它，避免在界面里再判一次空。"""
        return self.user_id if self.user_id else "无归属（单用户时期遗留）"


# --------------------------------------------------------------------------
# 连接管理
# --------------------------------------------------------------------------


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect(path: Path | None = None):
    """打开连接并保证关闭。

    把 sqlite3 的各类错误翻译成领域异常——界面只认领域异常，
    这样「不向用户暴露堆栈」只需在一处保证。
    """
    target = Path(path) if path is not None else config.database_path()
    _ensure_parent(target)

    try:
        connection = sqlite3.connect(target)
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "无法打开本地数据库文件，历史记录功能暂不可用。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    try:
        connection.row_factory = sqlite3.Row
        # SQLite 默认**不启用**外键约束，必须逐连接打开，
        # 否则 `product_prices` 上的 ON DELETE CASCADE 只是一句摆设。
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()


def _database_shape(path: Path) -> tuple[set[str], dict[str, set[str]], dict[str, str]]:
    """一次读齐库的形状：`(表集合, 表->列集合, 索引名->建索引 SQL)`。

    读不出来就返回空集合——**这里只回答「要不要先备份」，不负责报错**。
    真正的报错留给后面的建表：库真的坏了，用户应该看到的是
    「历史记录读取失败」，而不是这句体检失败。
    """
    tables: set[str] = set()
    columns: dict[str, set[str]] = {}
    indexes: dict[str, str] = {}

    if not path.exists():
        return tables, columns, indexes

    try:
        with connect(path) as connection:
            for row in connection.execute(
                "SELECT type, name, sql FROM sqlite_master"
            ):
                if row["type"] == "table":
                    tables.add(row["name"])
                    columns[row["name"]] = {
                        info["name"]
                        for info in connection.execute(
                            f"PRAGMA table_info({row['name']})"
                        )
                    }
                elif row["type"] == "index":
                    indexes[row["name"]] = row["sql"] or ""
    except (sqlite3.Error, ZhigouError):
        return set(), {}, {}

    return tables, columns, indexes


def _needs_multiuser_migration(path: Path) -> bool:
    """这个库文件需要升级到多用户形态吗。

    **判据必须先确认「它像历史库」。** 商品库里同样没有 users 表，
    若拿「users 表不存在」当判据，每个商品库都会被当成待升级的老库拿去备份，
    而它其实什么都不用迁。
    """
    tables, columns, indexes = _database_shape(path)
    if not ({"analysis_history", "favorites"} & tables):
        return False  # 不是历史库：商品库或空库，没有要迁的东西

    if "users" not in tables:
        return True
    if "user_id" not in columns.get("analysis_history", set()):
        return True
    if "favorites" in tables and "user_id" not in columns.get("favorites", set()):
        return True
    # 索引列变了也算待迁移：老索引是全局 (signature)，新索引是 (user_id, signature)
    legacy_index = indexes.get("idx_history_signature", "")
    return bool(legacy_index) and "user_id" not in legacy_index


def _backup_database(path: Path) -> Path | None:
    """迁移前把库文件复制一份，返回备份路径（复制失败则 None）。

    命名只到日期：一天里反复启动只留一份，不会堆一地文件。

    **复制失败不阻断迁移。** 备份是「迁完之后后悔」的保险，而「迁移中途出错」
    由 `_run_schema` 的事务兜住——两件事各管一头。为了备份把应用卡成不可用，
    是本末倒置。
    """
    stamp = now_local().strftime("%Y%m%d")
    target = path.with_name(f"{path.name}.bak-{stamp}")
    try:
        shutil.copy2(path, target)
    except OSError:
        return None
    return target


def _run_schema(path: Path | None, script: str) -> None:
    """建表并迁移。

    顺序是**先备份、再迁移**：备份必须在写入发生之前，否则备份里已经是
    半迁移的状态。`with connection:` 让整段迁移成为一个事务——
    任何一步抛错都整体回滚，老库保持原样（任务 2.7、2.11）。

    注意 `executescript` 会先隐式提交，所以建表本身不在那个事务里；
    这是可接受的：`CREATE TABLE IF NOT EXISTS` 全是幂等的，
    重复执行不会留下中间状态。真正危险的表重建都在 `_migrate` 里。
    """
    target = Path(path) if path is not None else config.database_path()
    _ensure_parent(target)

    if _needs_multiuser_migration(target):
        _backup_database(target)

    with connect(target) as connection:
        try:
            connection.executescript(script)
            with connection:
                # **必须显式 BEGIN。** Python 的 sqlite3 只在 DML（INSERT/UPDATE/
                # DELETE）前隐式开事务，DDL 不是——`ALTER TABLE` / `CREATE INDEX`
                # 会各自自动提交。不写这一句，「整段迁移在一个事务里」就是空话：
                # 中途失败时表已经被改掉了，而 `with connection:` 的 rollback
                # 无事可回滚，一路静悄悄（这个坑由 test_migration 里的
                # 「迁移中途失败」用例逮住）。
                connection.execute("BEGIN")
                _migrate(connection)
        except sqlite3.Error as exc:
            raise HistoryWriteError(
                "本地数据库初始化失败，历史记录功能暂不可用。",
                detail=f"{type(exc).__name__}: {exc}",
            ) from exc


def init_db(path: Path | None = None) -> None:
    """建**全部**表。

    测试与迁移脚本用——它们通常只对付一个库文件。
    应用自己的读写在下面两个**按范围**的入口里，别用这个：
    把商品表建到历史库上，会让那个文件看起来也装着商品数据，
    误导打开它的人（这个坑实际踩过一次）。
    """
    _run_schema(path, _SCHEMA_HISTORY + _SCHEMA_PRODUCTS)


def init_history_db(path: Path | None = None) -> None:
    """只建历史库的表。读历史时用它。

    **不带路径时落到哪个库，是按库的范围定的**：历史库 → `zhigou.db`。
    这一点原先靠 `_run_schema` 里的通用默认值（永远是历史库）间接成立，
    于是 `init_product_db()` 不带路径时会把**商品表建进历史库**——
    实测被在一条「历史库损坏不影响分析」的用例上逮到。
    """
    _run_schema(path if path is not None else config.database_path(), _SCHEMA_HISTORY)


def init_product_db(path: Path | None = None) -> None:
    """只建商品库的表。商品仓储层用它。不带路径时落到 `products.db`。"""
    _run_schema(path if path is not None else config.products_db_path(), _SCHEMA_PRODUCTS)


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
    }


def _rebuild_favorites(connection: sqlite3.Connection) -> None:
    """把单用户形态的 `favorites` 重建成带用户维度的形态。

    SQLite 不支持 `ALTER TABLE` 改主键，只能「建新表 → 搬 → 删旧 → 改名」。

    遗留收藏的 `user_id` 置为 NULL：**不知道是谁的，就不编一个归属**。
    它们因此只对管理员可见，与遗留历史记录的处理一致。
    """
    connection.execute("DROP TABLE IF EXISTS favorites_new")
    connection.execute(
        """
        CREATE TABLE favorites_new (
            user_id    TEXT,
            product_id TEXT NOT NULL,
            added_at   TEXT NOT NULL,
            PRIMARY KEY (user_id, product_id)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO favorites_new (user_id, product_id, added_at)
        SELECT NULL, product_id, added_at FROM favorites
        """
    )
    connection.execute("DROP TABLE favorites")
    connection.execute("ALTER TABLE favorites_new RENAME TO favorites")


def _drop_legacy_signature_index(connection: sqlite3.Connection) -> None:
    """删掉全局唯一的旧签名索引，好让新索引能建起来。

    不删的话 `CREATE UNIQUE INDEX IF NOT EXISTS idx_history_signature`
    会因为**同名索引已存在**而直接跳过，新库看似升级了、实际仍在用旧索引——
    那正是串号缺陷留存的方式。
    """
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_history_signature'"
    ).fetchone()
    if row is not None and "user_id" not in (row["sql"] or ""):
        connection.execute("DROP INDEX idx_history_signature")


def _migrate(connection: sqlite3.Connection) -> None:
    """老库升级。**必须幂等**——每次建表都会跑一遍。

    升级内容（design 的 Migration Plan 第 2–4 步）：
    给 `analysis_history` 补 `signature` 与 `user_id` 两列；
    把单用户形态的 `favorites` 重建成 `(user_id, product_id)` 主键；
    把全局唯一的签名索引换成按用户的。

    表层的建表不在这里——`CREATE TABLE IF NOT EXISTS` 对已存在的表不生效，
    所以**只有补列与改形状**才需要写在这里。

    **只在表存在时才动。** 这个函数会被三条建表路径共用，而商品库那条路上
    根本没有 analysis_history——不加这道判断就会在商品库上抛「表不存在」。
    """
    tables = {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    # 商品库的补列走这一支
    if "products" in tables:
        product_columns = _table_columns(connection, "products")
        if "image_url" not in product_columns:
            connection.execute("ALTER TABLE products ADD COLUMN image_url TEXT")
        if "is_active" not in product_columns:
            # 老库里的商品默认为**在售**：它们本来就在参与推荐，
            # 加这一列不该让整个商品库凭空下架。
            connection.execute(
                "ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
            )
        if "entered_by" not in product_columns:
            connection.execute("ALTER TABLE products ADD COLUMN entered_by TEXT")
        if "entered_at" not in product_columns:
            connection.execute("ALTER TABLE products ADD COLUMN entered_at TEXT")

    if "analysis_history" not in tables:
        return

    columns = _table_columns(connection, "analysis_history")
    if "signature" not in columns:
        connection.execute("ALTER TABLE analysis_history ADD COLUMN signature TEXT")
    if "user_id" not in columns:
        # 可空：遗留记录没有归属，如实留空而不是硬塞给某个账号（design D4）
        connection.execute("ALTER TABLE analysis_history ADD COLUMN user_id TEXT")

    if "favorites" in tables and "user_id" not in _table_columns(connection, "favorites"):
        _rebuild_favorites(connection)

    _drop_legacy_signature_index(connection)
    connection.execute(_SIGNATURE_INDEX)
    connection.execute(_USER_INDEX)


def _ensure_ready(path: Path | None) -> None:
    """读操作前的准备。

    建表本身是写操作，但**触发它的是一次读取**——数据库文件损坏时，
    用户看到的原因应该是「读取失败」而不是「写入失败」。
    所以这里把写异常翻译成读异常。
    """
    try:
        init_history_db(path)
    except HistoryWriteError as exc:
        raise HistoryReadError(
            "历史记录读取失败，可能是本地数据库文件损坏。当前仍可进行新的分析。",
            detail=exc.detail,
        ) from exc


def check_health(path: Path | None = None) -> tuple[bool, str]:
    """体检数据库。返回 (是否可用, 说明)。

    界面用它区分「数据库坏了」和「还没有历史记录」——这两种情况
    给用户的提示完全不同，不能都说成「暂无记录」。
    """
    try:
        init_db(path)
        with connect(path) as connection:
            connection.execute("SELECT COUNT(*) FROM analysis_history").fetchone()
    except (HistoryReadError, HistoryWriteError) as exc:
        return False, exc.user_message
    except sqlite3.Error as exc:
        return False, f"本地数据库读取失败：{type(exc).__name__}"
    return True, "正常"


# --------------------------------------------------------------------------
# 账号
# --------------------------------------------------------------------------
#
# 这一节是**账号的唯一写入口**。两条不变式钉在这里，而不是钉在界面上：
#
# 1. **明文密码不可能落库**：写函数只收明文，在内部派生。
#    把「传进来的必须已经是派生结果」交给调用方，早晚会有人传错，
#    而那种错一旦发生就是把明文写进了库。
# 2. **系统不会失去全部管理员**：降级或停用最后一个可用管理员会被拒绝。
#    守卫放在真正写库的那个事务里，界面绕不过去（design D3 的同一原则）。


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        username=row["username"],
        role=row["role"],
        is_active=bool(row["is_active"]),
        password_hash=row["password_hash"],
        created_at=row["created_at"],
    )


def create_user(
    username: str,
    password: str,
    role: str = ROLE_USER,
    path: Path | None = None,
) -> User:
    """新建账号。**只收明文密码，在这里派生**。

    Raises:
        UsernameTaken: 用户名已存在。
        HistoryWriteError: 写入失败。
    """
    created_at = now_local().isoformat(timespec="seconds")
    credential = hash_password(password)

    try:
        init_history_db(path)
        with connect(path) as connection:
            connection.execute(
                """
                INSERT INTO users (username, role, is_active, password_hash, created_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (username, role, credential, created_at),
            )
            connection.commit()
    except sqlite3.IntegrityError as exc:
        raise UsernameTaken(
            f"用户名「{username}」已被占用，请换一个。", detail=str(exc)
        ) from exc
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "账号创建失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc

    return User(
        username=username,
        role=role,
        is_active=True,
        password_hash=credential,
        created_at=created_at,
    )


def get_user(username: str, path: Path | None = None) -> User | None:
    """按用户名取账号。不存在返回 None。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute(
                """
                SELECT username, role, is_active, password_hash, created_at
                FROM users WHERE username = ?
                """,
                (username,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "账号信息读取失败，可能是本地数据库文件损坏。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    return _row_to_user(row) if row is not None else None


def list_users(path: Path | None = None) -> list[User]:
    """列出全部账号，按创建时间与用户名排序。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            rows = connection.execute(
                """
                SELECT username, role, is_active, password_hash, created_at
                FROM users ORDER BY created_at, username
                """
            ).fetchall()
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "账号列表读取失败，可能是本地数据库文件损坏。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    return [_row_to_user(row) for row in rows]


def count_users(path: Path | None = None) -> int:
    """账号总数。初始管理员的引导靠它判断「表是不是空的」（任务 11.1）。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()
            return int(row["n"])
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "账号数量统计失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc


def count_active_admins(path: Path | None = None) -> int:
    """还有几个**可用的**管理员。停用的不算——停用等于不能用。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM users WHERE role = ? AND is_active = 1",
                (ROLE_ADMIN,),
            ).fetchone()
            return int(row["n"])
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "管理员数量统计失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc


def _guard_last_admin(connection: sqlite3.Connection, username: str) -> None:
    """拒绝「让系统失去最后一个可用管理员」的操作。

    **判断放在同一个事务里**：先查后改之间若被插入另一个停用操作，
    两个操作各自都以为「还有别人」，结果一个都不剩。

    Raises:
        LastAdminProtected: 该账号是最后一个可用管理员。
    """
    row = connection.execute(
        "SELECT role, is_active FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None or row["role"] != ROLE_ADMIN or not row["is_active"]:
        return

    others = connection.execute(
        """
        SELECT COUNT(*) AS n FROM users
        WHERE role = ? AND is_active = 1 AND username <> ?
        """,
        (ROLE_ADMIN, username),
    ).fetchone()
    if int(others["n"]) == 0:
        raise LastAdminProtected(
            detail=f"{username} 是最后一个可用管理员，拒绝该操作"
        )


def _count_rows(connection: sqlite3.Connection, table: str, username: str) -> int:
    row = connection.execute(
        f"SELECT COUNT(*) AS n FROM {table} WHERE user_id = ?", (username,)
    ).fetchone()
    return int(row["n"])


def count_user_data(username: str, path: Path | None = None) -> tuple[int, int]:
    """该账号名下的 `(历史条数, 收藏条数)`。

    删除账号前用它把破坏性写在确认处——只说「确定删除吗」等于没提醒，
    把**具体多少条**摆出来，删的人才知道自己在删什么。

    偏好不计入：它只有一行、且是一份设置，报出来只是噪声。
    """
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            return (
                _count_rows(connection, "analysis_history", username),
                _count_rows(connection, "favorites", username),
            )
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "账号数据统计失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc


def _delete_user_rows(connection: sqlite3.Connection, username: str) -> None:
    """级联删掉该账号的全部数据。

    **抽成一个函数是为了能被测试打桩**：「中途失败要整体回滚」那条用例
    需要一个「删了一半」的位置来抛错，否则只能断言「函数抛了异常」——
    那与一个真删掉一半的实现无法区分。
    """
    connection.execute("DELETE FROM analysis_history WHERE user_id = ?", (username,))
    connection.execute("DELETE FROM favorites WHERE user_id = ?", (username,))
    connection.execute("DELETE FROM user_preferences WHERE user_id = ?", (username,))
    connection.execute("DELETE FROM users WHERE username = ?", (username,))


def delete_user(
    username: str, path: Path | None = None, *, viewer: User | None
) -> tuple[int, int]:
    """删除账号，并级联删除其历史、收藏与偏好。返回被删掉的 `(历史, 收藏)` 条数。

    三条边界：

    - **只有管理员能调**（`require_admin`）
    - **不能删自己**：删掉自己之后那个会话对象还在内存里，而守卫只看这个对象，
      会出现「已被删除的管理员仍能操作」的窗口
    - **不能删掉最后一个可用管理员**：复用既有守卫，**停用的不算可用**

    四张表的删除在一个事务里。`DELETE` 是 DML，Python 的 `sqlite3` 会在第一条 DML
    之前隐式开事务，`with connection:` 负责提交或回滚——中途失败不会留下
    「账号没了但数据还在」这种半删状态。

    **注意这与库迁移那段不同**：那里是 DDL，DDL 不会自动开事务，必须显式 `BEGIN`。
    两处的写法不一样不是疏忽，是 sqlite3 的行为不同。

    Raises:
        PermissionDenied: 调用者不是管理员。
        CannotDeleteSelf: 试图删除自己。
        LastAdminProtected: 该账号是最后一个可用管理员。
        HistoryWriteError: 账号不存在或写入失败。
    """
    require_admin(viewer)
    if viewer is not None and viewer.username == username:
        raise CannotDeleteSelf(detail=f"{username} 试图删除自己")

    try:
        _ensure_ready(path)
        with connect(path) as connection:
            with connection:
                exists = connection.execute(
                    "SELECT 1 FROM users WHERE username = ?", (username,)
                ).fetchone()
                if exists is None:
                    # 不把「删了个不存在的账号」当成成功：那会让界面显示
                    # 「已删除」，而实际什么也没发生。
                    raise HistoryWriteError(
                        f"找不到账号「{username}」，未做任何改动。", detail=username
                    )

                _guard_last_admin(connection, username)
                counts = (
                    _count_rows(connection, "analysis_history", username),
                    _count_rows(connection, "favorites", username),
                )
                _delete_user_rows(connection, username)
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "删除账号失败，账号与数据保持不变。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    return counts


def set_user_role(
    username: str, role: str, path: Path | None = None, *, viewer: User | None
) -> None:
    """改角色。**只有管理员能调**，且降级最后一个可用管理员会被拒绝。

    `viewer` 是必填的关键字参数：给默认值的话，某条路径漏传就会静默放行，
    而「普通用户直接调管理员操作」正是要挡住的那条路（design D3）。
    """
    require_admin(viewer)
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            with connection:
                if role != ROLE_ADMIN:
                    _guard_last_admin(connection, username)
                connection.execute(
                    "UPDATE users SET role = ? WHERE username = ?", (role, username)
                )
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "修改角色失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc


def set_user_password(
    username: str, password: str, path: Path | None = None, *, viewer: User | None
) -> None:
    """重置密码。**只有管理员能调**，且只收明文、在这里派生。

    最短长度也在这条路上守一遍。原先只有注册路径检查它，而管理员重置那条路
    照单全收——界面上写着「至少 8 位」，数据层却会接受一个 1 位密码。
    界面承诺的事必须在数据层兑现，这是「界面隐藏不算权限」的同一条原则：
    **别让规则只活在提示文案里。**
    """
    require_admin(viewer)
    validate_password(password)
    credential = hash_password(password)
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (credential, username),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "重置密码失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc


def set_user_active(
    username: str,
    is_active: bool,
    path: Path | None = None,
    *,
    viewer: User | None,
) -> None:
    """停用 / 启用账号。只有管理员能调，停用最后一个可用管理员会被拒绝。"""
    require_admin(viewer)
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            with connection:
                if not is_active:
                    _guard_last_admin(connection, username)
                connection.execute(
                    "UPDATE users SET is_active = ? WHERE username = ?",
                    (1 if is_active else 0, username),
                )
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "修改账号状态失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc


# --------------------------------------------------------------------------
# 按用户的偏好（JSON 存取）
# --------------------------------------------------------------------------
#
# `src/settings.py` 负责把 JSON 解析成 `UserPreferences`，SQL 全在这里。
# 分开是为了守住「SQL 只出现在本模块」这条既有约定。


def read_preferences_json(user_id: str, path: Path | None = None) -> str | None:
    """读某个用户存的偏好 JSON。没有记录返回 None。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute(
                "SELECT prefs_json FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return row["prefs_json"] if row is not None else None
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "偏好设置读取失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc


def write_preferences_json(
    user_id: str, prefs_json: str, path: Path | None = None
) -> None:
    try:
        init_history_db(path)
        with connect(path) as connection:
            connection.execute(
                """
                INSERT INTO user_preferences (user_id, prefs_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    prefs_json = excluded.prefs_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, prefs_json, now_local().isoformat(timespec="seconds")),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "偏好设置保存失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc


def read_template_json(path: Path | None = None) -> str | None:
    """读「新用户初始偏好模板」。没有则 None（表示用代码里的默认值）。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute(
                "SELECT prefs_json FROM preference_template WHERE id = 1"
            ).fetchone()
            return row["prefs_json"] if row is not None else None
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "偏好模板读取失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc


def write_template_json(prefs_json: str, path: Path | None = None) -> None:
    try:
        init_history_db(path)
        with connect(path) as connection:
            connection.execute(
                """
                INSERT INTO preference_template (id, prefs_json) VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET prefs_json = excluded.prefs_json
                """,
                (prefs_json,),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "偏好模板保存失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc


# --------------------------------------------------------------------------
# 分析历史
# --------------------------------------------------------------------------


def save_analysis(
    report: DecisionReport,
    path: Path | None = None,
    *,
    user_id: str | None = None,
) -> int:
    """写入一条分析记录，返回记录 ID。`user_id` 是归属账号。

    **按条件指纹去重，而且按用户去重**：同一个用户提交同一组条件只存一条；
    不同用户提交相同条件**各存一条**。

    这条用户维度是整个变更里最要紧的一处修复。之前查询是
    `WHERE signature = ?`，全局唯一——李四提交与张三完全相同的条件时，
    它会命中张三那条并把**张三的 ID 返回给李四**，于是李四打开历史看到的
    是别人的报告。不报错、不崩溃，只是把别人的数据当成自己的给出去。

    `user_id` 为空（遗留调用）时按「无归属」去重：SQLite 的 `IS` 把两个 NULL
    视为相等，所以这类记录仍然只存一条，行为与单用户时期一致。

    Raises:
        HistoryWriteError: 写入失败。调用方应提示用户，但**不中断**当前页面——
        结果还在内存里，用户的这次分析没有白做。
    """
    top = report.recommendations[0] if report.recommendations else None

    try:
        init_db(path)
    except HistoryWriteError as exc:
        # init_db 失败时它说的是「数据库初始化失败」，但用户此刻做的是「保存」。
        # 报错要按用户正在做的事来说，不然他会以为自己点错了地方。
        raise HistoryWriteError(
            "本次分析记录保存失败，结果仍可在当前页面查看。",
            detail=exc.detail,
        ) from exc

    signature = (report.signature or "").strip() or None

    try:
        with connect(path) as connection:
            if signature is not None:
                existing = connection.execute(
                    """
                    SELECT id FROM analysis_history
                    WHERE signature = ? AND user_id IS ?
                    LIMIT 1
                    """,
                    (signature, user_id),
                ).fetchone()
                if existing is not None:
                    return int(existing["id"])

            try:
                cursor = connection.execute(
                    """
                    INSERT INTO analysis_history
                        (created_at, demand_summary, top_product, top_score,
                         result_count, report_json, signature, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.created_at,
                        report.demand_summary,
                        top.name if top else "",
                        top.score_total if top else None,
                        len(report.recommendations),
                        json.dumps(report.to_dict(), ensure_ascii=False),
                        signature,
                        user_id,
                    ),
                )
                connection.commit()
                return int(cursor.lastrowid or 0)
            except sqlite3.IntegrityError:
                # 并发窗口内另一个会话刚好插入了同指纹记录。
                # 查回来按「已存在」处理；真的查不到再往外抛。
                connection.rollback()
                existing = connection.execute(
                    """
                    SELECT id FROM analysis_history
                    WHERE signature = ? AND user_id IS ?
                    LIMIT 1
                    """,
                    (signature, user_id),
                ).fetchone()
                if existing is not None:
                    return int(existing["id"])
                raise
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "本次分析记录保存失败，结果仍可在当前页面查看。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def find_analysis_by_signature(
    signature: str, user_id: str | None = None, path: Path | None = None
) -> int | None:
    """按条件指纹找一条**属于该用户**的记录 ID。没有则 None。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute(
                """
                SELECT id FROM analysis_history
                WHERE signature = ? AND user_id IS ?
                LIMIT 1
                """,
                (signature, user_id),
            ).fetchone()
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "历史记录查找失败。", detail=f"{type(exc).__name__}: {exc}"
        ) from exc

    return int(row["id"]) if row is not None else None


def _rows_to_entries(rows) -> list[HistoryEntry]:
    return [
        HistoryEntry(
            id=row["id"],
            created_at=row["created_at"],
            demand_summary=row["demand_summary"],
            top_product=row["top_product"],
            top_score=row["top_score"],
            result_count=row["result_count"],
            user_id=row["user_id"],
        )
        for row in rows
    ]


_HISTORY_COLUMNS = (
    "id, created_at, demand_summary, top_product, top_score, result_count, user_id"
)


def list_analyses(limit: int = 50, path: Path | None = None) -> list[HistoryEntry]:
    """列出**全部**历史记录，按时间由新到旧。

    **这个函数是给管理员的全站概览用的**（design D3：界面隐藏不算权限，
    所以「能不能看全部」由调用方是不是管理员决定，而这个入口本身就意味着
    「我要看全部」）。普通用户的历史页请用 `list_analyses_of()`。
    """
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            rows = connection.execute(
                f"""
                SELECT {_HISTORY_COLUMNS}
                FROM analysis_history
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "历史记录读取失败，可能是本地数据库文件损坏。当前仍可进行新的分析。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    return _rows_to_entries(rows)


def list_analyses_of(
    user_id: str, limit: int = 50, path: Path | None = None
) -> list[HistoryEntry]:
    """列出**某个用户本人**的历史记录，按时间由新到旧。

    遗留记录（`user_id` 为空）不会出现在任何人的列表里——它们没有归属，
    谁都认领不了，只在全站概览里单独标注。
    """
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            rows = connection.execute(
                f"""
                SELECT {_HISTORY_COLUMNS}
                FROM analysis_history
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "历史记录读取失败，可能是本地数据库文件损坏。当前仍可进行新的分析。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    return _rows_to_entries(rows)


def _may_read(connection: sqlite3.Connection, entry_id: int, viewer: User | None) -> bool:
    """这条记录能不能给这个访问者看。

    三种情况放行：管理员；记录归他本人；**遗留记录**（`user_id` 为空）只对管理员放行。
    其余一律拒绝——普通用户按 ID 猜别人的记录是必须挡住的一条路。
    """
    if is_admin(viewer):
        return True
    if viewer is None:
        return False

    row = connection.execute(
        "SELECT user_id FROM analysis_history WHERE id = ?", (entry_id,)
    ).fetchone()
    if row is None:
        return False
    return row["user_id"] == viewer.username


def get_analysis(
    entry_id: int, path: Path | None = None, *, viewer: User | None
) -> DecisionReport | None:
    """按 ID 取回完整报告。不存在**或无权查看**都返回 `None`。

    `viewer` 是**必填的关键字参数**，没有默认值：每一次读都必须说清楚
    「是谁在读」。给个默认值的话，某条路径漏传就会静默地按「全都能读」放行，
    而那正是要防的事。
    """
    try:
        with connect(path) as connection:
            if not _may_read(connection, entry_id, viewer):
                return None
            row = connection.execute(
                "SELECT report_json FROM analysis_history WHERE id = ?", (entry_id,)
            ).fetchone()
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "历史报告读取失败，可能是本地数据库文件损坏。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    if row is None:
        return None

    try:
        return DecisionReport.from_dict(json.loads(row["report_json"]))
    except (json.JSONDecodeError, TypeError) as exc:
        raise HistoryReadError(
            "这条历史记录的内容已损坏，无法打开。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def delete_analysis(
    entry_id: int, path: Path | None = None, *, viewer: User | None
) -> bool:
    """删除一条历史记录。返回是否真的删掉了。

    与 `get_analysis` 同一条归属校验：**能读才谈得上删**。
    """
    try:
        with connect(path) as connection:
            if not _may_read(connection, entry_id, viewer):
                return False
            cursor = connection.execute(
                "DELETE FROM analysis_history WHERE id = ?", (entry_id,)
            )
            connection.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "删除历史记录失败。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def count_analyses(path: Path | None = None) -> int:
    """历史总数（含遗留记录）。全站概览用。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM analysis_history"
            ).fetchone()
            return int(row["n"])
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "历史记录数量统计失败。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def count_analyses_of(user_id: str, path: Path | None = None) -> int:
    """某个用户本人的历史条数。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM analysis_history WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return int(row["n"])
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "历史记录数量统计失败。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def count_unowned_analyses(path: Path | None = None) -> int:
    """无归属的遗留历史条数。全站概览要**单独标注**它们（任务 7.3）。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM analysis_history WHERE user_id IS NULL"
            ).fetchone()
            return int(row["n"])
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "历史记录数量统计失败。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


# --------------------------------------------------------------------------
# 收藏
# --------------------------------------------------------------------------


def add_favorite(user_id: str, product_id: str, path: Path | None = None) -> None:
    """收藏一件商品，归属该用户。

    同一用户重复收藏**不报错、也不更新收藏时间**——保留第一次的那个时刻，
    列表顺序才稳定（早先的实现是整行替换，重复点一下就把条目挪到最前面）。

    两个用户可以各自收藏同一件商品：主键是 `(user_id, product_id)`。
    旧的单列主键下，第二个人点收藏是**覆盖**第一个人那条。
    """
    try:
        init_history_db(path)
        with connect(path) as connection:
            connection.execute(
                """
                INSERT INTO favorites (user_id, product_id, added_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, product_id) DO NOTHING
                """,
                (user_id, product_id, now_local().isoformat(timespec="seconds")),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "收藏保存失败。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def remove_favorite(user_id: str, product_id: str, path: Path | None = None) -> None:
    try:
        init_history_db(path)
    except HistoryWriteError as exc:
        raise HistoryWriteError("取消收藏失败。", detail=exc.detail) from exc

    try:
        with connect(path) as connection:
            connection.execute(
                "DELETE FROM favorites WHERE user_id = ? AND product_id = ?",
                (user_id, product_id),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "取消收藏失败。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def list_favorites(user_id: str, path: Path | None = None) -> list[tuple[str, str]]:
    """返回该用户的 [(product_id, added_at)]，按收藏时间由新到旧。

    无归属的遗留收藏**不会出现在任何人的列表里**（`user_id` 为 NULL，
    谁也认领不了它们）；它们仍在库中，可被全站概览统计到。
    """
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            rows = connection.execute(
                """
                SELECT product_id, added_at FROM favorites
                WHERE user_id = ? ORDER BY added_at DESC
                """,
                (user_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "收藏列表读取失败。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    return [(row["product_id"], row["added_at"]) for row in rows]


def count_unowned_favorites(path: Path | None = None) -> int:
    """无归属的遗留收藏条数。给全站概览用（design D5）。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM favorites WHERE user_id IS NULL"
            ).fetchone()
            return int(row["n"])
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "收藏数量统计失败。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def is_favorite(user_id: str, product_id: str, path: Path | None = None) -> bool:
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute(
                "SELECT 1 FROM favorites WHERE user_id = ? AND product_id = ?",
                (user_id, product_id),
            ).fetchone()
            return row is not None
    except (sqlite3.Error, ZhigouError):
        # 收藏状态的读取失败不应该挡住界面渲染，按「未收藏」处理。
        # 这里刻意吞掉领域异常：它是一个渲染期的辅助查询，
        # 数据库坏了也该让用户看到商品列表，而不是整页报错。
        return False
