"""SQLite 持久化：分析历史与收藏。

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
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from src import config
from src.errors import HistoryReadError, HistoryWriteError, ZhigouError
from src.report_service import DecisionReport, now_local

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT    NOT NULL,
    demand_summary TEXT    NOT NULL,
    top_product    TEXT    NOT NULL DEFAULT '',
    top_score      REAL,
    result_count   INTEGER NOT NULL DEFAULT 0,
    report_json    TEXT    NOT NULL,
    signature      TEXT
);

CREATE INDEX IF NOT EXISTS idx_history_created_at
    ON analysis_history (created_at DESC);

CREATE TABLE IF NOT EXISTS favorites (
    product_id TEXT PRIMARY KEY,
    added_at   TEXT NOT NULL
);

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
    source_url   TEXT,                                -- 可空：自造数据没有真实来源
    data_status  TEXT NOT NULL DEFAULT 'unverified',  -- verified / unverified
    updated_at   TEXT NOT NULL DEFAULT ''
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
"""

#: 同一组条件只存一条的唯一索引。
#: 部分索引（WHERE signature IS NOT NULL）让**老记录**（签名列为 NULL）
#: 与「没算出签名的报告」互不冲突，升级老库时不会因为历史重复数据而失败。
_SIGNATURE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_history_signature
    ON analysis_history (signature)
    WHERE signature IS NOT NULL;
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

    @property
    def created_at_label(self) -> str:
        """把 ISO 时间串显示成 `2026-10-12 21:30`。"""
        text = self.created_at.replace("T", " ")
        return text[:16]

    @property
    def score_label(self) -> str:
        return f"{self.top_score:.0f} 分" if self.top_score is not None else "无推荐"


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


def init_db(path: Path | None = None) -> None:
    """建表并做轻量迁移。可重复调用，已存在时不做任何改动。"""
    with connect(path) as connection:
        try:
            connection.executescript(_SCHEMA)
            _migrate(connection)
            connection.commit()
        except sqlite3.Error as exc:
            raise HistoryWriteError(
                "本地数据库初始化失败，历史记录功能暂不可用。",
                detail=f"{type(exc).__name__}: {exc}",
            ) from exc


def _migrate(connection: sqlite3.Connection) -> None:
    """老库升级。当前唯一的一步：给没有 signature 列的 analysis_history 补列。

    `CREATE TABLE IF NOT EXISTS` 对已存在的表不生效，所以老库的
    signature 列只能在这里补。列加了之后签名是 NULL，配合
    `_SIGNATURE_INDEX` 的部分索引，历史数据不需要回填也不会冲突。
    """
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(analysis_history)")
    }
    if "signature" not in columns:
        connection.execute("ALTER TABLE analysis_history ADD COLUMN signature TEXT")
    connection.execute(_SIGNATURE_INDEX)


def _ensure_ready(path: Path | None) -> None:
    """读操作前的准备。

    建表本身是写操作，但**触发它的是一次读取**——数据库文件损坏时，
    用户看到的原因应该是「读取失败」而不是「写入失败」。
    所以这里把写异常翻译成读异常。
    """
    try:
        init_db(path)
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
# 分析历史
# --------------------------------------------------------------------------


