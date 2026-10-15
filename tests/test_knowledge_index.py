"""BM25 索引与打分的测试。

重点在三条「机制真的生效」的证据：

- 命中越多分越高（否则排序没有依据）
- 长文档被归一化（否则一篇长文靠字数就能霸榜）
- 类型系数确实改变排序（否则「怎么选」会被答成某款具体商品）
"""

from __future__ import annotations

import pytest

from src import config
from src.knowledge.corpus import (
    TYPE_CATEGORY,
    TYPE_PRODUCT,
    TYPE_SERVICE,
    Document,
)
from src.knowledge.index import BM25Index


def _doc(doc_id: str, body: str, *, doc_type: str = TYPE_CATEGORY, category: str = ""):
    return Document(
        doc_id=doc_id,
        title=doc_id,
        body=body,
        doc_type=doc_type,
        source="测试",
        updated_at="2026-01-01",
        category=category,
    )


# --------------------------------------------------------------------------
# 基本检索
# --------------------------------------------------------------------------


def test_empty_index_returns_nothing():
    assert BM25Index([]).search("任何问题") == []


def test_empty_query_returns_nothing():
    index = BM25Index([_doc("a", "降噪耳机的选购要点")])
    assert index.search("") == []
    assert index.search("   ") == []


def test_unrelated_query_is_not_returned():
    """一个词都没命中的文档不进结果——它和问题毫不相关。"""
    index = BM25Index([_doc("a", "冰箱的能效等级怎么看")])
    assert index.search("耳机降噪") == []


def test_size_reports_document_count():
    assert BM25Index([_doc("a", "x"), _doc("b", "y")]).size == 2


# --------------------------------------------------------------------------
# 打分单调性（任务 2.4）
# --------------------------------------------------------------------------


def test_more_hits_score_higher():
    """同一查询下，命中词更多的文档得分更高。"""
    index = BM25Index(
        [
            _doc("few", "降噪"),
            _doc("many", "降噪 降噪 通勤 通勤 佩戴"),
        ]
    )
    hits = {h.document.doc_id: h.score for h in index.search("降噪 通勤 佩戴")}
    assert hits["many"] > hits["few"]


def test_longer_document_is_normalised():
    """一篇把关键词埋在大量无关文字里的长文，不该压过短小精悍的那篇。

    这就是 BM25 里 `b` 参数的作用——不加长度归一化，长文档靠字数堆命中，
    结果会全是长篇。
    """
    short = _doc("short", "主动降噪适合通勤")
    long = _doc("long", "主动降噪适合通勤。" + "本段与问题无关。" * 80)

    hits = {h.document.doc_id: h.score for h in BM25Index([short, long]).search("主动降噪")}
    assert hits["short"] > hits["long"], "长文档没有被归一化，长度成了得分来源"


def test_result_order_is_descending():
    index = BM25Index(
        [
            _doc("low", "耳机"),
            _doc("high", "耳机 耳机 降噪 降噪 通勤"),
        ]
    )
    scores = [h.score for h in index.search("降噪 耳机 通勤")]
    assert scores == sorted(scores, reverse=True)


def test_limit_caps_the_results():
    docs = [_doc(f"d{i}", "降噪耳机") for i in range(10)]
    assert len(BM25Index(docs).search("降噪耳机", limit=3)) == 3


def test_ties_are_broken_deterministically():
    """同分时按 doc_id 排——排序必须稳定，否则每次刷新顺序都在跳。"""
    docs = [_doc("b", "降噪耳机"), _doc("a", "降噪耳机")]
    ids = [h.document.doc_id for h in BM25Index(docs).search("降噪耳机")]
    assert ids == ["a", "b"]


# --------------------------------------------------------------------------
# 文档类型加权（任务 2.6）
# --------------------------------------------------------------------------


def test_type_weight_lowers_product_documents():
    """同样内容下，商品条目的得分被压低。"""
    body = "通勤耳机的降噪与佩戴"
    index = BM25Index(
        [
            _doc("cat", body, doc_type=TYPE_CATEGORY),
            _doc("prod", body, doc_type=TYPE_PRODUCT),
        ]
    )
    hits = {h.document.doc_id: h.score for h in index.search("通勤耳机降噪佩戴")}
    assert hits["cat"] > hits["prod"]
    assert hits["prod"] == pytest.approx(
        hits["cat"] * config.KNOWLEDGE_TYPE_WEIGHTS[TYPE_PRODUCT]
    )


