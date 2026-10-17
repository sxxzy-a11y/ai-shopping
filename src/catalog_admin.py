"""管理员在界面上维护商品数据（变更 `add-login-and-user-roles` §8）。

这一层把「界面输入」变成「可以写进商品库的记录」，顺路做完全部校验。
分成三层的老规矩：`product_store` 只管 SQL，这里管规则，界面只管渲染。

几条刻意的立场：

- **界面录入一律标为未核验**，`data_source` 自动写「管理员界面录入 · 未核验」。
  是谁填的**不等于**核实过——管理员能录入，不代表他逐条对照过来源。
- **修改不覆盖来源与核验状态**：改一个参数不该把一条带真实来源的数据
  变成「管理员界面录入」。
- **写入前复用既有的校验**（`ingest.validate_products` + `consistency`）：
  界面和命令行导入必须同一套标准，否则「界面上能存进去、脚本会被拦下」
  这种分裂迟早出现。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from src import comparison, config, consistency, ingest, product_store, scoring
from src.auth import User, require_admin
from src.data_loader import Product
from src.errors import (
    InvalidImageUrl,
    InvalidSpec,
    ProductValidationFailed,
    ProductStoreReadError,
)

#: 界面录入商品的来源说明。**不是「已核验」**，这是本变更反复强调的一点。
ENTRY_DATA_SOURCE = "管理员界面录入 · 未核验"

#: 界面上可以改的字段。**不在这个集合里的字段，界面改不动**——
#: `data_source` / `data_status` / `entered_by` 都在其外，正是要点：
#: 录入者不该能顺手把自己录的数据标成已核验。
EDITABLE_FIELDS: tuple[str, ...] = (
    "name",
    "model",
    "brand",
    "category",
    "price",
    "specs",
    "use_cases",
    "pros",
    "cons",
    "image_url",
    "source_url",
)


def validate_image_url(value: Any) -> str:
    """图片地址。空或纯空白 → 空串（表示「没有图片」）；否则必须是 http(s) 链接。

    纯空白**不能原样存进去**：早先 `_thumb` 的缺陷就是只判空不判空白，
    一个 `"   "` 渲染出了指向当前页面的 `<img>`。

    Raises:
        InvalidImageUrl: 不是 http/https 链接。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if not lowered.startswith(("http://", "https://")):
        raise InvalidImageUrl(detail=f"拒绝的图片地址：{text[:80]}")
    return text


def validate_specs(category: str, specs: Any) -> dict[str, Any]:
    """参数校验，返回清洗后的参数表。

    两条规则：

    1. **键必须属于该分类既有的参数集合**（`comparison.param_keys`）。
       写错一个键名不会被静默接受——那会让这件商品在比较表里缺一行，
       而没人知道为什么。
    2. **档位与数值必须落在既有区间内**（`scoring.spec_bounds`）。
       区间与评分读的是同一份定义。

    Raises:
        InvalidSpec: 键不认识或取值越界。
    """
    if specs in (None, ""):
        return {}
    if not isinstance(specs, Mapping):
        raise InvalidSpec("参数应当是一组「参数名：取值」。")

    allowed = set(comparison.param_keys(category))
    cleaned: dict[str, Any] = {}

    for raw_key, value in specs.items():
        key = str(raw_key).strip()
        if not key:
            continue

        if allowed and key not in allowed:
            raise InvalidSpec(
                f"参数「{key}」不属于该分类。可用的参数：{'、'.join(sorted(allowed))}",
                detail=f"category={category} key={key}",
            )

        if value is None or value == "":
            continue

        if key in ingest.TIER_KEYS:
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
                raise InvalidSpec(f"档位「{key}」应为 1–5 的整数，实际是 {value!r}。")
        else:
            bounds = scoring.spec_bounds(category, key)
            if bounds and isinstance(value, (int, float)) and not isinstance(value, bool):
                low, high = bounds
                # 区间两端可能反着写（重量越小越好），所以两种方向都接受
                lower, upper = min(low, high), max(low, high)
                if not lower <= float(value) <= upper:
                    raise InvalidSpec(
                        f"参数「{key}」的取值 {value} 超出既有区间 {lower}–{upper}。",
                        detail=f"category={category} key={key} value={value}",
                    )

        cleaned[key] = value

    return cleaned