def save_analysis(report: DecisionReport, path: Path | None = None) -> int:
    """写入一条分析记录，返回记录 ID。

    **按条件指纹去重**：数据库里已有同指纹记录时不新增，
    直接返回已有记录的 ID。去重在数据库层完成——所以跨会话
    （刷新页面、重开浏览器后再提交同一组条件）同样只存一条，
    这是对 spec「同一组条件只存一条记录」场景的兑现。
    签名为空的报告（老版本生成的记录）不做去重，保持历史行为。

    Raises:
        HistoryWriteError: 写入失败。调用方应提示用户，但**不中断**当前页面——
        结果还在内存里，用户的这次分析没有白做。
    """
    top = report.recommendations[0] if report.recommendations else None

    try:
        init_db(path)
    except HistoryWriteError as exc:
        # init_db 失败时它说的是「数据库初始化失败」，但用户此刻做的是「保存」。
        # 报错要按用户正在做的事来说，不然他会以为是自己点错了地方。
        raise HistoryWriteError(
            "本次分析记录保存失败，结果仍可在当前页面查看。",
            detail=exc.detail,
        ) from exc

    signature = (report.signature or "").strip() or None

    try:
        with connect(path) as connection:
            if signature is not None:
                existing = connection.execute(
                    "SELECT id FROM analysis_history WHERE signature = ? LIMIT 1",
                    (signature,),
                ).fetchone()
                if existing is not None:
                    return int(existing["id"])

            try:
                cursor = connection.execute(
                    """
                    INSERT INTO analysis_history
                        (created_at, demand_summary, top_product, top_score,
                         result_count, report_json, signature)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.created_at,
                        report.demand_summary,
                        top.name if top else "",
                        top.score_total if top else None,
                        len(report.recommendations),
                        json.dumps(report.to_dict(), ensure_ascii=False),
                        signature,
                    ),
                )
                connection.commit()
                return int(cursor.lastrowid or 0)
            except sqlite3.IntegrityError:
                # 并发窗口内另一个会话刚好插入了同指纹记录。
                # 查回来按「已存在」处理；真的查不到再往外抛。
                connection.rollback()
                existing = connection.execute(
                    "SELECT id FROM analysis_history WHERE signature = ? LIMIT 1",
                    (signature,),
                ).fetchone()
                if existing is not None:
                    return int(existing["id"])
                raise
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "本次分析记录保存失败，结果仍可在当前页面查看。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def list_analyses(limit: int = 50, path: Path | None = None) -> list[HistoryEntry]:
    """列出历史记录，按时间由新到旧。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, demand_summary, top_product,
                       top_score, result_count
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

    return [
        HistoryEntry(
            id=row["id"],
            created_at=row["created_at"],
            demand_summary=row["demand_summary"],
            top_product=row["top_product"],
            top_score=row["top_score"],
            result_count=row["result_count"],
        )
        for row in rows
    ]


def get_analysis(entry_id: int, path: Path | None = None) -> DecisionReport | None:
    """按 ID 取回完整报告。不存在返回 None。"""
    try:
        with connect(path) as connection:
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


def delete_analysis(entry_id: int, path: Path | None = None) -> bool:
    """删除一条历史记录。返回是否真的删掉了。"""
    try:
        with connect(path) as connection:
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


# --------------------------------------------------------------------------
# 收藏
# --------------------------------------------------------------------------


def add_favorite(product_id: str, path: Path | None = None) -> None:
    """收藏一件商品。重复收藏不报错。"""
    try:
        init_db(path)
        with connect(path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO favorites (product_id, added_at) VALUES (?, ?)",
                (product_id, now_local().isoformat(timespec="seconds")),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "收藏保存失败。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def remove_favorite(product_id: str, path: Path | None = None) -> None:
    try:
        init_db(path)
    except HistoryWriteError as exc:
        raise HistoryWriteError("取消收藏失败。", detail=exc.detail) from exc

    try:
        with connect(path) as connection:
            connection.execute(
                "DELETE FROM favorites WHERE product_id = ?", (product_id,)
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise HistoryWriteError(
            "取消收藏失败。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def list_favorites(path: Path | None = None) -> list[tuple[str, str]]:
    """返回 [(product_id, added_at)]，按收藏时间由新到旧。"""
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            rows = connection.execute(
                "SELECT product_id, added_at FROM favorites ORDER BY added_at DESC"
            ).fetchall()
    except sqlite3.Error as exc:
        raise HistoryReadError(
            "收藏列表读取失败。",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    return [(row["product_id"], row["added_at"]) for row in rows]


def is_favorite(product_id: str, path: Path | None = None) -> bool:
    try:
        _ensure_ready(path)
        with connect(path) as connection:
            row = connection.execute(
                "SELECT 1 FROM favorites WHERE product_id = ?", (product_id,)
            ).fetchone()
            return row is not None
    except (sqlite3.Error, ZhigouError):
        # 收藏状态的读取失败不应该挡住界面渲染，按「未收藏」处理。
        # 这里刻意吞掉领域异常：它是一个渲染期的辅助查询，
        # 数据库坏了也该让用户看到商品列表，而不是整页报错。
        return False
