"""把 `data/products.json` 导入商品数据库。

用法::

    python scripts/migrate_products.py --dry-run          # 先看会写什么
    python scripts/migrate_products.py --mode replace     # 清空后导入（整套换数据时用）
    python scripts/migrate_products.py                    # 合并导入（同 ID 覆盖，其余保留）

商品数据存在 SQLite 里，`data/products.json` 是**种子文件**：库为空时应用会
自动导入一次，之后不再参与运行时读取。这个脚本用于在库已经有数据时**显式重新导入**。

**换整套数据集必须用 `--mode replace`。** 合并模式按商品 ID 覆盖，换数据集时
新数据的 ID 与老数据不同，于是新旧两批会同时留在库里——搜索结果里混着
已经不存在的商品，而没有任何地方会报错。

**来源字段如实转写，不做加工。** 数据集里写了什么 `source_url`、什么
`data_status`，就照原样入库。数据核验没核验过只有写数据的人知道，
导入脚本替他「顺手标成已核验」是最不该有的行为。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import config, data_loader, ingest, product_store  # noqa: E402
from src.errors import ZhigouError  # noqa: E402
from src.product_store import STATUS_UNVERIFIED  # noqa: E402


def _prepare(records: list[dict]) -> list[dict]:
    """补上数据集**没写**、但入库需要的派生字段。

    **只补缺，不覆盖。** 种子文件里显式写了的 `model` / `source_url` /
    `data_status` 一律以文件为准。

    上一版这里把 `source_url` 无条件清空——那是给「全部自造、没有来源可填」
    那批数据写的。换成有真实来源的数据以后再跑一次，会把 40 条来源链接
    全部抹掉，而且一路不报错。
    """
    prepared: list[dict] = []
    for record in records:
        item = dict(record)

        if not str(item.get("model") or "").strip():
            item["model"] = ingest.derive_model(
                str(item.get("name") or ""), str(item.get("brand") or "")
            )

        # `source_url` / `image_url` 缺键或为空都落地成空串，不做别的猜测。
        item["source_url"] = str(item.get("source_url") or "").strip()
        item["image_url"] = str(item.get("image_url") or "").strip()

        # 没写核验状态的，按**未核验**入库——没核实过就不该说是已核实。
        item["data_status"] = str(item.get("data_status") or STATUS_UNVERIFIED)

        # 价格记录的来源与采集时间：数据里给了就用，没给才从商品级说明兜底。
        item["price_source"] = str(
            item.get("price_source") or item.get("data_source") or ""
        )
        item["price_collected_at"] = str(
            item.get("price_collected_at") or item.get("updated_at") or ""
        )
        prepared.append(item)
    return prepared


def _report(prepared: list[dict], *, db_path: Path, mode: str) -> None:
    def count(predicate) -> int:
        return sum(1 for item in prepared if predicate(item))

    print("来源字段按数据集原样转写，不做加工：")
    print(f"  source_url     有 {count(lambda i: i['source_url'])} 条")
    print(f"  image_url      有 {count(lambda i: i['image_url'])} 条")
    print(f"  data_status    已核验 {count(lambda i: i['data_status'] == 'verified')} 条"
          f"（其余标为未核验）")
    print()
    print(f"目标数据库：{db_path}")
    print(f"导入模式：{'replace（先清空）' if mode == 'replace' else 'merge（同 ID 覆盖）'}")
    print(f"共 {len(prepared)} 条商品\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把种子数据集导入商品数据库")
    parser.add_argument(
        "--seed", default=str(config.products_path()), help="种子数据文件"
    )
    parser.add_argument(
        "--db", default=str(config.products_db_path()), help="目标商品数据库"
    )
    parser.add_argument(
        "--mode", choices=("merge", "replace"), default="replace",
        help="replace：清空后导入（默认，整套换数据时用）；merge：同 ID 覆盖",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只报告将要写入的内容，不写库"
    )
    args = parser.parse_args(argv)

    seed_path = Path(args.seed)
    db_path = Path(args.db)

    try:
        records, meta = data_loader.read_seed(seed_path)
        meta = {key: str(value) for key, value in meta.items()
                if key not in ("products", "source")}
    except ZhigouError as exc:
        print(f"读取种子数据失败：{exc}")
        return 1

    prepared = _prepare(records)
    _report(prepared, db_path=db_path, mode=args.mode)

    if args.dry_run:
        print("--dry-run：未写库。")
        return 0

    before = product_store.count_products(db_path)
    if args.mode == "replace":
        product_store.clear_products(db_path)
        written = product_store.save_products(prepared, path=db_path)
    else:
        written = product_store.save_products(prepared, path=db_path)
    product_store.save_dataset_meta(meta, path=db_path)

    after = product_store.count_products(db_path)
    print(f"导入前库中 {before} 条，本次写入 {written} 条，导入后 {after} 条。")
    if args.mode == "merge" and before and after > written:
        print("提示：合并模式下旧商品仍在库中。整套换数据请用 --mode replace。")

    # 冒烟验证：用应用自己的加载器读一遍，确认真的能跑起来
    catalog = data_loader.load_catalog(db_path)
    print(
        f"加载器验证通过：{len(catalog)} 条可用商品，"
        f"覆盖类别 {'、'.join(config.category_label(c) for c in catalog.present_categories())}"
    )
    with_image = sum(1 for p in catalog.products if p.has_image)
    print(f"其中带图片 {with_image} 条；信息不完整 {catalog.incomplete_count} 条。")
    if catalog.issues:
        print(f"加载问题 {len(catalog.issues)} 条，前几条：")
        for issue in catalog.issues[:5]:
            print(f"  - {issue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
