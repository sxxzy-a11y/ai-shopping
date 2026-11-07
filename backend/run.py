"""开发/本地启动入口：从项目根目录执行 `python backend/run.py`。

直接传 app 对象给 uvicorn，避免字符串导入在脚本启动时找不到 `backend` 包
（`python backend/run.py` 的 sys.path[0] 是 backend/ 而不是项目根）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from backend.app.main import app  # noqa: E402


def main() -> None:
    uvicorn.run(
        app,
        host=os.getenv("ZHIGOU_API_HOST", "127.0.0.1"),
        port=int(os.getenv("ZHIGOU_API_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
