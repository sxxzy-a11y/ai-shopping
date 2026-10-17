"""知识文档的增删（管理员）。

文档是**文件**：新增写到 `data/knowledge/custom/<slug>.md`，删除即删文件。
数据库只存派生出来的向量与索引，不存文档本身——语料需要可 diff、可回滚。

边界：
- 只允许品类级与服务级；商品级由商品字段合成，没有独立文件。
- 同一分类只允许一份指南（doc_id 会重复）。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from src import config
from src.errors import ZhigouError
from src.knowledge.corpus import load_documents

#: 允许由界面新增的文档类型。
ALLOWED_TYPES: tuple[str, ...] = ("category", "service")

#: 新建文档的落盘子目录。
CUSTOM_DIR = "custom"


class KnowledgeDocError(ZhigouError):
    """知识文档操作失败（可用于界面提示）。"""


def _knowledge_dir(path: Path | None = None) -> Path:
    return Path(path) if path is not None else config.knowledge_dir()


def _slug(title: str) -> str:
    """标题 → 文件名片段。保留中文与字母数字，其余折叠为 `-`。"""
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title.strip(), flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    return text or "doc"


def _unique_target(directory: Path, slug: str) -> Path:
    """同名文件自动追加 -2、-3……"""
    target = directory / f"{slug}.md"
    index = 2
    while target.exists():
        target = directory / f"{slug}-{index}.md"
        index += 1
    return target


def create_document(
    *,
    title: str,
    doc_type: str,
    body: str,
    source: str = "本项目整理（非厂商资料）",
    category: str = "",
    updated_at: str | None = None,
    knowledge_dir: Path | None = None,
) -> Path:
    """新增一份知识文档，返回落盘路径。

    Raises:
        KnowledgeDocError: 字段缺失、类型不允许、分类非法或该分类已有指南。
    """
    title = title.strip()
    body = body.strip()
    doc_type = doc_type.strip()
    category = category.strip()
    source = source.strip() or "本项目整理（非厂商资料）"

    if not title:
        raise KnowledgeDocError("标题不能为空。")
    if not body:
        raise KnowledgeDocError("正文不能为空。")
    if doc_type not in ALLOWED_TYPES:
        raise KnowledgeDocError(
            f"只能新增品类级或服务级资料（当前：{doc_type or '空'}）。"
        )
    if doc_type == "category":
        if not category:
            raise KnowledgeDocError("品类级资料必须选择商品分类。")
        if category not in config.CATEGORY_LABELS:
            raise KnowledgeDocError(
                f"分类「{category}」未在系统中登记。"
            )
        existing = [
            document
            for document in load_documents(_knowledge_dir(knowledge_dir))
            if document.doc_type == "category" and document.category == category
        ]
        if existing:
            raise KnowledgeDocError(
                f"「{config.category_label(category)}」已有选购指南"
                f"（{existing[0].title}），同一分类只允许一份指南。"
            )
    else:
        category = ""

    moment = updated_at or datetime.now().strftime("%Y-%m-%d")
    target_dir = _knowledge_dir(knowledge_dir) / CUSTOM_DIR
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = _unique_target(target_dir, _slug(title))
        content = (
            "---\n"
            f"title: {title}\n"
            f"type: {doc_type}\n"
            f"category: {category}\n"
            f"source: {source}\n"
            f"updated_at: {moment}\n"
            "---\n\n"
            f"{body}\n"
        )
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise KnowledgeDocError(
            "知识文档写入失败，请检查 data/knowledge 目录是否可写。"
        ) from exc
    return target


def delete_document(document_id: str, *, knowledge_dir: Path | None = None) -> Path:
    """删除一份**文件型**知识文档，返回被删路径。

    Raises:
        KnowledgeDocError: 文档不存在，或它是商品级（没有独立文件）。
    """
    documents = load_documents(_knowledge_dir(knowledge_dir))
    target = next((doc for doc in documents if doc.doc_id == document_id), None)
    if target is None:
        raise KnowledgeDocError(f"找不到资料「{document_id}」。")
    if target.doc_type == "product" or not target.source_path:
        raise KnowledgeDocError(
            "商品级资料由商品数据自动生成，没有独立文件；请到「商品维护」中编辑商品。"
        )

    path = Path(target.source_path)
    try:
        path.unlink()
    except OSError as exc:
        raise KnowledgeDocError("删除资料失败，请检查文件是否被占用。") from exc
    return path
