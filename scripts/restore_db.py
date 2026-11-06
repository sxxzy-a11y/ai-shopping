"""数据库备份、校验与恢复。

历史库（账号 / 分析历史 / 收藏 / 偏好）与商品库分开存，
用 `--db history|products|all` 选择目标，默认 `all`。

备份用 `VACUUM INTO`，会把 WAL 里尚未 checkpoint 的数据一并写进新文件，
比直接复制 `.db` 安全。恢复前会**先自动备份当前库**——恢复本身也是破坏性操作。

用法：
    python scripts/restore_db.py --backup
    python scripts/restore_db.py --backup --db products
    python scripts/restore_db.py --verify storage/backups/history-20261106-201500.db
    python scripts/restore_db.py --restore <bak> --db history
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import config  # noqa: E402

BACKUP_DIR = PROJECT_ROOT / "storage" / "backups"

#: 恢复一份陌生文件前，至少要确认它带着这张表——否则恢复完是半个空库。
REQUIRED_TABLES: dict[str, tuple[str, ...]] = {
    "history": ("users", "analysis_history", "favorites", "user_preferences"),
    "products": ("products", "product_prices", "dataset_meta"),
}

DB_CHOICES = ("history", "products", "all")


def _target_path(name: str) -> Path:
    return config.database_path() if name == "history" else config.products_db_path()


def _selected(name: str) -> list[str]:
    return list(REQUIRED_TABLES) if name == "all" else [name]


def backup_one(name: str) -> Path:
    """把库导出一份带时间戳的备份，返回备份路径。"""
    source = _target_path(name)
    if not source.exists():
        raise SystemExit(f"{name} 库不存在：{source}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"{name}-{stamp}.db"
    if target.exists():
        raise SystemExit(f"备份目标已存在，请稍后重试：{target}")

    # 路径来自配置而非用户输入，这里仍按 SQL 字面量规则转义单引号。
    quoted = str(target).replace("'", "''")
    connection = sqlite3.connect(source)
    try:
        connection.isolation_level = None  # VACUUM 不能在事务里执行
        connection.execute(f"VACUUM INTO '{quoted}'")
    except sqlite3.Error as exc:
        raise SystemExit(f"{name} 库备份失败：{exc}") from exc
    finally:
        connection.close()
    return target


def verify_one(path: Path, name: str) -> None:
    """确认这是一份完整、可读、表齐全的备份。"""
    if not path.exists():
        raise SystemExit(f"文件不存在：{path}")

    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise SystemExit(f"打不开这个文件：{exc}") from exc

    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise SystemExit(f"完整性检查未通过：{integrity}")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    except sqlite3.DatabaseError as exc:
        raise SystemExit(f"不是可读的 SQLite 文件：{exc}") from exc
    finally:
        connection.close()

    missing = [table for table in REQUIRED_TABLES[name] if table not in tables]
    if missing:
        raise SystemExit(
            f"备份缺少 {name} 库应有的表：{missing}（现有 {sorted(tables)}）"
        )


def restore_one(path: Path, name: str) -> tuple[Path, Path | None]:
    """校验后恢复。返回 (目标路径, 恢复前的安全备份路径)。"""
    verify_one(path, name)
    target = _target_path(name)

    safety = backup_one(name) if target.exists() else None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

    # WAL 副文件属于旧库，留着会和恢复后的主文件内容对不上。
    for suffix in ("-wal", "-shm"):
        sidecar = target.with_name(target.name + suffix)
        sidecar.unlink(missing_ok=True)

    return target, safety


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="备份、校验与恢复本地数据库")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--backup", action="store_true", help="导出一份备份")
    action.add_argument("--verify", metavar="BAK", help="校验指定备份文件")
    action.add_argument("--restore", metavar="BAK", help="用指定备份覆盖当前库")
    parser.add_argument("--db", choices=DB_CHOICES, default="all", help="目标库")
    args = parser.parse_args(argv)

    if args.verify:
        path = Path(args.verify)
        for name in _selected(args.db):
            verify_one(path, name)
            print(f"OK  {name}：{path}")
        return 0

    if args.restore:
        path = Path(args.restore)
        for name in _selected(args.db):
            target, safety = restore_one(path, name)
            print(f"已恢复 {name} → {target}")
            if safety is not None:
                print(f"  恢复前的库已备份到 {safety}")
        return 0

    for name in _selected(args.db):
        written = backup_one(name)
        print(f"已备份 {name} → {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
