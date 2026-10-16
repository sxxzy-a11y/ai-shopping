"""线性图标系统。

为什么是内联 SVG 而不是 emoji 或图标字体：
- 需求明确禁止把 emoji 当主要图标系统
- 图标字体要多引一个依赖，且字形渲染在不同系统上不一致
- 内联 SVG 可以继承 `currentColor`，跟着文字颜色走，深浅背景都好使

所有图标统一 24×24 视框、1.7 线宽、圆头圆角，保证视觉重量一致。
图标全部由基本图元（线、圆、矩形、折线）拼出，不依赖任何外部资源。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("zhigou.icons")

#: 图标名 → SVG 内部内容（不含外层 <svg>）。
_PATHS: dict[str, str] = {
    # --- 导航 ---
    "home": '<path d="M3.2 10.6 12 3.4l8.8 7.2"/><path d="M5.9 9.6V20h12.2V9.6"/>'
            '<path d="M10 20v-5.2h4V20"/>',
    "analysis": '<path d="M3.5 20.5h17"/><rect x="4.6" y="12.6" width="3.6" height="5.9" rx="1"/>'
                '<rect x="10.2" y="7.6" width="3.6" height="10.9" rx="1"/>'
                '<rect x="15.8" y="10.4" width="3.6" height="8.1" rx="1"/>',
    "compare": '<rect x="3.2" y="4.4" width="7.3" height="15.2" rx="1.6"/>'
               '<rect x="13.5" y="4.4" width="7.3" height="15.2" rx="1.6"/>'
               '<path d="M6.2 9h1.3M6.2 12.4h1.3M16.5 9h1.3M16.5 12.4h1.3"/>',
    "history": '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.3V12l3.2 2"/>',
    "settings": '<path d="M4 7.2h5M13 7.2h7M4 16.8h7M15 16.8h5"/>'
                '<circle cx="10.8" cy="7.2" r="2.1"/><circle cx="13.2" cy="16.8" r="2.1"/>',
    "info": '<circle cx="12" cy="12" r="8.4"/><path d="M12 11v5.4"/>'
            '<circle cx="12" cy="7.9" r="0.95" fill="currentColor" stroke="none"/>',
    "bookmark": '<path d="M6.4 3.8h11.2a1 1 0 0 1 1 1v15.4l-6.6-4.3-6.6 4.3V4.8a1 1 0 0 1 1-1Z"/>',

    # --- 动作 ---
    "search": '<circle cx="10.8" cy="10.8" r="6.4"/><path d="m15.6 15.6 4.4 4.4"/>',
    "filter": '<path d="M3.8 5.6h16.4l-6.4 7.6v5.8l-3.6 2v-7.8Z"/>',
    "download": '<path d="M12 4v10.4"/><path d="m7.8 10.6 4.2 4.2 4.2-4.2"/>'
                '<path d="M4.6 18.4h14.8"/>',
    "refresh": '<path d="M19.4 12a7.4 7.4 0 1 1-2.3-5.35"/>'
               '<path d="M19.2 4.4v4.6h-4.6"/>',
    "arrow-right": '<path d="M4.6 12h14.2"/><path d="m13.4 6.8 5.4 5.2-5.4 5.2"/>',
    "arrow-left": '<path d="M19.4 12H5.2"/><path d="m10.6 6.8-5.4 5.2 5.4 5.2"/>',
    "check": '<path d="m5.2 12.4 4.6 4.6 9-9.6"/>',
    "close": '<path d="m6.6 6.6 10.8 10.8M17.4 6.6 6.6 17.4"/>',
    "alert": '<path d="M12 3.6 21.2 19.6H2.8Z"/><path d="M12 9.4v4.4"/>'
             '<circle cx="12" cy="16.7" r="0.95" fill="currentColor" stroke="none"/>',
    "star": '<path d="m12 3.4 2.72 5.6 6.08.87-4.4 4.3 1.04 6.13L12 17.4l-5.44 2.9L7.6 14.17 3.2 9.87l6.08-.87Z"/>',

    # --- 商品类别 ---
    "laptop": '<rect x="3.6" y="5" width="16.8" height="11.2" rx="1.7"/>'
              '<path d="M2.2 19.2h19.6"/>',
    "phone": '<rect x="7.2" y="2.8" width="9.6" height="18.4" rx="2.2"/>'
             '<path d="M10.6 5.6h2.8"/>'
             '<circle cx="12" cy="18.2" r="0.9" fill="currentColor" stroke="none"/>',
    "headphone": '<path d="M4.4 15.2v-2.4a7.6 7.6 0 0 1 15.2 0v2.4"/>'
                 '<rect x="2.6" y="14.2" width="4" height="6.4" rx="1.6"/>'
                 '<rect x="17.4" y="14.2" width="4" height="6.4" rx="1.6"/>',
    "keyboard": '<rect x="2.4" y="6.6" width="19.2" height="10.8" rx="2"/>'
                '<path d="M6 10h1M9.5 10h1M13 10h1M16.5 10h1.5M7.6 13.4h8.8"/>',
    "grid": '<rect x="3.4" y="3.4" width="7.2" height="7.2" rx="1.6"/>'
            '<rect x="13.4" y="3.4" width="7.2" height="7.2" rx="1.6"/>'
            '<rect x="3.4" y="13.4" width="7.2" height="7.2" rx="1.6"/>'
            '<rect x="13.4" y="13.4" width="7.2" height="7.2" rx="1.6"/>',

    # --- 其他 ---
    "sparkles": '<path d="M11.4 3.2 13 8l4.8 1.6L13 11.2l-1.6 4.8-1.6-4.8L5 9.6 9.8 8Z"/>'
                '<path d="M18 15.2l.85 2.45L21.3 18.5l-2.45.85L18 21.8l-.85-2.45L14.7 18.5l2.45-.85Z"/>',
    "shield": '<path d="M12 3 19.4 6v5.6c0 4.3-3.1 7.6-7.4 9.4-4.3-1.8-7.4-5.1-7.4-9.4V6Z"/>'
              '<path d="m9.2 12 2.1 2.1 3.5-3.7"/>',
    "wallet": '<rect x="3" y="5.6" width="18" height="13.2" rx="2.2"/>'
              '<path d="M3 10.2h18"/>'
              '<circle cx="16.8" cy="14.6" r="1.05" fill="currentColor" stroke="none"/>',
    "tag": '<path d="M4 12.4V5.2a1.2 1.2 0 0 1 1.2-1.2h7.2L20 11.6 12.4 19.2Z"/>'
           '<circle cx="8.5" cy="8.5" r="1.25"/>',
    "target": '<circle cx="12" cy="12" r="8.2"/><circle cx="12" cy="12" r="4.4"/>'
              '<circle cx="12" cy="12" r="0.95" fill="currentColor" stroke="none"/>',
    "scale": '<path d="M12 3.6v16.8"/><path d="M6.4 6.6h11.2"/>'
             '<path d="M6.4 6.6 3.4 13h6Z"/><path d="M17.6 6.6 14.6 13h6Z"/>',
    "clock": '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.3V12l3.2 2"/>',
    "file": '<path d="M13.2 3.4H7a1.8 1.8 0 0 0-1.8 1.8v13.6A1.8 1.8 0 0 0 7 20.6h10a1.8 1.8 0 0 0 1.8-1.8V9.2Z"/>'
            '<path d="M13.2 3.4v5.8H18.8"/>'
            '<path d="M8.8 13h6.4M8.8 16.2h4.2"/>',
}


#: 名字写错时的兜底图标。宁可显示一个通用图标，也不要在版面上留一个空洞——
#: 开发时「view_column 不存在」就真的在统计卡上留了一块空白。
_FALLBACK = "tag"


def icon(name: str, *, size: int = 20, color: str = "currentColor", stroke: float = 1.7) -> str:
    """返回一个内联 SVG 字符串。

    未知图标名不抛异常——退回通用图标并记一条 warning。
    之所以要记日志：`tests/test_app.py` 里有一条测试跑遍所有页面并断言
    「没有任何图标回退」，写错图标名会在测试阶段被拦下，而不是留个空洞上线。
    """
    body = _PATHS.get(name)
    if body is None:
        logger.warning("未知图标名 %r，已回退到 %r", name, _FALLBACK)
        body = _PATHS[_FALLBACK]

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'style="vertical-align:-0.18em;flex-shrink:0">{body}</svg>'
    )


def category_icon(category: str, **kwargs) -> str:
    """按商品类别取图标，未知类别回退到一个通用的盒子图标。"""
    return icon(category if category in _CATEGORY_NAMES else "tag", **kwargs)


#: 有专属图标的商品类别。比 `_PATHS` 小——那里还住着 sparkles、shield 这类
#: 通用图标。键盘与耳机的图标仍留在 `_PATHS` 里（图标库不必和品类同步），
#: 但它们已不是商品类别，所以从这个集合里拿掉了。
_CATEGORY_NAMES = {"laptop", "phone"}


def available_icons() -> list[str]:
    """已定义的图标名，供测试断言使用。"""
    return sorted(_PATHS)
