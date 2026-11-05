"""悬停按钮：magicui「Interactive Hover Button」的 Streamlit 版。

原组件是 React + Tailwind：一枚 `bg-primary` 的圆点从左侧膨胀铺满整颗按钮，
旧文字向右滑走、旧层淡出，新一层「文字 + ArrowRight」滑入。

Streamlit 的按钮里塞不进第二层文字（标签由服务端渲染，改不了 DOM），
所以这里保留最容易感知的两拍——**圆点膨胀成金色填充 + 箭头从右侧滑入**，
文字在填充上换成深色、向左让出箭头的宽度，hover 时仍然读得出来。

样式在 `src/ui/backend_theme.py` 的「悬停按钮」一节，靠 `st-key-zg-hover-*`
这个类名命中：**只有 key 以这个前缀开头的按钮才会开启动效**，不影响其余控件。

用法：

    from src.ui.hover_button import hover_button

    if hover_button("开始分析", key="home_cta"):
        ...
"""

from __future__ import annotations

from typing import Literal

import streamlit as st

#: key 前缀。CSS 用 `[class*="st-key-zg-hover-"]` 命中，改这里要同步改样式。
PREFIX = "zg-hover-"

#: 侧栏导航专用的前缀。导航是整行左对齐 + 图标，和主区的药丸 CTA 不是同一种
#: 控件，所以单独一个类名，样式也单独一节（见 backend_theme 的「侧栏导航」）。
NAV_PREFIX = "zg-hover-nav-"

#: 按钮宽度：铺满容器 / 跟随内容 / 固定像素
Width = Literal["stretch", "content"] | int


def hover_key(key: str) -> str:
    """把业务 key 统一成带前缀的控件 key。

    幂等：已经是前缀的直接返回，避免调用方手写前缀时叠成
    `zg-hover-zg-hover-xxx`（样式仍然生效，但 key 会变得难认）。
    """
    key = str(key).strip()
    if not key:
        raise ValueError("hover_button 需要一个非空 key")
    return key if key.startswith(PREFIX) else f"{PREFIX}{key}"


def hover_button(
    label: str,
    *,
    key: str,
    variant: Literal["primary", "secondary"] = "primary",
    width: Width = "content",
    disabled: bool = False,
    help: str | None = None,
    icon: str | None = None,
) -> bool:
    """渲染一颗带悬停动效的按钮，返回是否被点击。

    参数与 `st.button` 一一对应，只多了一层样式约定：

    - `variant="primary"`：主操作，金币色圆点、hover 铺满后深色文字；
    - `variant="secondary"`：次操作，同样的动效，静息态更轻；
    - `width`：默认 `"content"`，按钮贴合文字宽度——**别用 `"stretch"`**，
      列一窄就会把中文标签挤掉（overflow 裁切），只有在确定的宽容器里才拉伸；
    - `key`：**必填**。动效靠 key 派生出的类名命中，没有 key 就没有样式。
    """
    return st.button(
        label,
        key=hover_key(key),
        type="primary" if variant == "primary" else "secondary",
        width=width,
        disabled=disabled,
        help=help,
        icon=icon,
    )


def nav_key(key: str) -> str:
    """侧栏导航的 key：加 `zg-hover-nav-` 前缀，幂等。"""
    key = str(key).strip()
    if not key:
        raise ValueError("nav_button 需要一个非空 key")
    return key if key.startswith(NAV_PREFIX) else f"{NAV_PREFIX}{key}"


def nav_button(
    label: str,
    *,
    key: str,
    icon: str | None = None,
    active: bool = False,
    width: Width = "stretch",
) -> bool:
    """侧栏导航行，带同一套悬停动效，但按导航的形态适配。

    和 `hover_button` 的区别：

    - 整行铺满、左对齐、保留 Material 图标；
    - 圆点更小（6px），hover 铺开的是**浅金**，深金留给「当前页」；
    - 当前页（`active=True`）走 `type="primary"`，悬停动效关掉，避免和选中态打架。
    """
    return st.button(
        label,
        key=nav_key(key),
        icon=icon,
        type="primary" if active else "secondary",
        width=width,
    )
