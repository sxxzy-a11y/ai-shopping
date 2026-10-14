"""商品数据接入 CLI：从外部数据源抓取商品并生成 data/products.json。

用法示例
--------

1) 先用 CSV 通道跑通全流程（零依赖、可离线验证）：

    # 生成一份列名模板，按你平台的导出结构改它
    python scripts/fetch_products.py --write-template data/platform_export.csv

    # 用 CSV 生成商品数据（合并模式：同 id 覆盖，其余保留）
    python scripts/fetch_products.py --source csv --input data/platform_export.csv

    # 先看结果不写文件
    python scripts/fetch_products.py --source csv --input xx.csv --dry-run

2) 接入真实平台 API 时，实现一个 ProductSource 子类（见下方 ApiSource），
   然后：

    python scripts/fetch_products.py --source api --mode replace

环境变量
--------
- ZHIGOU_PLATFORM_BASE_URL   平台 API 根地址，例如 https://open.example.com
- ZHIGOU_PLATFORM_API_KEY    API 密钥（只从环境变量读，不落盘）
- ZHIGOU_PLATFORM_SOURCE_LABEL
                            数据来源标注，会写进每条商品的 data_source，
                            例如「来自 XX 平台开放接口」。不设置时按数据源
                            名称自动生成。

设计说明
--------
- 取数（本文件）与转换/校验（src/ingest.py）分离：转换规则可脱离网络单测
- **写盘前严格校验**：校验不过就不写文件，绝不把坏数据落库
- 写盘采用「临时文件 + 替换」，中途失败不会留下半个文件
- 真实数据的真实性标注是硬要求：data_source 由本脚本统一盖章，
  不沿用平台自己的文案
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import config, data_loader, ingest  # noqa: E402

DEFAULT_PRODUCTS_PATH = PROJECT_ROOT / "data" / "products.json"


# --------------------------------------------------------------------------
# 数据源适配器
# --------------------------------------------------------------------------


class ProductSource(ABC):
    """数据源适配器接口。

    子类只需要实现 `fetch()`：返回一批「原始记录」（字典列表），
    字段叫什么名字都行——统一映射在 `src/ingest.py` 的 `_FIELD_ALIASES`
    里配置。
    """

    #: 展示用的数据源名称，会进入 data_source 标注。
    name: str = "未知数据源"

    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        """拉取原始记录。"""

    def describe(self) -> str:
        return self.name


class CsvSource(ProductSource):
    """从 CSV 文件读取。适合平台后台导出、人工整理的数据。

    列名用平台的叫法即可（如「商品ID」「标题」「价格」「参数」），
    别名映射见 `src/ingest.py`；「参数」列支持三种写法：
    JSON 对象、`键:值;键:值` 文本、或留空。
    """

    def __init__(self, path: Path, *, name: str = "平台导出 CSV") -> None:
        self._path = Path(path)
        self.name = name

    def fetch(self) -> list[dict[str, Any]]:
        if not self._path.is_file():
            raise FileNotFoundError(f"CSV 文件不存在：{self._path}")
        with self._path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for row in reader]

    def describe(self) -> str:
        return f"{self.name}（{self._path.name}）"


class ApiSource(ProductSource):
    """HTTP JSON API 的**骨架**。

    真实平台各不相同，这里给出最常见的一类结构：分页返回 JSON，
    列表在某个字段里。接入时你只需要：

    1. 按平台的鉴权方式补全 `_headers()`
    2. 按平台的分页协议改 `_next_page()`（页码 / cursor / 总数）
    3. 按返回结构改 `_extract_items()`

    除此之外的流程（转换、校验、写盘）都不需要动。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        path: str = "/products",
        page_size: int = 100,
        max_pages: int = 50,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._path = path
        self._page_size = page_size
        self._max_pages = max_pages
        self.name = "平台开放接口"

    # --- 接入点 1：鉴权 ---------------------------------------------------
    def _headers(self) -> dict[str, str]:
        # TODO(接入方)：按平台要求改成 AppKey/签名/Token 等。
        return {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}

    # --- 接入点 2：分页协议 ------------------------------------------------
    def _params(self, page: int) -> dict[str, Any]:
        # TODO(接入方)：改成平台的分页参数名（page/offset/cursor...）。
        return {"page": page, "page_size": self._page_size}

    # --- 接入点 3：返回结构 ------------------------------------------------
    def _extract_items(self, payload: Any) -> list[dict[str, Any]]:
        """从一页响应里取出商品记录列表。

        兼容最常见的几种包装：裸数组、{"items": [...]}、
        {"data": {"list": [...]}}。平台结构特殊时改这里。
        """
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, Mapping):
            for key in ("items", "list", "products", "result"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
                if isinstance(value, Mapping):
                    for nested in ("items", "list", "products"):
                        nested_value = value.get(nested)
                        if isinstance(nested_value, list):
                            return [
                                item for item in nested_value if isinstance(item, dict)
                            ]
        return []

    def fetch(self) -> list[dict[str, Any]]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - 依赖已随项目安装
            raise RuntimeError("缺少 httpx 依赖，无法调用接口") from exc

        collected: list[dict[str, Any]] = []
        with httpx.Client(
            base_url=self._base_url, headers=self._headers(), timeout=30.0
        ) as client:
            for page in range(1, self._max_pages + 1):
                response = client.get(self._path, params=self._params(page))
                response.raise_for_status()
                items = self._extract_items(response.json())
                if not items:
                    break
                collected.extend(items)
                if len(items) < self._page_size:
                    break
        return collected


# --------------------------------------------------------------------------
# 模板与报告
# --------------------------------------------------------------------------


def write_csv_template(path: Path) -> None:
    """生成 CSV 列名模板，按平台导出结构改名即可。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["商品ID", "标题", "商品类目", "价格", "品牌", "参数", "适用场景", "优点", "缺点"]
    rows = [
        [
            "EX0001",
            "示例 商品名称",
            "家用电器",
            "2999",
            "示例品牌",
            '{"容量": 318, "能效等级": "一级", "耐用档位": 5}',
            "家庭、厨房",
            "一级能效，长期省电",
            "体积偏大",
        ]
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"已写入模板：{path}")
    print("说明：「参数」列支持 JSON 对象或「键:值;键:值」文本。")


def _print_report(
    *,
    source: ProductSource,
    products: list[dict[str, Any]],
    skipped: int,
    issues: list[str],
) -> None:
    print(f"数据源：{source.describe()}")
    print(f"转换成功：{len(products)} 条；跳过：{skipped} 条")
    if issues:
        print(f"校验/转换问题共 {len(issues)} 条：")
        for issue in issues[:30]:
            print("  -", issue)
        if len(issues) > 30:
            print(f"  ...（其余 {len(issues) - 30} 条略）")


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def _resolve_source(args: argparse.Namespace) -> ProductSource:
    if args.source == "csv":
        if not args.input:
            raise SystemExit("--source csv 需要提供 --input <csv 路径>")
        return CsvSource(Path(args.input))

    base_url = os.environ.get("ZHIGOU_PLATFORM_BASE_URL", "").strip()
    api_key = os.environ.get("ZHIGOU_PLATFORM_API_KEY", "").strip()
    if not base_url:
        raise SystemExit(
            "未配置 ZHIGOU_PLATFORM_BASE_URL。请先在环境变量里设置平台接口地址。"
        )
    if not api_key:
        raise SystemExit(
            "未配置 ZHIGOU_PLATFORM_API_KEY。请在环境变量里设置平台密钥。"
        )
    return ApiSource(
        base_url=base_url,
        api_key=api_key,
        path=args.api_path,
        page_size=args.page_size,
    )


def _source_label(source: ProductSource, explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env_label = os.environ.get("ZHIGOU_PLATFORM_SOURCE_LABEL", "").strip()
    if env_label:
        return env_label
    return f"来自{source.describe()}"


def _load_existing(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """读现有数据集。文件不存在或损坏时返回空集合并说明。"""
    if not path.is_file():
        return [], {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"警告：现有数据集无法解析（{exc}），将按空数据集处理。")
        return [], {}
    if isinstance(raw, dict):
        products = raw.get("products", [])
        meta = {k: v for k, v in raw.items() if k != "products"}
        return [p for p in products if isinstance(p, dict)], meta
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)], {}
    return [], {}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从外部数据源生成 data/products.json（写盘前严格校验）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--source", choices=["csv", "api"], default="csv",
                        help="数据源类型（默认 csv）")
    parser.add_argument("--input", help="CSV 模式下的输入文件路径")
    parser.add_argument("--out", default=str(DEFAULT_PRODUCTS_PATH),
                        help="输出文件（默认 data/products.json）")
    parser.add_argument("--mode", choices=["merge", "replace"], default="merge",
                        help="与现有数据的合并方式（默认 merge：同 id 覆盖，新 id 追加）")
    parser.add_argument("--limit", type=int, default=0,
                        help="只处理前 N 条（调试用，0 表示不限制）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只转换与校验，不写文件")
    parser.add_argument("--write-template", metavar="CSV_PATH",
                        help="生成 CSV 列名模板后退出")
    parser.add_argument("--source-label", default="",
                        help="数据来源标注（覆盖环境变量与默认值）")
    parser.add_argument("--api-path", default="/products",
                        help="API 模式的商品列表路径")
    parser.add_argument("--page-size", type=int, default=100,
                        help="API 模式每页条数")

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.write_template:
        write_csv_template(Path(args.write_template))
        return 0

    source = _resolve_source(args)
    label = _source_label(source, args.source_label)

    print(f"开始抓取：{source.describe()} ...")
    raw_items = source.fetch()
    if args.limit > 0:
        raw_items = raw_items[: args.limit]
    print(f"原始记录：{len(raw_items)} 条")

    products: list[dict[str, Any]] = []
    issues: list[str] = []
    skipped = 0
    for raw in raw_items:
        record, record_issues = ingest.normalize_record(raw, source_label=label)
        if record is None:
            skipped += 1
            issues.extend(record_issues or ["未知问题"])
            continue
        products.append(record)
        if record_issues:
            issues.extend(f"{record['id']}：{item}" for item in record_issues)

    issues.extend(ingest.validate_products(products))
    _print_report(source=source, products=products, skipped=skipped, issues=issues)

    if issues:
        print("\n发现不合格数据，**未写入文件**。修好数据后重试。")
        return 1

    if args.dry_run:
        print("\n--dry-run：校验通过，未写文件。")
        return 0

    out_path = Path(args.out)
    existing, meta = _load_existing(out_path)
    merged = ingest.merge_products(existing, products, mode=args.mode)
    document = ingest.build_document(merged, meta=meta, source_label=label)
    ingest.write_document(out_path, document)
    print(f"\n已写入 {out_path}：共 {len(merged)} 条商品"
          f"（本次转换 {len(products)} 条，模式 {args.mode}）。")

    # 最后用应用自己的加载器做一次冒烟验证
    catalog = data_loader.load_catalog(out_path)
    print(f"加载器验证通过：{len(catalog)} 条可用商品，"
          f"覆盖类别 {'、'.join(config.category_label(c) for c in catalog.present_categories())}")
    for issue in catalog.issues:
        print(f"  提示：{issue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