def _clean(
    record: Mapping[str, Any], *, existing: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """把界面输入整成一条可写库的记录，并做完全部校验。

    `existing` 非空表示这是**修改**：来源与核验状态沿用原有的，
    不因为「界面改过」就变成界面录入。
    """
    category = str(record.get("category") or (existing or {}).get("category") or "")

    cleaned: dict[str, Any] = dict(record)
    cleaned["specs"] = validate_specs(category, record.get("specs"))
    cleaned["image_url"] = validate_image_url(record.get("image_url"))

    if existing is not None:
        # 来源与核验状态取自原记录：**界面不提供改它们的入口**
        cleaned["data_source"] = existing.get("data_source") or ""
        cleaned["data_status"] = existing.get("data_status") or config.STATUS_UNVERIFIED
        cleaned["entered_by"] = existing.get("entered_by") or ""
        cleaned["entered_at"] = existing.get("entered_at") or ""

    issues = list(ingest.validate_products([cleaned]))
    issues.extend(_consistency_issues(cleaned))
    if issues:
        raise ProductValidationFailed("；".join(issues), detail="；".join(issues))

    return cleaned


def _consistency_issues(record: Mapping[str, Any]) -> list[str]:
    """把记录包成 `Product` 跑一遍内部矛盾检查。

    界面录入的商品**矛盾就拒收**（而库里已有数据的矛盾只做标记）：
    新填的数据不该带着自相矛盾进库，那等于把问题留给以后的人去发现。
    """
    product = Product(
        id=str(record.get("id") or ""),
        name=str(record.get("name") or ""),
        category=str(record.get("category") or ""),
        price=record.get("price"),
        brand=str(record.get("brand") or ""),
        specs=dict(record.get("specs") or {}),
        use_cases=list(record.get("use_cases") or []),
        pros=list(record.get("pros") or []),
        cons=list(record.get("cons") or []),
        data_source=str(record.get("data_source") or ""),
        updated_at=str(record.get("updated_at") or ""),
        model=str(record.get("model") or ""),
    )
    return [f"{product.id}：{issue.reason}" for issue in consistency.check_product(product)]


def _find(product_id: str) -> dict[str, Any]:
    for record in product_store.load_product_records():
        if str(record.get("id")) == product_id:
            return record
    raise ProductStoreReadError(f"找不到商品 {product_id}。", detail=product_id)


def create_product(
    viewer: User | None,
    record: Mapping[str, Any],
    *,
    path: Path | None = None,
    stamp: str | None = None,
) -> dict[str, Any]:
    """新增一件商品。

    来源与核验状态**写死在这里**，不接受调用方传值：界面录入就是未核验。

    Raises:
        PermissionDenied: 不是管理员。
        InvalidSpec / InvalidImageUrl / ProductValidationFailed: 数据不合规。
    """
    require_admin(viewer)

    moment = stamp or datetime.now().strftime("%Y-%m-%d")
    prepared = dict(record)
    prepared["data_source"] = ENTRY_DATA_SOURCE
    prepared["data_status"] = config.STATUS_UNVERIFIED
    prepared["entered_by"] = viewer.username if viewer else ""
    prepared["entered_at"] = moment
    prepared["updated_at"] = prepared.get("updated_at") or moment
    prepared.setdefault("is_active", True)

    cleaned = _clean(prepared)
    product_store.save_products([cleaned], path=path, stamp=moment)
    return cleaned


def update_product(
    viewer: User | None,
    product_id: str,
    changes: Mapping[str, Any],
    *,
    path: Path | None = None,
    stamp: str | None = None,
) -> dict[str, Any]:
    """修改一件既有商品。**只有 `EDITABLE_FIELDS` 里的字段能改。**

    改价走既有的价格记录机制（`save_products` 里那套）：价格变了就新增
    一条记录、旧记录置为非当前，历史因此可追溯。
    """
    require_admin(viewer)

    existing = _find(product_id)
    prepared = dict(existing)
    for field in EDITABLE_FIELDS:
        if field in changes:
            prepared[field] = changes[field]
    prepared["id"] = product_id

    moment = stamp or datetime.now().strftime("%Y-%m-%d")
    prepared["updated_at"] = moment

    cleaned = _clean(prepared, existing=existing)
    product_store.save_products([cleaned], path=path, stamp=moment)
    return cleaned


def set_active(
    viewer: User | None,
    product_id: str,
    is_active: bool,
    *,
    path: Path | None = None,
) -> bool:
    """上下架。下架不删数据，价格记录与历史引用都留着。"""
    require_admin(viewer)
    return product_store.set_product_active(product_id, is_active, path=path)


def list_products(path: Path | None = None) -> list[dict[str, Any]]:
    """商品维护页要的商品清单（含在售状态与录入者）。"""
    return product_store.load_product_records(path)

# --------------------------------------------------------------------------
# 界面文本 ↔ 结构化字段（两个管理页共用）
# --------------------------------------------------------------------------


def specs_to_text(specs: Mapping[str, Any]) -> str:
    """参数对象 → 「一行一个 键: 值」的文本。"""
    return "\n".join(f"{key}: {value}" for key, value in (specs or {}).items())


def text_to_specs(text: str) -> dict[str, Any]:
    """「一行一个 键: 值」→ 参数字典；数字能转就转，转不动保留字符串。"""
    specs: dict[str, Any] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not key:
            continue
        try:
            number = float(value)
        except ValueError:
            specs[key] = value
        else:
            specs[key] = int(number) if number.is_integer() else number
    return specs


def lines_to_list(text: str) -> list[str]:
    """一行一条 → 字符串列表。"""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]

