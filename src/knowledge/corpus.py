"""知识语料的加载与商品级条目的合成。

语料分两类，**都在本模块汇成同一种 `Document`**，检索层不区分来源：

- **手写文档**：`data/knowledge/` 下的 Markdown，带 front-matter 元数据。
  品类级（各品类的选购指南）与服务级（术语说明、系统能力说明）。
- **商品级条目**：**不写文件**，在加载时由商品字段合成。
  同一事实只保留一处来源，商品数据改了知识库自动跟着变，
  不会出现「改了规格忘了改介绍」的失同步（design.md D4）。

容错沿用项目的既有做法：单份文档格式非法只跳过该份并记日志，
不让整批加载失败。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src import config

if TYPE_CHECKING:  # 只为类型标注
    from src.data_loader import Product

logger = logging.getLogger("zhigou.knowledge")

#: 文档类型。检索时按类型加权（design.md D2）。
TYPE_CATEGORY = "category"
TYPE_SERVICE = "service"
TYPE_PRODUCT = "product"

#: front-matter 的正确结束标记。
_FRONT_MATTER_FENCE = "---"

#: 手写文档必须具备的字段。缺任何一个即跳过该文档。
_REQUIRED_META = ("title", "type", "source", "updated_at")

_ALLOWED_TYPES = {TYPE_CATEGORY, TYPE_SERVICE}


@dataclass(frozen=True)
class Document:
    """一份可检索的知识文档。

    Attributes:
        doc_id: 稳定标识，用于去重与调试（如 `category:headphone`）。
        title: 展示用标题。
        body: 正文，参与切分与打分。
        doc_type: 见 `TYPE_*` 常量。
        source: 来源说明。
        updated_at: 更新时间（字符串，原样展示）。
        product_id: 商品级条目的关联商品；手写文档为空。
    """

    doc_id: str
    title: str
    body: str
    doc_type: str
    source: str = ""
    updated_at: str = ""
    product_id: str = ""
    category: str = ""

    @property
    def searchable_text(self) -> str:
        """参与切分的文本。标题也算——标题往往就是用户在问的东西。"""
        return f"{self.title}\n{self.body}"

    @property
    def type_label(self) -> str:
        """文档类型的中文名，界面直接展示。"""
        return {
            TYPE_CATEGORY: "品类级",
            TYPE_SERVICE: "服务级",
            TYPE_PRODUCT: "商品级",
        }.get(self.doc_type, self.doc_type)


# --------------------------------------------------------------------------
# front-matter 解析
# --------------------------------------------------------------------------


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """拆出 front-matter 与正文。

    格式要求很松：文件**必须**以 `---` 开头，随后是 `key: value` 行，
    再由一行 `---` 结束。不满足时返回空元数据与全文——
    调用方（`document_from_text`）负责判定这算不算合法文档。

    Returns:
        (元数据字典, 正文)。正文已去掉前导空行。
    """
    if not text.startswith(_FRONT_MATTER_FENCE):
        return {}, text

    lines = text.splitlines()
    meta: dict[str, str] = {}
    for index in range(1, len(lines)):
        line = lines[index].strip()
        if line == _FRONT_MATTER_FENCE:
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            return meta, body
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    # 没有结束标记 —— 当作没有 front-matter，避免把正文当元数据吃掉
    return {}, text


def _strip_leading_title(body: str, title: str) -> str:
    """去掉正文开头与 front-matter 标题重复的一级标题。

    手写文档习惯先写一行 `# 标题`，但它和 front-matter 里的 title 是同一句话。
    留着会让抽取的片段以重复标题开头，也在索引里多出一份相同的二元组。
    只在**确实同名**时才剥——正文里的其他标题都保留。
    """
    lines = body.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") and stripped[2:].strip() == title.strip():
            return "\n".join(lines[index + 1 :]).lstrip("\n")
        break  # 第一行有内容且不是同名标题 —— 不动它
    return body


def document_from_text(text: str, *, fallback_id: str) -> Document | None:
    """把一份 Markdown 文本解析成 `Document`。不合法返回 None。"""
    meta, body = parse_front_matter(text)

    missing = [key for key in _REQUIRED_META if not meta.get(key)]
    if missing:
        logger.warning("知识文档 %s 缺少元数据 %s，已跳过", fallback_id, missing)
        return None

    doc_type = meta["type"]
    if doc_type not in _ALLOWED_TYPES:
        logger.warning(
            "知识文档 %s 的 type=%s 不在允许范围 %s，已跳过",
            fallback_id,
            doc_type,
            sorted(_ALLOWED_TYPES),
        )
        return None

    body = _strip_leading_title(body, meta["title"])
    if not body.strip():
        logger.warning("知识文档 %s 正文为空，已跳过", fallback_id)
        return None

    # 优先用类别做 ID，便于与商品类别对齐；没有类别时退回文件名。
    slug = meta.get("category") or fallback_id.replace("\\", "/").rsplit("/", 1)[-1]
    slug = slug.removesuffix(".md")
    return Document(
        doc_id=f"{doc_type}:{slug}",
        title=meta["title"],
        body=body,
        doc_type=doc_type,
        source=meta["source"],
        updated_at=meta["updated_at"],
        category=meta.get("category", ""),
    )


def load_documents(knowledge_dir: Path) -> list[Document]:
    """扫描语料目录，加载全部合法的 Markdown 文档。

    目录不存在时返回空列表——**不抛异常**。知识问答会提示没有资料，
    商品搜索、筛选、比较、推荐四项功能不受影响。
    """
    if not knowledge_dir.is_dir():
        logger.info("知识语料目录不存在：%s（知识问答将无资料可用）", knowledge_dir)
        return []

    documents: list[Document] = []
    for path in sorted(knowledge_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("知识文档 %s 读取失败，已跳过", path, exc_info=True)
            continue
        document = document_from_text(text, fallback_id=str(path))
        if document is not None:
            documents.append(document)
    return documents


# --------------------------------------------------------------------------
# 商品级条目合成
# --------------------------------------------------------------------------


def _join(values: Iterable[Any], *, sep: str = "；") -> str:
    return sep.join(str(v) for v in values if str(v).strip())


def spec_line(specs: dict[str, Any]) -> str:
    """把参数拼成一行，跳过空值。

    参数名用 `config.SPEC_LABELS` 里的**中文标签**而不是原始键名：
    用户会用「内存」「续航」提问，不会用 `ram_gb`、`battery_h`——
    写英文键名会让中文查询命中不到商品条目。
    """
    parts: list[str] = []
    for key, value in specs.items():
        if value in (None, ""):
            continue
        label = config.SPEC_LABELS.get(key, key)
        if isinstance(value, bool):
            # 布尔值渲染成 Python 的 True/False 既不好读，也是个无用的检索单元。
            value = "支持" if value else "不支持"
        parts.append(f"{label} {value}")
    return "、".join(parts)


def synthesize_product_document(product: Product) -> Document:
    """由商品字段合成一条知识条目。

    模板刻意保持与商品字段**字面一致**——不做转述、不加形容词，
    这样它不会与商品数据本身产生分歧（`harden-ai-enhancement` 的矛盾检测
    正在盯着这类问题）。
    """
    lines = [
        f"{product.name}（品牌 {product.brand or '未知'}，"
        f"类别 {product.category_label}，参考价 {product.price_label}）。"
    ]
    if product.specs:
        lines.append(f"参数：{spec_line(product.specs)}。")
    if product.use_cases:
        lines.append(f"适用场景：{_join(product.use_cases, sep='、')}。")
    if product.pros:
        lines.append(f"优点：{_join(product.pros)}。")
    if product.cons:
        lines.append(f"不足：{_join(product.cons)}。")

    return Document(
        doc_id=f"{TYPE_PRODUCT}:{product.id}",
        title=product.name or product.id,
        body="".join(lines),
        doc_type=TYPE_PRODUCT,
        source=product.data_source,
        updated_at=product.updated_at,
        product_id=product.id,
        category=product.category,
    )


def build_corpus(
    knowledge_dir: Path, products: Sequence[Product] = ()
) -> list[Document]:
    """汇总手写语料与商品级条目，构成完整检索语料。"""
    documents = load_documents(knowledge_dir)
    documents.extend(synthesize_product_document(p) for p in products)
    return documents
