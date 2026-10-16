"""外部商品数据接入：平台原始记录 → 内部商品结构。

定位
----
本模块只做**转换与校验**，不负责取数——HTTP 请求、文件读取都在
`scripts/fetch_products.py` 里。这样转换规则可以脱离网络做单元测试，
将来换数据库、换爬虫、换手工表格，这一层都不用动。

接入分三步：

1. **取数**：`scripts/fetch_products.py` 的 `ProductSource` 拿到平台原始记录
2. **转换**：本模块 `normalize_record()` 把原始记录映射成内部商品结构
3. **校验**：`validate_products()` 在写文件**之前**拦住不合法数据

字段契约（内部结构）与「真实数据注意事项」见 `docs/platform-integration.md`。

关于档位（tier）
----------------
本项目为规则评分设定了 1–5 的档位（如 `energy_grade` 能效等级、`cpu_tier`
处理器档位），5 最高。真实平台数据通常给的是「一级能效」「8 核」这类
原始表述，需要在这里折算成档位——`parse_energy_grade()` 和 `to_tier()`
是给这个用途的示例，其余品类按同样思路补映射。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from src import config

# --------------------------------------------------------------------------
# 字段别名：平台叫法 → 内部字段
# --------------------------------------------------------------------------
#
# 各家平台的字段名都不一样。接入新平台时先在这里补齐别名，
# 不要在 normalize_record 里写 if-else。

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "id": ("id", "product_id", "sku", "sku_id", "商品id", "商品ID", "货号"),
    "name": ("name", "title", "product_name", "标题", "商品名称"),
    "category": ("category", "category_name", "cat", "类目", "商品类目", "分类"),
    "price": ("price", "sale_price", "current_price", "价格", "售价", "到手价"),
    "brand": ("brand", "brand_name", "shop_name", "品牌", "店铺", "商家"),
    "specs": ("specs", "attributes", "params", "spec", "参数", "规格", "属性"),
    "use_cases": ("use_cases", "scenes", "适用场景", "场景"),
    "pros": ("pros", "advantages", "highlights", "优点", "亮点", "卖点"),
    "cons": ("cons", "disadvantages", "drawbacks", "缺点", "不足"),
    "data_source": ("data_source", "source", "数据来源"),
    "updated_at": ("updated_at", "fetched_at", "更新时间", "抓取时间"),
    # 溯源字段。缺了它们，接入进来的商品会丢掉来源与图片，
    # 而那种「字段悄悄没了」最难发现——数据看着都对，只是少了东西。
    "model": ("model", "型号", "规格型号"),
    "source_url": ("source_url", "url", "来源链接", "资料链接", "原始链接"),
    "image_url": ("image_url", "image", "图片", "图片地址", "主图", "图片链接"),
    "data_status": ("data_status", "核验状态", "状态"),
}

#: 平台类目名 → 内部类别键。键为小写，匹配时先精确后包含。
#: 只登记商品库真正覆盖的四个类别；接入新类别时，先在 `config.CATEGORY_LABELS`
#: 和 `config.SCORING_WEIGHTS` 里补上该类别的权重表，再到这里来加映射，
#: 否则导进来的商品会落进一个没有权重、也没有中文名的类别里。
DEFAULT_CATEGORY_MAP: dict[str, str] = {
    "笔记本电脑": "laptop",
    "笔记本": "laptop",
    "手机": "phone",
}

#: 平台参数名 → 内部 specs 键。
#:
#: 中文那半**从 `config.SPEC_LABELS` 反查生成**，不手抄。平台导出的参数名就是
#: 这些中文标签（「处理器」「续航」「驱动单元」），而标签本身又是界面上的显示名——
#: 同一份东西抄两遍，就一定会出现「界面叫这个、导入时认不出这个」。
#: 手写的那部分是各平台自己的叫法，与标签不同名，才需要单独登记。
#:
#: 未登记的键会**原样保留**（比较表能显示，只是没有中文标签），
#: 所以宁可先少映射几个，也不要乱映射。
SPEC_ALIASES: dict[str, str] = {
    **{label: key for key, label in config.SPEC_LABELS.items()},
    "内存容量": "ram_gb",
    "硬盘容量": "storage_gb",
    "处理器型号": "cpu",
    "芯片型号": "chip",
}

#: 1–5 档位型的 specs 键。这些键的取值必须是 1–5 的整数（5 最高）。
#: 从 `config.SPEC_LABELS` 推导：凡是以 `_tier` 结尾的都是档位。
#: 不手写清单——手写的那份一定会和标签表漂移。
TIER_KEYS: frozenset[str] = frozenset(
    key for key in config.SPEC_LABELS if key.endswith("_tier")
)

#: 中文数字 → 数值，用于「一级能效」这类表述。
_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

#: 「能效等级」的中文档位 → 内部 1–5（5 = 一级，最省电）。
#: 注意方向：项目内部 5 最高，而「一级能效」是最好的，所以一级映射到 5。
_ENERGY_GRADE_MAP = {"一级": 5, "二级": 4, "三级": 3, "四级": 2, "五级": 1}


# --------------------------------------------------------------------------
# 取值与解析
# --------------------------------------------------------------------------


def _first(raw: Mapping[str, Any], field: str) -> Any:
    """按别名列表取第一个非空值。"""
    for key in _FIELD_ALIASES.get(field, (field,)):
        if key in raw and raw[key] not in (None, "", [], {}):
            return raw[key]
    return None


def parse_price(value: Any) -> float | None:
    """把「￥2,999.00」「2999元」这类价格文本转成数字。解析不了返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.]", "", value.replace(",", ""))
        try:
            number = float(cleaned)
        except ValueError:
            return None
        return number if number > 0 else None
    return None


