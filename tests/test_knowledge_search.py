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
    passages = search_knowledge("处理器档位是什么意思", index=index, limit=1)
    assert passages
    citation = passages[0].citation
    assert passages[0].title in citation
    assert "更新于" in citation, "引用里必须带更新时间——这是需求明确要求的"


def test_passage_type_labels_are_chinese(index):
    passages = search_knowledge("处理器档位是什么意思", index=index, limit=2)
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
    passages = search_knowledge("笔记本 手机 拍照 续航 重量 内存 芯片", index=index, limit=2)
    assert len(passages) <= 2


def test_result_count_never_exceeds_the_configured_cap(index):
    """条数上限是硬约束——即使很多命中都过了阈值。"""
    passages = search_knowledge(
        "笔记本 手机 拍照 续航 重量 内存 芯片 处理器",
        index=index,
        min_score=0.0,  # 刻意放开绝对阈值，让上限来兜
    )
    assert 0 < len(passages) <= config.KNOWLEDGE_MAX_RESULTS


def test_relative_cut_drops_hits_an_order_of_magnitude_below_the_top(index):
    """与第一名不同量级的弱命中被丢弃——它们过了绝对阈值，但对作答只有稀释。"""
    # 实测分布：19.20 / 1.26 / 1.09 —— 只有第一名在自己量级里
    passages = search_knowledge("系统匹配评分是怎么算出来的", index=index, limit=5)
    assert len(passages) == 1, f"应当只剩最高分那一条，实际 {[round(p.score, 2) for p in passages]}"


def test_relative_cut_keeps_a_close_second_hit(index):
    """并列相关的第二条要保住——截断不能把「同一量级」的资料误伤。"""
    # 实测分布：8.57 / 4.13 / 2.41 —— 第二条在同量级，第三条不是
    passages = search_knowledge("处理器档位是什么意思", index=index, limit=5)
    assert len(passages) == 2, f"应当保留前两条，实际 {[round(p.score, 2) for p in passages]}"


def test_excerpt_covers_the_key_numbers_of_the_matched_section(index):
    """片段要覆盖命中小节的关键数字，而不是只给相邻段落。

    实测踩过：问「笔记本多重适合带出门」时，只给「命中段 + 相邻段」会让
    片段里没有 1.2–1.4kg 这行，模型只能回答「资料没有覆盖」。片段如今
    不再直接展示，覆盖关键信息比行文连贯更重要。
    """
    passages = search_knowledge("笔记本多重适合带出门", index=index, limit=1)
    assert passages
    excerpt = passages[0].excerpt
    assert "整机重量" in excerpt and "1.2–1.4kg" in excerpt, excerpt


# --------------------------------------------------------------------------
# 品牌加权（refine-ai-qa：宽问题也要能答）
# --------------------------------------------------------------------------


def test_brand_only_question_hits_brand_products(index):
    """只问品牌（「华为怎么样」）也必须有结果——品牌词短、BM25 分低，
    不加权就会被阈值挡成「检索不到」，而用户明明问到了点子上。"""
    for query in ("华为怎么样", "红米怎么样"):
        passages = search_knowledge(query, index=index, limit=3)
        assert passages, f"「{query}」不该返回空"
        assert all("华为" in p.title or "红米" in p.title for p in passages), (
            f"「{query}」的结果应是该品牌的商品：{[p.title for p in passages]}"
        )


def test_brand_boost_respects_the_mentioned_category(index):
    """「华为笔记本怎么样」不该把华为的手机顶上来。"""
    passages = search_knowledge("华为笔记本怎么样", index=index, limit=3)
    titles = [p.title for p in passages]
    assert any("MateBook" in title for title in titles), titles
    assert all("Mate 70" not in title for title in titles), (
        "问的是笔记本，手机条目不该进入结果"
    )


def test_brand_boost_does_not_rescue_off_corpus_queries(index):
    """品牌加权只对语料里的品牌生效，且结果只限该品牌的商品。"""
    # 戴森不在商品库品牌里——怎么问都不该有结果
    assert search_knowledge("戴森吸尘器怎么样", index=index) == []
    # 小米是库里的品牌：问「小米加湿器」没有加湿器资料，
    # 但返回的若有结果，也只能是小米的商品，而不是别的品牌
    passages = search_knowledge("小米加湿器怎么样", index=index)
    assert all("小米" in p.title for p in passages)


# --------------------------------------------------------------------------
# 固定查询集回归基线（任务 5.1 / 5.2 / 5.4）
# --------------------------------------------------------------------------

#: 正例：(查询, 期待的排第一的文档标题片段, 期待的文档类型)
#: 查的是「排第一的**应该是哪一类**」，不是精确标题——语料润色不该让基线失效。
POSITIVE_CASES = [
    # 术语类 → 服务级或品类级。
    ("处理器档位是什么意思", None, {"服务级"}),
    ("为什么没有销量和用户评价", None, {"服务级"}),
    ("系统匹配评分是怎么算出来的", None, {"服务级"}),
    # 通用选购类 → 品类级。每个品类各来一题，缺哪类就说明那篇指南没起到作用。
    ("笔记本多重适合带出门", "笔记本电脑", {"品类级"}),
    ("手机拍照怎么选", "手机", {"品类级"}),
    ("编程用什么电脑", "笔记本电脑", {"品类级"}),
    ("手机电池容量大续航就好吗", "手机", {"品类级"}),
    # 具体商品类 → 商品级。商品名取自数据集，改数据时这条要跟着改。
    ("苹果 iPhone 16 怎么样", "iPhone 16", {"商品级"}),
    ("华为 MateBook X Pro 怎么样", "MateBook X Pro", {"商品级"}),
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
    """复现 design.md「已实测验证」表里的查询性质。

    这批查询是当初选 bigram + BM25 方案的依据，必须持续成立——
    它们同时也是这个方案为什么可行的证据。
    （品类聚焦后语料移除了耳机与 ANC 术语，术语题换成「处理器档位」。）
    """
    # 术语问题命中、且第一名分数高于第二名
    hits = search_knowledge("处理器档位是什么意思", index=index, limit=2)
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
    # 不写死条数：语料规模随商品数与指南数变化，钉一个数只会让删文档的人
    # 顺手把阈值改小。这条要守的是「真实语料确实是个成规模的语料」——
    # 否则上面那句「小样本得分低」就失去了参照，阈值也没有校准依据。
    assert index.size > alone.size * 10, "真实语料规模变了，阈值需要重新校准"


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
