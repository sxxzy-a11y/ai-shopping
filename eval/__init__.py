"""效果评测包。

对外入口集中在这里，方便脚本、测试和页面读取器复用同一套语义。

`runner` 用惰性导入：`python -m eval.runner` 会先执行包的 `__init__`，
如果在包初始化时就导入 runner，会触发 runpy 的「模块已在 sys.modules」警告。
"""

from __future__ import annotations

from .checks import Outcome
from .report import (
    EvaluationReport,
    LoadedReport,
    build_report,
    load_report,
    render_markdown,
    render_terminal,
)

__all__ = [
    "Outcome",
    "EvaluationReport",
    "LoadedReport",
    "build_report",
    "load_cases",
    "load_report",
    "main",
    "render_markdown",
    "render_terminal",
    "run_cases",
    "evaluate",
]

_RUNNER_EXPORTS = frozenset({"run_cases", "load_cases", "main", "evaluate"})


def __getattr__(name: str):
    if name in _RUNNER_EXPORTS:
        from . import runner

        return getattr(runner, name)
    raise AttributeError(f"module 'eval' has no attribute {name!r}")