def parse_energy_grade(value: Any) -> int | None:
    """能效等级 → 内部 1–5（5 = 一级能效）。

    接受「一级」「1级」「一级能效」「5」等写法。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        grade = int(value)
        return grade if 1 <= grade <= 5 else None
    text = str(value).strip()
    for label, mapped in _ENERGY_GRADE_MAP.items():
        if label in text:
            return mapped
    match = re.search(r"([1-5])", text)
    return int(match.group(1)) if match else None


def to_tier(value: Any, *, scale_max: int = 5) -> int | None:
    """把数值/中文档位折算成 1–5 的档位（5 最高）。

    平台给的可能不是 1–5 分制（例如满分 10 分），按比例折算并夹紧。
    中文「三星」这类表述也支持。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        for char, digit in _CN_DIGITS.items():
            if char in text:
                return max(1, min(scale_max, digit))
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if scale_max <= 0:
        return None
    scaled = round(number / scale_max * 5)
    return max(1, min(5, scaled))


def _to_list(value: Any) -> list[str]:
    """把列表或「、/，/;」分隔的字符串统一成字符串列表。"""
    if isinstance(value, str):
        parts = re.split(r"[、，,;；|]", value)
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalize_specs(value: Any) -> dict[str, Any]:
    """specs 兼容三种入参：dict、JSON 字符串、「键:值;键:值」文本。"""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            value = parsed
        else:
            pairs = {}
            for chunk in re.split(r"[;；\n]", text):
                if ":" in chunk:
                    key, _, val = chunk.partition(":")
                elif "：" in chunk:
                    key, _, val = chunk.partition("：")
                else:
                    continue
                pairs[key.strip()] = val.strip()
            value = pairs
    if not isinstance(value, Mapping):
        return {}

    specs: dict[str, Any] = {}
    for key, val in value.items():
        internal = SPEC_ALIASES.get(str(key).strip(), str(key).strip())
        if not internal:
            continue
        if internal == "energy_grade":
            parsed_grade = parse_energy_grade(val)
            if parsed_grade is not None:
                specs[internal] = parsed_grade
            continue
        if internal in TIER_KEYS:
            tier = to_tier(val) if not isinstance(val, bool) else None
            if tier is not None:
                specs[internal] = tier
            continue
        specs[internal] = val
    return specs


# --------------------------------------------------------------------------
# 类目归一
# --------------------------------------------------------------------------


def normalize_category(
    raw_category: Any, mapping: Mapping[str, str] | None = None
) -> str | None:
    """把平台类目名映射成内部类别键，认不出来返回 None。

    匹配顺序：映射表精确匹配 → 映射表包含匹配 → 内部类别中文名包含匹配。
    """
    if raw_category is None:
        return None
    text = str(raw_category).strip()
    if not text:
        return None

    table = {key.lower(): val for key, val in (mapping or DEFAULT_CATEGORY_MAP).items()}
    lowered = text.lower()
    if lowered in table:
        return table[lowered]
    for key, value in table.items():
        if key in lowered:
            return value
    for internal_key, label in config.CATEGORY_LABELS.items():
        if label in text:
            return internal_key
    return None


# --------------------------------------------------------------------------
# 记录归一
# --------------------------------------------------------------------------


#: 型号里的「型号特征」——几乎都含阿拉伯数字。
#: 靠它区分「AirBook 14」与「纯棉 T恤」：后者虽然含拉丁字母，但不是型号。
_MODEL_DIGIT = re.compile(r"\d")

