"""把 `data/products.json` 迁移进商品数据库。

用法::

    python scripts/migrate_products.py --dry-run     # 先看会写什么
    python scripts/migrate_products.py               # 真正写入

商品数据现在存在 SQLite 里，这个脚本负责把自带的示例数据集**搬进去**。
之后 `data/products.json` 只在库为空时作为种子被自动导入一次，
不再参与运行时读取。

**来源如实填写，不伪造。** 这 112 条全是本项目自造的，没有任何真实来源可填：
`source_url` 留空、`data_status` 标为未核验。字段与流程建好，
等接入真实数据时自然填上——但**当前这批就是未核验的演示数据**，
不因为「字段有了」就标成已核实。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import config, data_loader, ingest, product_store  # noqa: E402
from src.product_store import STATUS_UNVERIFIED  # noqa: E402
from src.errors import ZhigouError  # noqa: E402


def _prepare(records: list[dict]) -> list[dict]:
    """补上迁移时该定的字段。

    - **型号**：从名称派生，派生不出来就留空（服装家具本来没有型号概念）
    - **来源与核验状态**：如实标注——全是自造数据，没有真实来源
    """
    prepared: list[dict] = []
    for record in records:
        item = dict(record)
        item["model"] = ingest.derive_model(
            str(item.get("name") or ""), str(item.get("brand") or "")
        )
        # 逐条来源字段：留空。全批共用一条说明放在 data_source 里，
        # 那已经如实写了「本项目自行构造」。
        item["source_url"] = ""
        item["data_status"] = STATUS_UNVERIFIED
        # 价格记录的来源与采集时间取自现有字段——它们本来就是这批数据的说明。
        item["price_source"] = str(item.get("data_source") or "")
        item["price_collected_at"] = str(item.get("updated_at") or "")
        prepared.append(item)
    return prepared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把示例数据集迁移进商品数据库")
    parser.add_argument(
        "--seed", default=str(config.products_path()), help="种子数据文件"
    )
    parser.add_argument(
        "--db", default=str(config.products_db_path()), help="目标商品数据库"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只报告将要写入的内容，不写库"
    )
    args = parser.parse_args(argv)

    seed_path = Path(args.seed)
    db_path = Path(args.db)

    try:
        records, meta = data_loader.read_seed(seed_path)
    except ZhigouError as exc:
        print(f"读取种子数据失败：{exc}")
        return 1

    prepared = _prepare(records)
    with_model = sum(1 for r in prepared if r["model"])
    with_price = sum(1 for r in prepared if r.get("price") not in (None, ""))

    print(f"种子文件：{seed_path}")
    print(f"目标数据库：{db_path}")
    print(f"读到 {len(prepared)} 条商品")
    print(f"  能派生型号：{with_model} 条；无型号概念留空：{len(prepared) - with_model} 条")
    print(f"  有价格、会建价格记录：{with_price} 条")
    print()
    print("来源与核验状态按实情填写：")
    print("  source_url     留空（这批数据没有真实来源可填）")
    print("  data_status    未核验")
    print("  price_source   取自各条的 data_source")
    print("  collected_at   取自各条的 updated_at")

    if args.dry_run:
        print("\n--dry-run：未写库。")
        return 0

    written = product_store.save_products(prepared, path=db_path)
    product_store.save_dataset_meta(meta, path=db_path)

    total = product_store.count_products(db_path)
    print(f"\n已写入 {written} 条；库中现有 {total} 条商品。")

    # 冒烟验证：用应用自己的加载器读一遍
    catalog = data_loader.load_catalog(db_path)
    statuses = {p.status_label for p in catalog.products}
    print(
        f"加载器验证通过：{len(catalog)} 条可用商品，"
        f"覆盖类别 {'、'.join(config.category_label(c) for c in catalog.present_categories())}"
    )
    print(f"核验状态：{'、'.join(sorted(statuses))}")
    for issue in catalog.issues:
        print(f"  提示：{issue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
