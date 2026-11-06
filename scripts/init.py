"""一键准备本地运行环境。

四件事，全部幂等，可重复执行：

1. 检查 Python 版本；
2. 商品库为空时导入 `data/products.json` 种子；
3. 账号表为空时创建初始管理员（**随机密码只在这里打印一次**，
   云端部署时比等应用启动后再去翻日志更可靠）；
4. 打印一份现状体检：商品数、知识语料、评测用例。

用法：
    python scripts/init.py            # 初始化（不动已有数据）
    python scripts/init.py --check    # 只体检，不创建任何东西
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import accounts, config, database, product_store  # noqa: E402
from src.errors import ZhigouError, to_user_message  # noqa: E402

#: 与 requirements.txt 中 numpy 2.3.5 的 Requires-Python 保持一致。
MIN_PYTHON = (3, 11)


def _check_python() -> None:
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(
            f"需要 Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 或更高版本，"
            f"当前是 {sys.version_info.major}.{sys.version_info.minor}。"
        )


def _seed_products() -> str:
    """库空才导种子——`seed_from_json` 明确把「空不空」的判断留给调用方。"""
    try:
        existing = product_store.count_products()
    except ZhigouError as exc:
        return f"商品库不可读：{to_user_message(exc)}"

    if existing:
        return f"商品库已有 {existing} 条商品，跳过种子导入。"

    try:
        imported = product_store.seed_from_json()
    except ZhigouError as exc:
        return f"种子导入失败：{to_user_message(exc)}"
    return f"已从 data/products.json 导入 {imported} 条商品。"


def _ensure_admin() -> str:
    """账号表为空时建管理员。返回给终端看的一段说明（可能含明文密码）。"""
    try:
        created = accounts.ensure_initial_admin()
    except ZhigouError as exc:
        return f"初始管理员创建失败：{to_user_message(exc)}"

    if created is None:
        try:
            total = database.count_users()
        except ZhigouError:
            total = 0
        return f"账号表已有 {total} 个账号，跳过初始管理员创建。"

    _admin, notice = created
    return notice or "初始管理员已创建（密码来自配置，无需打印）。"


def _count_knowledge_files() -> int:
    directory = config.knowledge_dir()
    try:
        return sum(1 for _ in directory.rglob("*.md"))
    except OSError:
        return 0


def _count_cases() -> int:
    path = PROJECT_ROOT / "data" / "evaluation" / "cases.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    cases = payload.get("cases")
    return len(cases) if isinstance(cases, list) else 0


def _report() -> list[str]:
    lines: list[str] = []

    try:
        lines.append(f"商品库：{product_store.count_products()} 条商品")
    except ZhigouError as exc:
        lines.append(f"商品库：不可读（{to_user_message(exc)}）")

    try:
        lines.append(f"账号：{database.count_users()} 个")
    except ZhigouError as exc:
        lines.append(f"账号：不可读（{to_user_message(exc)}）")

    lines.append(f"知识语料：{_count_knowledge_files()} 份 Markdown")
    lines.append(f"评测用例：{_count_cases()} 条")
    lines.append(f"历史库：{config.database_path()}")
    lines.append(f"商品库文件：{config.products_db_path()}")

    configured = []
    if config.is_ai_configured():
        configured.append("对话模型")
    if config.is_embedding_configured():
        configured.append("向量检索")
    lines.append(
        "AI 能力："
        + ("、".join(configured) if configured else "未配置（本地规则模式）")
    )

    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="准备本地运行环境")
    parser.add_argument(
        "--check",
        action="store_true",
        help="只打印现状，不导入种子、不创建管理员",
    )
    args = parser.parse_args(argv)

    _check_python()
    print("=" * 60)
    print("智购参谋 · 本地环境准备")
    print("=" * 60)

    if not args.check:
        print("[1/2] " + _seed_products())
        print("[2/2] " + _ensure_admin())

    print("\n现状体检")
    for line in _report():
        print(f"  · {line}")

    print("\n下一步：streamlit run app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
