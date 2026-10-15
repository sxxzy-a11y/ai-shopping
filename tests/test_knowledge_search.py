"""检索入口的测试，兼作**固定查询集回归基线**。

这个文件是知识库的质量闸门。改语料、调类型系数或相关度阈值之后，
跑一遍就知道是变好了还是变坏了——否则「检索效果」只能靠感觉。
这也是后续「效果评测」子项目的雏形。

基线由两部分组成：

- **正例**：必须命中，且排第一的应当是**正确的那一类**文档
  （术语问题→服务级，通用选购→品类级，具体商品→商品级）
- **反例**：语料外的问题必须判定为检索不到
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import config, data_loader
from src.knowledge import corpus, search
from src.knowledge.corpus import Document
from src.knowledge.index import BM25Index
from src.knowledge.search import (
    EXCERPT_MAX_CHARS,
    Passage,
    extract_excerpt,
    search_knowledge,
)


@pytest.fixture(scope="module")
def index() -> BM25Index:
    """真实语料上的索引。模块级建一次——语料不变就没必要反复建。"""
    catalog = data_loader.load_catalog()
    documents = corpus.build_corpus(config.knowledge_dir(), catalog.products)
    return BM25Index(documents)


def _titles(passages: list[Passage]) -> list[str]:
    return [p.title for p in passages]


# --------------------------------------------------------------------------
# 片段抽取
# --------------------------------------------------------------------------


def test_excerpt_picks_the_relevant_paragraph():
    body = "## 无关段落\n\n这一段说的是别的事情。\n\n## 降噪\n\n主动降噪对低频有效。"
    excerpt = extract_excerpt(body, "主动降噪", max_chars=200)
    assert "主动降噪" in excerpt


def test_excerpt_falls_back_to_the_beginning():
    """一段都命不中时返回开头，**不能返回空字符串**。"""
    excerpt = extract_excerpt("第一段内容。\n\n第二段内容。", "完全不相关的词")
    assert excerpt.startswith("第一段")


def test_excerpt_is_bounded():
    body = "\n\n".join(f"第 {i} 段：降噪耳机" for i in range(50))
    assert len(extract_excerpt(body, "降噪", max_chars=200)) <= 201  # 允许结尾的省略号


def test_excerpt_of_empty_body_is_empty():
    assert extract_excerpt("", "任何问题") == ""


def test_single_paragraph_body_is_returned():
    assert extract_excerpt("只有一段", "内容") == "只有一段"


# --------------------------------------------------------------------------
# 引用信息
# --------------------------------------------------------------------------


def test_passage_citation_carries_source_and_time(index):
    passages = search_knowledge("主动降噪和被动降噪有什么区别", index=index, limit=1)
    assert passages
    citation = passages[0].citation
    assert passages[0].title in citation
    assert "更新于" in citation, "引用里必须带更新时间——这是需求明确要求的"


def test_passage_type_labels_are_chinese(index):
    passages = search_knowledge("主动降噪和被动降噪有什么区别", index=index, limit=2)
    labels = {p.type_label for p in passages}
    assert labels <= {"品类级", "服务级", "商品级"}


# --------------------------------------------------------------------------
# 相关度阈值（任务 4.4 / 4.5）
# --------------------------------------------------------------------------


def test_out_of_corpus_question_returns_nothing(index):
    """语料外的问题必须**明确判定为检索不到**，而不是硬返回弱相关结果。"""
    for question in ["今天天气怎么样", "周杰伦的新歌好听吗", "怎么修自行车"]:
        assert search_knowledge(question, index=index) == [], f"「{question}」不该有结果"


def test_threshold_changes_the_verdict(index):
    """调阈值会改变「有结果 / 无结果」的判定——阈值是真在起作用。"""
    question = "今天天气怎么样"

    assert search_knowledge(question, index=index, min_score=3.0) == []
    assert search_knowledge(question, index=index, min_score=0.1) != []


def test_blank_query_returns_nothing(index):
    assert search_knowledge("", index=index) == []
    assert search_knowledge("   ", index=index) == []


def test_limit_is_respected(index):
    passages = search_knowledge("耳机怎么选 通勤 降噪 佩戴", index=index, limit=2)
    assert len(passages) <= 2


# --------------------------------------------------------------------------
# 固定查询集回归基线（任务 5.1 / 5.2 / 5.4）
# --------------------------------------------------------------------------

#: 正例：(查询, 期待的排第一的文档标题片段, 期待的文档类型)
#: 查的是「排第一的**应该是哪一类**」，不是精确标题——语料润色不该让基线失效。
POSITIVE_CASES = [
    # 术语类 → 服务级或品类级。
    # 耳机那题不限定标题：FAQ 与耳机指南都有一节讲这个，谁排第一都算对。
    ("主动降噪和被动降噪有什么区别", None, {"服务级", "品类级"}),
    ("能效等级是什么意思", None, {"服务级"}),
    ("系统匹配评分是怎么算出来的", None, {"服务级"}),
    # 通用选购类 → 品类级
    ("通勤戴的耳机怎么选", "耳机", {"品类级"}),
    ("笔记本多重适合带出门", "笔记本电脑", {"品类级"}),
    ("机械键盘选什么轴", "键盘", {"品类级"}),
    ("婴儿车怎么挑", "母婴", {"品类级"}),
    ("沙发买什么材质", "家具", {"品类级"}),
    ("编程用什么电脑", "笔记本电脑", {"品类级"}),
    # 具体商品类 → 商品级
    ("静谷 ANC Pro 怎么样", "静谷", {"商品级"}),
    ("云梯 可折叠婴儿车", "云梯", {"商品级"}),
]

#: 反例：语料里没有对应资料，必须判定为检索不到。
NEGATIVE_QUERIES = [
    "今天天气怎么样",
    "周杰伦的新歌好听吗",
    "怎么给自行车补胎",
    "明天股市会涨吗",
]


@pytest.mark.parametrize("query, title_fragment, expected_types", POSITIVE_CASES)
def test_positive_cases_hit_the_right_kind_of_document(
    index, query: str, title_fragment, expected_types: set[str]
):
    passages = search_knowledge(query, index=index, limit=3)
    assert passages, f"「{query}」没有检索到任何资料"

    top = passages[0]
    assert top.type_label in expected_types, (
        f"「{query}」排第一的是 {top.type_label}「{top.title}」，"
        f"期待 {expected_types}"
    )
    if title_fragment:
        assert title_fragment in top.title, (
            f"「{query}」排第一的是「{top.title}」，期待包含「{title_fragment}」"
        )


@pytest.mark.parametrize("query", NEGATIVE_QUERIES)
def test_negative_cases_return_nothing(index, query: str):
    assert search_knowledge(query, index=index) == []


# --------------------------------------------------------------------------
# 设计文档里记录的实测查询（任务 5.4）
# --------------------------------------------------------------------------


def test_design_document_queries_still_hold(index):
    """复现 design.md「已实测验证」表里的四个查询。

    这四条是当初选 bigram + BM25 方案的依据，必须持续成立——
    它们同时也是这个方案为什么可行的证据。
    """
    # 术语问题命中、且第一名分数高于第二名
    hits = search_knowledge("主动降噪和被动降噪有什么区别", index=index, limit=2)
    assert len(hits) >= 2
    assert hits[0].score > hits[1].score

    # 通用选购问题命中对应品类的指南
    assert "笔记本电脑" in search_knowledge("笔记本多重适合带出门", index=index)[0].title

    # 语料外问题无任何结果
    assert search_knowledge("今天天气怎么样", index=index) == []


# --------------------------------------------------------------------------
# 语料变更后仍然成立
# --------------------------------------------------------------------------


def test_search_reflects_edited_corpus(tmp_path: Path):
    """改语料后重建索引，结果随之变化——不需要任何缓存机制参与。

    注意这里显式放低了 `min_score`：BM25 的**绝对分数随语料规模变化**
    （idf 依赖文档总数），单文档语料上的分数天然很低，用生产阈值会一律判成
    「检索不到」。这不影响线上——真实语料固定是百条量级，
    阈值就是按那个规模校准的。测试要越过阈值就直接指定一个。
    """
    from src.knowledge.corpus import load_documents

    (tmp_path / "new.md").write_text(
        "---\ntitle: 全新指南\ntype: service\nsource: 测试\nupdated_at: 2026-01-01\n---\n"
        "关于折叠屏手机的选购建议，注意转轴寿命。\n",
        encoding="utf-8",
    )
    index = BM25Index(load_documents(tmp_path))
    hits = search_knowledge("折叠屏手机转轴寿命", index=index, min_score=0.1)
    assert hits
    assert hits[0].title == "全新指南"


def test_absolute_scores_depend_on_corpus_size(index):
    """把上面的现象写成断言，免得以后有人把它当成 bug 去「修」。

    同一份文档，在单文档索引里的得分远低于在百条语料里的得分——
    阈值因此**必须按真实语料规模校准**，不能拿小样本试出来一个数就用。
    """
    from src.knowledge.corpus import Document

    body = "折叠屏手机的选购建议，注意转轴寿命。"
    alone = BM25Index(
        [Document(doc_id="x", title="T", body=body, doc_type="service",
                  source="s", updated_at="t")]
    )
    small_score = alone.search("折叠屏手机转轴寿命")[0].score

    assert small_score < config.KNOWLEDGE_MIN_SCORE
    assert index.size > 100, "真实语料规模变了，阈值需要重新校准"


def test_empty_corpus_yields_no_results():
    index = BM25Index([])
    assert search_knowledge("任何问题", index=index) == []


def test_document_with_only_title_still_does_not_crash():
    doc = Document(
        doc_id="x", title="标题", body="", doc_type="service", source="s", updated_at="t"
    )
    assert search_knowledge("标题", index=BM25Index([doc])) is not None


def test_excerpt_max_chars_is_a_sane_value():
    """片段长度常量本身要合理——太小读不出信息，太大等于没截。"""
    assert 200 <= EXCERPT_MAX_CHARS <= 800
