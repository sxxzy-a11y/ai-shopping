"""悬停按钮的约定测试。

样式是 CSS，跑不了视觉断言，所以这里守三条**结构**约定：

1. `hover_button()` 一定给 key 加上 `zg-hover-` 前缀，且幂等；
2. 样式表里确实存在命中该前缀的规则，且圆点 / 箭头 / hover 三拍齐全；
3. 只有这个前缀的按钮被改写——别把普通按钮的常规样式带跑。

图形对不对要人看，但「动画根本没挂上」这类错误测能拦住。
"""

from __future__ import annotations

import pytest

from src.ui import backend_theme
from src.ui.hover_button import NAV_PREFIX, PREFIX, hover_key, nav_key

CSS = backend_theme._STYLES


class TestHoverKey:
    def test_adds_prefix(self):
        assert hover_key("home_cta") == f"{PREFIX}home_cta"

    def test_idempotent(self):
        once = hover_key("home_cta")
        assert hover_key(once) == once

    def test_strips_whitespace(self):
        assert hover_key("  home_cta  ") == f"{PREFIX}home_cta"

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_empty_key_rejected(self, bad):
        with pytest.raises(ValueError):
            hover_key(bad)

    def test_nav_prefix_separate(self):
        # 导航和主区 CTA 用两套前缀：前者整行左对齐，后者是药丸。
        # 注意 NAV_PREFIX 以 PREFIX 开头，样式靠作用域（stMain / stSidebar）区分，
        # 不是靠前缀互斥。
        assert nav_key("nav_首页").startswith(NAV_PREFIX)
        assert NAV_PREFIX != PREFIX

    def test_nav_key_idempotent(self):
        once = nav_key("nav_首页")
        assert nav_key(once) == once

    def test_nav_empty_key_rejected(self):
        with pytest.raises(ValueError):
            nav_key(" ")


class TestHoverStyles:
    @pytest.mark.parametrize(
        "needle",
        [
            "st-key-zg-hover-",
            "button::before",
            "button::after",
            "button:hover::before",
            "button:hover::after",
        ],
    )
    def test_rule_present(self, needle):
        assert needle in CSS

    def test_dot_expands_on_hover(self):
        # 圆点靠放大铺满按钮，倍率必须真的放大，不能是 1
        assert "scale(160)" in CSS

    def test_arrow_uses_lucide_mask(self):
        # 箭头是 Lucide ArrowRight 的 mask，颜色跟随 currentColor
        assert "M5 12h14" in CSS
        assert "background-color: currentColor" in CSS

    def test_prefix_only_scope(self):
        # 前缀选择器命中 st-key-*，不直接改 .stButton 的全局样式
        assert '[class*="st-key-zg-hover-"] .stButton > button' in CSS

    def test_touch_fallback(self):
        # 触屏没有 hover，必须有 @media (hover: none) 的静态填充
        assert "@media (hover: none)" in CSS
