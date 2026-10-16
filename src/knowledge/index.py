"""倒排索引与 BM25 打分。

纯标准库实现。BM25 的公式本身只是几十行算术，引一个检索库反而是
更大的负担（多一个依赖，且现场演示时多一处可能出问题的地方）。

打分结果会乘上**文档类型系数**（design.md D2）：通用性问题
（「怎么选」「有什么区别」）应该命中选购指南，而不是某件具体商品。
商品条目是字段罗列，命中二元组天然多，不压一压会霸榜。
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from src import config
from src.demand_parser import detect_category_terms
from src.knowledge.corpus import Document
from src.knowledge.tokenize import tokenize

logger = logging.getLogger("zhigou.knowledge")


@dataclass(frozen=True)
class ScoredDocument:
    """一条打分结果。"""

    document: Document
    score: float


class BM25Index:
    """对一组 `Document` 建索引并支持检索。

    建索引是纯内存操作——语料规模在百条量级，毫秒级完成，
    不需要持久化索引文件，也就没有「索引与语料不同步」的问题。
    """

    def __init__(
        self,
        documents: Sequence[Document],
        *,
        type_weights: dict[str, float] | None = None,
        k1: float | None = None,
        b: float | None = None,
    ) -> None:
        self._documents = list(documents)
        self._type_weights = (
            type_weights if type_weights is not None else config.KNOWLEDGE_TYPE_WEIGHTS
        )
        self._k1 = config.KNOWLEDGE_BM25_K1 if k1 is None else k1
        self._b = config.KNOWLEDGE_BM25_B if b is None else b

        self._term_freq: list[Counter[str]] = []
        self._lengths: list[int] = []
        for document in self._documents:
            tokens = tokenize(document.searchable_text)
            self._term_freq.append(Counter(tokens))
            self._lengths.append(len(tokens))

        #: 语料中出现过的品牌（来自商品级条目）。检索时判断查询是否点名了品牌。
        self._brands = {d.brand for d in self._documents if d.brand}

        self._avg_length = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )
        self._idf = self._compute_idf()

    # -- 建索引 ----------------------------------------------------------

    def _compute_idf(self) -> dict[str, float]:
        """逆文档频率。出现文档越少的词越有区分度。"""
        total = len(self._documents)
        if total == 0:
            return {}

        doc_freq: Counter[str] = Counter()
        for freqs in self._term_freq:
            doc_freq.update(freqs.keys())

        return {
            term: math.log(1 + (total - count + 0.5) / (count + 0.5))
            for term, count in doc_freq.items()
        }

    # -- 检索 ------------------------------------------------------------

    def _weight_for(
        self, document: Document, mentioned: set[str], mentioned_brands: set[str]
    ) -> float:
        weight = self._type_weights.get(document.doc_type, 1.0)
        if document.category and document.category in mentioned:
            weight *= config.KNOWLEDGE_CATEGORY_BOOST
        # 查询点名了文档的品牌，且（没点名品类，或品类也对得上）——
        # 「华为怎么样」「华为笔记本怎么样」都该把华为的商品条目往前排，
        # 但「华为笔记本」不该把华为的手机也顶上来。
        if (
            document.brand
            and document.brand.lower() in mentioned_brands
            and (not mentioned or document.category in mentioned)
        ):
            weight *= config.KNOWLEDGE_BRAND_BOOST
        return weight

    def _score(self, position: int, query_terms: Sequence[str]) -> float:
        freqs = self._term_freq[position]
        length = self._lengths[position]
        if not length or self._avg_length == 0:
            return 0.0

        score = 0.0
        for term in query_terms:
            frequency = freqs.get(term)
            if not frequency:
                continue
            idf = self._idf.get(term, 0.0)
            denominator = frequency + self._k1 * (
                1 - self._b + self._b * length / self._avg_length
            )
            score += idf * frequency * (self._k1 + 1) / denominator
        return score

    def search(self, query: str, *, limit: int = 5) -> list[ScoredDocument]:
        """检索与查询最相关的文档，按得分降序。

        得分为 0 的文档不返回——一个词都没命中，说明毫不相关，
        让调用方拿到它只会污染结果。
        """
        terms = tokenize(query)
        if not terms or not self._documents:
            return []

        # 用户点名的品类——那个品类的资料往前排。
        mentioned = set(detect_category_terms(query))
        # 用户点名的品牌——该品牌的商品条目也往前排（品牌词短，
        # BM25 天然分低，「华为怎么样」不加权会被阈值挡在门外）。
        lowered = query.lower()
        mentioned_brands = {b for b in self._brands if b.lower() in lowered}

        scored: list[ScoredDocument] = []
        for position, document in enumerate(self._documents):
            raw = self._score(position, terms)
            if raw <= 0:
                continue
            scored.append(
                ScoredDocument(
                    document=document,
                    score=raw
                    * self._weight_for(document, mentioned, mentioned_brands),
                )
            )

        scored.sort(key=lambda item: (-item.score, item.document.doc_id))
        return scored[:limit]

    @property
    def size(self) -> int:
        """索引里的文档数，界面用来判断「有没有语料可用」。"""
        return len(self._documents)
