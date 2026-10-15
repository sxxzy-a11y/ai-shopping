"""中文检索用的切分。

**不引入分词器**（design.md D1）。中文按字符**二元组**切分：

    主动降噪  →  主动 / 动降 / 降噪

这样不需要理解词边界，「降噪」和「主动降噪」就共享了 `降噪` 这个检索单元。
分词需要词典或模型，都是新增依赖；二元组是纯字符串操作，标准库足够。

拉丁字母与数字按**整词**切分，让 `16GB`、`K87`、`r5` 这类型号能被整体匹配。
"""

from __future__ import annotations

import re

#: 连续的中日韩字符。范围覆盖常用汉字与扩展区，够本项目的语料用。
_CJK_RUN = re.compile(r"[㐀-䶿一-鿿豈-﫿]+")

#: 拉丁字母与数字的连续串。
_LATIN_WORD = re.compile(r"[a-z0-9]+")


def cjk_bigrams(run: str) -> list[str]:
    """把一个连续中文串切成字符二元组。单字串原样返回。"""
    if len(run) <= 1:
        return [run] if run else []
    return [run[i : i + 2] for i in range(len(run) - 1)]


def tokenize(text: str) -> list[str]:
    """把文本切成检索单元。中文出二元组，拉丁数字出整词。

    Args:
        text: 任意文本。空串返回空列表。

    Returns:
        切分结果，**保留重复**——调用方自己按需统计词频。
    """
    if not text:
        return []

    lowered = text.lower()
    tokens: list[str] = list(_LATIN_WORD.findall(lowered))
    for run in _CJK_RUN.findall(lowered):
        tokens.extend(cjk_bigrams(run))
    return tokens


def token_set(text: str) -> set[str]:
    """去重后的检索单元，用于命中判断。"""
    return set(tokenize(text))
