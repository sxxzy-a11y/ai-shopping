"""知识语料加载与商品级合成的测试。

语料是**人写的文件**，所以这里重点是容错：格式错了、目录没了、
正文空了，都不该让应用崩掉或整批失败——沿用项目一贯的
「单条降级、不牵连整体」做法。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import data_loader
from src.knowledge import corpus
from src.knowledge.corpus import (
    TYPE_CATEGORY,
    TYPE_PRODUCT,
    TYPE_SERVICE,
    build_corpus,
    document_from_text,
    load_documents,
    parse_front_matter,
    spec_line,
    synthesize_product_document,
)


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


VALID = """---
title: 测试指南
type: category
category: laptop
source: 测试来源
updated_at: 2026-01-01
---

正文第一段。

正文第二段。
"""


# --------------------------------------------------------------------------
# front-matter 解析
# --------------------------------------------------------------------------


def test_front_matter_is_split_from_body():
    meta, body = parse_front_matter(VALID)
    assert meta["title"] == "测试指南"
    assert meta["category"] == "laptop"
    assert body.startswith("正文第一段")


def test_text_without_front_matter_returns_whole_body():
    meta, body = parse_front_matter("没有元数据的正文")
    assert meta == {}
    assert body == "没有元数据的正文"


def test_unterminated_front_matter_is_treated_as_body():
    """少了结束的 `---` 时当作没有元数据，**不能把正文当元数据吃掉**。"""
    text = "---\ntitle: 半截\n\n这里是正文"
    meta, body = parse_front_matter(text)
    assert meta == {}
    assert "这里是正文" in body


def test_quoted_values_are_unwrapped():
    meta, _ = parse_front_matter('---\ntitle: "带引号的标题"\n---\n正文')
    assert meta["title"] == "带引号的标题"


def test_colons_inside_values_are_preserved():
    """值里含冒号时只按**第一个**冒号切分。"""
    meta, _ = parse_front_matter("---\ntitle: 标题：带冒号\n---\n正文")
    assert meta["title"] == "标题：带冒号"


# --------------------------------------------------------------------------
# 文档合法性
# --------------------------------------------------------------------------


def test_valid_document_is_loaded():
    doc = document_from_text(VALID, fallback_id="x.md")
    assert doc is not None
    assert doc.doc_type == TYPE_CATEGORY
    assert doc.doc_id == "category:laptop"


def test_missing_metadata_is_skipped():
    text = "---\ntitle: 只有标题\n---\n正文"
    assert document_from_text(text, fallback_id="x.md") is None


@pytest.mark.parametrize("bad_type", ["unknown", "PRODUCT", "", "商品"])
def test_unknown_type_is_skipped(bad_type: str):
    text = (
        f"---\ntitle: T\ntype: {bad_type}\nsource: S\nupdated_at: 2026-01-01\n---\n正文"
    )
    assert document_from_text(text, fallback_id="x.md") is None


def test_empty_body_is_skipped():
    text = "---\ntitle: T\ntype: service\nsource: S\nupdated_at: 2026-01-01\n---\n\n  \n"
    assert document_from_text(text, fallback_id="x.md") is None


def test_duplicate_title_heading_is_stripped():
    """正文开头与 title 同名的一级标题会被去掉，避免片段以重复标题开头。"""
    doc = document_from_text(VALID, fallback_id="x.md")
    assert doc is not None
    assert not doc.body.startswith("#")


def test_different_heading_is_kept():
    text = VALID.replace("正文第一段", "# 另一个标题")
    doc = document_from_text(text, fallback_id="x.md")
    assert doc is not None
    assert "另一个标题" in doc.body


def test_document_id_falls_back_to_filename():
    """没有 category 的文档（如 FAQ）用文件名生成 ID。"""
    text = "---\ntitle: T\ntype: service\nsource: S\nupdated_at: 2026-01-01\n---\n正文"
    doc = document_from_text(text, fallback_id="path/to/faq.md")
    assert doc is not None
    assert doc.doc_id == f"{TYPE_SERVICE}:faq"


# --------------------------------------------------------------------------
# 目录级加载
# --------------------------------------------------------------------------


def test_missing_directory_returns_empty(tmp_path: Path):
    """目录不存在返回空列表，**不抛异常**——其余功能要照常可用。"""
    assert load_documents(tmp_path / "不存在") == []


def test_bad_document_does_not_block_the_others(tmp_path: Path):
    _write(tmp_path, "good.md", VALID)
    _write(tmp_path, "bad.md", "没有元数据的文件")
    _write(tmp_path, "also-bad.md", "---\ntitle: 缺字段\n---\n正文")

    docs = load_documents(tmp_path)
    assert len(docs) == 1
    assert docs[0].doc_id == "category:laptop"


def test_subdirectories_are_scanned(tmp_path: Path):
    _write(tmp_path, "category/laptop.md", VALID)
    _write(tmp_path, "faq.md", VALID.replace("category: laptop", "category: service"))
    names = {d.doc_id for d in load_documents(tmp_path)}
    assert len(names) == 2


def test_non_markdown_files_are_ignored(tmp_path: Path):
    _write(tmp_path, "note.txt", VALID)
    _write(tmp_path, "guide.md", VALID)
    assert len(load_documents(tmp_path)) == 1


# --------------------------------------------------------------------------
# 商品级合成
# --------------------------------------------------------------------------


@pytest.fixture
def sample_product():
    return data_loader.load_catalog().get("LP001")


def test_product_document_carries_key_fields(sample_product):
    doc = synthesize_product_document(sample_product)
    assert doc.doc_type == TYPE_PRODUCT
    assert doc.product_id == sample_product.id
    assert doc.title == sample_product.name
    assert doc.doc_id == f"{TYPE_PRODUCT}:{sample_product.id}"


def test_product_document_uses_chinese_labels(sample_product):
    """参数名用中文标签——用户问「内存」，不会问 `ram_gb`。"""
    doc = synthesize_product_document(sample_product)
    assert "内存" in doc.body
    assert "ram_gb" not in doc.body


def test_booleans_render_in_chinese(sample_product):
    """布尔值渲染成「支持/不支持」，不出现 Python 的 True/False。"""
    doc = synthesize_product_document(sample_product)
    assert "False" not in doc.body
    assert "True" not in doc.body


def test_product_document_includes_pros_and_cons(sample_product):
    doc = synthesize_product_document(sample_product)
    assert sample_product.pros[0] in doc.body
    assert sample_product.cons[0] in doc.body


def test_spec_line_skips_empty_values():
    assert spec_line({"a": 1, "b": None, "c": ""}) == "a 1"


def test_product_document_does_not_contradict_the_source(sample_product):
    """合成条目不能与商品数据本身分歧——商品名、价格都要原样出现。"""
    doc = synthesize_product_document(sample_product)
    assert sample_product.name in doc.body
    assert f"{sample_product.price:.0f}" in doc.body


# --------------------------------------------------------------------------
# 汇总
# --------------------------------------------------------------------------


def test_build_corpus_combines_written_and_synthesized(tmp_path: Path, catalog):
    _write(tmp_path, "laptop.md", VALID)
    docs = build_corpus(tmp_path, catalog.products)

    types = {d.doc_type for d in docs}
    assert types == {TYPE_CATEGORY, TYPE_PRODUCT}
    assert len(docs) == 1 + len(catalog.products)


def test_build_corpus_without_products_still_works(tmp_path: Path):
    _write(tmp_path, "laptop.md", VALID)
    assert len(build_corpus(tmp_path, [])) == 1


# --------------------------------------------------------------------------
# 真实语料
# --------------------------------------------------------------------------


def test_real_corpus_is_well_formed():
    """项目自带的语料必须全部合法——写错格式会让知识问答静默变哑。"""
    documents = load_documents(corpus_config_dir())
    assert len(documents) >= 11, "品类指南或 FAQ 缺失"

    for doc in documents:
        assert doc.title
        assert doc.source
        assert doc.updated_at
        assert doc.body.strip()
        assert doc.doc_type in {TYPE_CATEGORY, TYPE_SERVICE}


def test_real_corpus_covers_every_category():
    """每个品类都要有选购指南——缺哪个，问那个品类就答不上来。"""
    from src import config

    covered = {
        doc.category
        for doc in load_documents(corpus_config_dir())
        if doc.doc_type == TYPE_CATEGORY
    }
    missing = set(config.CATEGORY_LABELS) - covered
    assert missing == set(), f"这些品类缺选购指南：{sorted(missing)}"


def corpus_config_dir() -> Path:
    from src import config

    return config.knowledge_dir()