#: 纯中文的词块。型号一般是拉丁字母与数字，纯中文的多半是品类词或修饰语。
_PURE_CJK = re.compile(r"^[一-鿿]+$")


def derive_model(name: str, brand: str) -> str:
    """从商品名里派生出型号。**拿不准就返回空串。**

    做法很保守：去掉品牌名，再剥掉首尾的纯中文词块，剩下的**必须含阿拉伯数字**
    才算型号。这条数字要求是用来挡「纯棉 T恤」这类假阳性的——它含拉丁字母，
    但那不是型号。

    宁可少派生也不造错：一个错的型号比没有型号更糟，它会被当成事实展示，
    而系统无从知道它是错的。

    Examples:
        「轻羽 AirBook 14」→「AirBook 14」·「锋刃 X15 游戏本」→「X15」
        「云梯 可折叠婴儿车」→「」（全中文，没有型号概念）
        「织风 纯棉 T恤」→「」（有拉丁字母但不含数字，不是型号）
    """
    if not name:
        return ""

    rest = name.replace(brand, " ").strip() if brand else name.strip()
    if not rest:
        return ""

    tokens = rest.split()
    # 剥掉首尾的纯中文词块：「冰箱 BCD-318」→「BCD-318」
    while tokens and _PURE_CJK.match(tokens[0]):
        tokens.pop(0)
    while tokens and _PURE_CJK.match(tokens[-1]):
        tokens.pop()

    candidate = " ".join(tokens).strip()
    if not candidate or not _MODEL_DIGIT.search(candidate):
        return ""
    return candidate


def fill_derived_fields(record: dict) -> dict:
    """补上能从现有字段派生出来的东西。

    目前只有**型号**：从名称里派生。名称里没有就留空——
    「没有型号」是事实，不是待填的空。

    这个函数被两条入口共用：外部数据接入（`normalize_record`）与
    种子导入（`product_store.seed_from_json`）。**两条入口都要过它**，
    否则「型号有没有」会取决于数据是怎么进来的——那种不一致最难查。
    """
    if not record.get("model"):
        record["model"] = derive_model(
            str(record.get("name") or ""), str(record.get("brand") or "")
        )
    return record


