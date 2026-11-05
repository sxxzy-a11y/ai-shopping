"""载入态的约定测试。

动效本身靠肉眼，这里守的是**结构约定**：

1. 三球 + 三影子的结构数量对得上 CSS 里的 nth-child；
2. 标签文本必须转义（用户输入会进到这段 HTML 里）；
3. 登录过场和页面载入共用同一份 CSS，不是各写一份；
4. 主流程用的是自家载入层，不再回退到 st.spinner。
"""

from __future__ import annotations

import pathlib

from src.ui import loader
from src.ui.pages import login

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_markup_has_three_balls_and_shadows():
    markup = loader.loader_markup()
    assert markup.count("zg-loader-dot") == 3
    assert markup.count("zg-loader-shadow") == 3


def test_overlay_escapes_label():
    html = loader.overlay_html("<b>慢</b>")
    assert "&lt;b&gt;慢&lt;/b&gt;" in html
    assert "zg-loading-overlay" in html


def test_css_keyframes_present():
    css = loader.LOADER_CSS + loader.OVERLAY_CSS
    for name in ("zgLoaderBounce", "zgLoaderShadow", "zgLoadingFade"):
        assert name in css


def test_login_transition_reuses_shared_css():
    # 共用一份，不是复制一份：整段 LOADER_CSS 必须原样出现在过场里
    assert loader.LOADER_CSS in login._LOGIN_TRANSITION
    assert login._LOGIN_TRANSITION.count('class="zg-loader-dot"') == 3


def test_login_veil_reuses_shared_css():
    # 首屏载入幕布同样是共用那一份，不是另写一套
    assert loader.LOADER_CSS in login._LOGIN_VEIL
    assert login._LOGIN_VEIL.count('class="zg-loader-dot"') == 3


def test_analysis_uses_loading_overlay():
    source = (ROOT / "src/ui/pages/analysis.py").read_text(encoding="utf-8")
    assert "st.spinner(" not in source
    assert "with loading(" in source


def test_knowledge_uses_loading_overlay():
    source = (ROOT / "src/ui/pages/knowledge.py").read_text(encoding="utf-8")
    assert "with loading(" in source