def test_type_weight_changes_the_ranking():
    """类型系数不只是缩放——它要能**改变排序**才算起作用。

    构造一个商品条目，它的字面命中略多于选购指南；没有系数时商品排第一，
    加上系数后指南反超。这正是 design.md D2 要解决的问题。
    """
    guide = _doc("guide", "通勤耳机怎么选：看降噪和佩戴", doc_type=TYPE_CATEGORY)
    product = _doc(
        "product",
        "通勤耳机 通勤耳机 降噪降噪 佩戴佩戴",
        doc_type=TYPE_PRODUCT,
    )

    # 先确认：不加系数时商品确实靠命中数领先
    raw = BM25Index([guide, product], type_weights={})
    assert raw.search("通勤耳机 降噪 佩戴")[0].document.doc_id == "product"

    # 加上真实系数后，选购指南反超
    weighted = BM25Index([guide, product])
    assert weighted.search("通勤耳机 降噪 佩戴")[0].document.doc_id == "guide"


def test_service_documents_are_not_discounted():
    """服务级与品类级同为 1.0——术语问题该命中 FAQ。"""
    assert config.KNOWLEDGE_TYPE_WEIGHTS[TYPE_SERVICE] == 1.0
    assert config.KNOWLEDGE_TYPE_WEIGHTS[TYPE_CATEGORY] == 1.0


# --------------------------------------------------------------------------
# 品类加权
# --------------------------------------------------------------------------


def test_named_category_is_boosted():
    """用户点名了品类，那个品类的资料往前排。

    这条针对的是语料之间的**无意字面碰撞**：键盘指南里提到「在笔记本和平板
    之间切换」，于是问「笔记本」时它会被词频顶上去。
    """
    laptop = _doc("laptop", "笔记本怎么选：看重量和续航", category="laptop")
    keyboard = _doc(
        "keyboard", "键盘怎么选：在笔记本和平板之间切换", category="keyboard"
    )

    plain = BM25Index([laptop, keyboard], type_weights={})
    boosted = BM25Index([laptop, keyboard], type_weights={})

    # 查询里点名了「笔记本」，laptop 品类的文档应当登顶
    assert boosted.search("笔记本 怎么选")[0].document.doc_id == "laptop"
    # 而没点名品类时不应受影响——两边的相对顺序由词频决定
    assert plain.search("怎么选")[0].document.doc_id in {"laptop", "keyboard"}


def test_boost_only_applies_to_the_named_category():
    """没被点名的品类不享受加权。

    「手机怎么选」和「笔记本怎么选」共享 `怎么` / `么选` 两个二元组，
    所以它**会**被检索到——但排名应在被点名的品类之后。
    """
    other = _doc("phone", "手机怎么选", category="phone")
    target = _doc("laptop", "笔记本怎么选", category="laptop")
    hits = BM25Index([other, target]).search("笔记本怎么选")
    ids = [h.document.doc_id for h in hits]

    assert ids[0] == "laptop", "被点名的品类没有被加权"
    scores = {h.document.doc_id: h.score for h in hits}
    assert scores["laptop"] > scores["phone"]


def test_disjoint_document_is_absent():
    """一个字面重合都没有的文档不进结果。"""
    doc = _doc("fridge", "冰箱能效", category="appliance")
    assert BM25Index([doc]).search("笔记本怎么选") == []


def test_index_returns_weak_matches_but_marks_them_low():
    """索引层只要命中就给分——**「检索不到」是阈值层的职责**。

    这条守住分层：不能把「过滤弱相关」塞进索引里，否则阈值就无从调整，
    也没法用固定查询集做回归。这里确认弱命中确实存在且分数明显偏低。
    """
    doc = _doc("fridge", "冰箱的能效等级怎么看", category="appliance")
    hits = BM25Index([doc]).search("笔记本怎么选")

    assert len(hits) == 1, "共享「怎么」两个字面单元，索引层应当返回"
    assert hits[0].score < config.KNOWLEDGE_MIN_SCORE, "弱命中却高于阈值，阈值形同虚设"
