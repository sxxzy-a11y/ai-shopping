"""中文切分的测试。

切分是整套检索的地基：切错了，后面的 BM25 再准也没用。
重点在两件事——中文出二元组（不引分词器也能匹配），
以及拉丁字母数字出整词（型号码不被切碎）。
"""

from __future__ import annotations

import pytest

from src.knowledge.tokenize import cjk_bigrams, token_set, tokenize


# --------------------------------------------------------------------------
# 中文二元组
# --------------------------------------------------------------------------


def test_chinese_becomes_overlapping_bigrams():
    """「主动降噪」切成 主动/动降/降噪——重叠是刻意的。"""
    assert cjk_bigrams("主动降噪") == ["主动", "动降", "降噪"]


def test_single_character_becomes_itself():
    """单字没有相邻字可组，原样保留。"""
    assert cjk_bigrams("好") == ["好"]


def test_empty_string_yields_nothing():
    assert cjk_bigrams("") == []
    assert tokenize("") == []


def test_shared_bigram_links_related_phrases():
    """「降噪」与「主动降噪」共享 `降噪` —— 这正是不要分词器的理由。"""
    short = token_set("降噪")
    long = token_set("主动降噪")
    assert short <= long


# --------------------------------------------------------------------------
# 拉丁字母与数字
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("16GB", ["16gb"]),
        ("K87", ["k87"]),
        ("R5-7530U", ["r5", "7530u"]),
        ("ANC", ["anc"]),
    ],
)
def test_latin_and_digits_stay_whole(text: str, expected: list[str]):
    """型号码不能被切碎——`16gb` 切成分片就再也匹配不上了。"""
    assert tokenize(text) == expected


def test_case_is_folded():
    assert token_set("ANC anc Anc") == {"anc"}


def test_hyphen_separates_but_does_not_vanish_the_parts():
    """连字符当作分隔符，两侧各自成词。"""
    assert tokenize("R5-7530U") == ["r5", "7530u"]


# --------------------------------------------------------------------------
# 中英混排
# --------------------------------------------------------------------------


def test_mixed_text_yields_both_kinds():
    tokens = tokenize("16GB 内存")
    assert "16gb" in tokens
    assert "内存" in tokens


def test_chinese_and_latin_do_not_bleed_into_each_other():
    """紧挨着写也不能跨边界组词：`16GB内存` 里不该出现 `b内`。

    拉丁部分是**整词** `16gb`，不是切出来的 `gb`——这是刻意的，
    型号码要能整体匹配。
    """
    tokens = tokenize("16GB内存")
    assert "b内" not in tokens
    assert "16gb" in tokens
    assert "内存" in tokens


def test_punctuation_does_not_produce_tokens():
    tokens = tokenize("，。！？——  · 「」")
    assert tokens == []


def test_punctuation_splits_chinese_runs():
    """标点两侧是两段独立的中文，不该跨界组二元组。"""
    tokens = tokenize("通勤，降噪")
    assert "勤降" not in tokens
    assert "通勤" in tokens
    assert "降噪" in tokens


# --------------------------------------------------------------------------
# 其他
# --------------------------------------------------------------------------


def test_tokenize_keeps_duplicates_for_frequency():
    """保留重复——BM25 需要词频，调用方自己按需去重。"""
    tokens = tokenize("降噪 降噪")
    assert tokens.count("降噪") == 2


def test_token_set_deduplicates():
    assert token_set("降噪 降噪") == {"降噪"}


def test_longer_text_is_handled():
    """一段真实语料能切出足够多的单元，且不抛异常。

    标点把整句分成两段中文：9 字 → 8 个二元组，12 字 → 11 个，合计 19。
    """
    text = "主动降噪对低频有效，比如地铁轰鸣和空调嗡嗡声。"
    tokens = tokenize(text)
    assert len(tokens) == 19
    assert "降噪" in tokens
    assert "轰鸣" in tokens
