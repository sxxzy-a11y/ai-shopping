"""效果评测的兼容入口。

评测逻辑已经搬到 `eval/` 包：

- `eval/checks.py`：各场景的检查
- `eval/runner.py`：调度、计时与 CLI
- `eval/report.py`：指标汇总与 Markdown / JSON / 终端渲染

保留这个文件只是为了不让 README、文档与已有命令失效：

    python scripts/evaluate.py
    python scripts/evaluate.py --only 知识检索
    python scripts/evaluate.py --json
    python scripts/evaluate.py --write docs/eval-report.md

正式入口也可以直接用：

    python -m eval.runner --output-dir data/evaluation
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.runner import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