def normalize_record(
    raw: Mapping[str, Any],
    *,
    source_label: str,
    category_map: Mapping[str, str] | None = None,
    today: date | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """把一条平台原始记录转成内部商品结构。

    Returns:
        (商品记录, 问题列表)。商品记录为 None 表示这条无法使用——
        调用方应把问题记录进日志，而不是让整批数据失败。

    `data_source` 会统一盖成 `source_label` + 抓取日期：真实性标注
    是硬要求，**不允许**沿用平台自己的文案。同样，尽量也**不要**
    把平台的营销文案直接塞进 pros/cons——先用它们自己的字段，
    实在没有再退回简短截断，并保留来源说明。
    """
    issues: list[str] = []

    product_id = str(_first(raw, "id") or "").strip()
    if not product_id:
        return None, ["缺少商品 id，已跳过"]

    name = str(_first(raw, "name") or "").strip()
    if not name:
        issues.append("缺少商品名称")

    price = parse_price(_first(raw, "price"))
    if price is None:
        issues.append("价格缺失或无法解析")

    category = normalize_category(_first(raw, "category"), category_map)
    if category is None:
        issues.append(f"类目无法识别：{_first(raw, 'category')!r}")

    brand = str(_first(raw, "brand") or "").strip()

    moment = today or date.today()
    record = {
        "id": product_id,
        "name": name,
        "category": category or "",
        "price": price,
        "brand": brand,
        "specs": _normalize_specs(_first(raw, "specs")),
        "use_cases": _to_list(_first(raw, "use_cases")),
        "pros": _to_list(_first(raw, "pros")),
        "cons": _to_list(_first(raw, "cons")),
        "data_source": f"{source_label} · 抓取于 {moment.isoformat()}",
        "updated_at": moment.isoformat(),
        # 溯源字段原样透传。data_status 缺省为未核验——**没标过就是没核验**，
        # 不该因为「接入方没说」就默认成已核验。
        "source_url": str(_first(raw, "source_url") or "").strip(),
        "image_url": str(_first(raw, "image_url") or "").strip(),
        "data_status": str(_first(raw, "data_status") or "").strip() or "unverified",
    }
    # 补上能从名称派生的型号——入口一（外部数据接入）
    fill_derived_fields(record)
    return record, issues


# --------------------------------------------------------------------------
# 写前校验
# --------------------------------------------------------------------------


def validate_products(products: Sequence[Mapping[str, Any]]) -> list[str]:
    """写文件前的严格校验。返回问题列表，空列表代表全部通过。

    与 `data_loader` 的宽容策略**刻意不同**：读取端要容忍老数据、坏数据，
    让人还能用；写入端必须严格，坏数据根本不该写进文件。
    """
    issues: list[str] = []
    seen: set[str] = set()

    for index, product in enumerate(products, start=1):
        pid = str(product.get("id") or "").strip()
        if not pid:
            issues.append(f"第 {index} 条：缺少 id")
            continue
        if pid in seen:
            issues.append(f"第 {index} 条：id 重复 {pid}")
        seen.add(pid)

        if not str(product.get("name") or "").strip():
            issues.append(f"{pid}：缺少名称")
        if not str(product.get("category") or "").strip():
            issues.append(f"{pid}：缺少类别")
        elif product["category"] not in config.CATEGORY_LABELS:
            issues.append(
                f"{pid}：类别 {product['category']} 未在 config.CATEGORY_LABELS 登记"
            )

        price = product.get("price")
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
            issues.append(f"{pid}：价格非法（{price!r}）")

        if not isinstance(product.get("specs"), Mapping):
            issues.append(f"{pid}：specs 应为对象")

        for key in ("use_cases", "pros", "cons"):
            if not isinstance(product.get(key), (list, tuple)):
                issues.append(f"{pid}：{key} 应为列表")

        for key, value in (product.get("specs") or {}).items():
            if key in TIER_KEYS and value is not None:
                if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
                    issues.append(f"{pid}：档位 {key} 应为 1–5 的整数（实际 {value!r}）")

        source = str(product.get("data_source") or "")
        if not source:
            issues.append(f"{pid}：缺少数据来源说明")

    return issues


# --------------------------------------------------------------------------
# 合并与落盘
# --------------------------------------------------------------------------


def merge_products(
    existing: Sequence[Mapping[str, Any]],
    incoming: Sequence[Mapping[str, Any]],
    *,
    mode: str = "merge",
) -> list[dict[str, Any]]:
    """把新数据并进现有数据集。

    - `merge`（默认）：按 id 覆盖已有商品，新 id 追加到末尾；不在本次抓取
      范围内的老商品**保留**、顺序不变。适合增量更新或平台只返回部分商品。
    - `replace`：完全用新数据替换。适合全量抓取。

    Raises:
        ValueError: mode 不是 merge / replace。
    """
    if mode not in ("merge", "replace"):
        raise ValueError(f"未知的合并模式：{mode!r}")

    new_items = [dict(item) for item in incoming]
    if mode == "replace":
        return new_items

    by_id = {str(item.get("id")): dict(item) for item in incoming}
    merged: list[dict[str, Any]] = []
    used: set[str] = set()
    for item in existing:
        key = str(item.get("id"))
        if key in by_id:
            merged.append(by_id[key])
            used.add(key)
        else:
            merged.append(dict(item))
    # 全新的商品按抓取顺序追加在末尾
    merged.extend(item for key, item in by_id.items() if key not in used)
    return merged


def build_document(
    products: Sequence[Mapping[str, Any]],
    *,
    meta: Mapping[str, Any] | None = None,
    source_label: str = "",
) -> dict[str, Any]:
    """组装最终写盘的文档结构（兼容 data_loader 的两种顶层结构约定）。"""
    document: dict[str, Any] = {
        "dataset_name": "智购参谋商品数据集",
        "disclaimer": (
            "本数据集由接入脚本从外部数据源生成。商品信息（价格、参数、优缺点）"
            "来自所标注的数据源，会随抓取时间变化；使用与展示时必须保留"
            "data_source 标注，不得表述为实时价格或真实用户评价。"
        ),
        "updated_at": date.today().isoformat(),
        "source": source_label,
        "spec_tier_note": (
            "specs 中以 *_tier 结尾的档位字段为本项目为规则评分设定的 "
            "1–5 分级（5 最高），由接入脚本按映射规则折算，"
            "不是厂商跑分或专业评测结果。"
        ),
        "products": [dict(item) for item in products],
    }
    if meta:
        # 保留调用方提供的额外元信息（如数据集名称、免责声明）
        document.update(dict(meta))
    return document


def write_document(path: str | Path, document: Mapping[str, Any]) -> None:
    """写 JSON 文件。先写临时文件再替换，避免中途失败留下半个文件。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temp.replace(target)
