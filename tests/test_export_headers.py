"""导出响应头的编码回归。

背景：`Content-Disposition` 里直接放中文文件名时，Starlette 用 latin-1 编码
头部会抛 `UnicodeEncodeError`，线上导出接口整体 500。这里锁住 RFC 5987 的写法。
"""

from __future__ import annotations

from src import report_service


def test_chinese_filename_header_is_latin1_safe() -> None:
    # 与 `suggested_filename()` 的真实输出形态一致：中文 + 日期 + 后缀。
    filename = "智购参谋报告_20261108_2348.md"
    header = report_service.content_disposition(filename, "md")

    # 关键断言：这行在修复前会抛 UnicodeEncodeError。
    header.encode("latin-1")

    assert 'filename="zhigou-report.md"' in header
    assert "filename*=UTF-8''" in header


def test_encoded_filename_round_trips() -> None:
    from urllib.parse import unquote

    filename = "智购参谋报告_20261108_2348.csv"
    header = report_service.content_disposition(filename, "csv")
    encoded = header.split("filename*=UTF-8''", 1)[1]

    assert unquote(encoded) == filename


def test_ascii_fallback_matches_suffix() -> None:
    assert 'filename="zhigou-report.csv"' in report_service.content_disposition(
        "任意名字.csv", "csv"
    )
