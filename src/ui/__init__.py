"""界面层。

本包是唯一依赖 Streamlit 的地方。业务逻辑全部在 `src/` 下的模块里，
界面只负责编排、渲染与错误提示——`app.py` 与 `src/ui/pages/*` 中
不应出现评分、筛选、比较等业务规则。
"""

from __future__ import annotations

__all__: list[str] = []
