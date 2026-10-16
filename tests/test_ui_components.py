"""商品缩略图的渲染：有图显示图片，没图或图挂了回落类别图标。

缩略图是**演示现场最容易出丑的一处**：商品图是外链，随时可能失效，
而没有回落的话用户看到的是一张破图——比不显示图片难看得多。
所以这里的断言不是「能显示图片」，而是「图片挂掉之后还剩什么」。
"""

from __future__ import annotations

from src.data_loader import Product
from src.ui.components import _thumb


def _product(**overrides) -> Product:
    base = {
        "id": "LP001",
        "name": "测试笔记本",
        "category": "laptop",
        "brand": "联想",
    }
    base.update(overrides)
    return Product(**base)


def test_without_image_shows_category_icon_only():
    html = _thumb(_product())

    assert "<img" not in html
    assert "<svg" in html, "没有图片时必须给类别图标"
    assert 'class="zg-thumb"' in html


def test_with_image_renders_img():
    html = _thumb(_product(image_url="https://example.com/a.jpg"))

    assert 'src="https://example.com/a.jpg"' in html


def test_category_icon_stays_underneath_the_image():
    """有图时图标也必须在。

    图标是图片加载失败后的退路，只给 `onerror` 而不垫图标，
    等于把「破图」换成了「一个空方块」——问题只是换了个样子。
    """
    html = _thumb(_product(image_url="https://example.com/a.jpg"))

    assert "<svg" in html, "有图片时也要垫着类别图标"


def test_image_hides_itself_when_it_fails_to_load():
    html = _thumb(_product(image_url="https://example.com/a.jpg"))

    assert "onerror" in html
    assert "display" in html and "none" in html


def test_image_url_is_html_escaped():
    """图片地址来自外部数据，直接拼进 HTML 就是把注入口开着。"""
    html = _thumb(_product(image_url='"><script>alert(1)</script>'))

    assert "<script>" not in html


def test_large_variant_uses_the_large_class():
    assert "is-lg" in _thumb(_product(), large=True)
    assert "is-lg" not in _thumb(_product())


def test_blank_image_url_falls_back_to_icon():
    """空串与 None 一样都算「没有图片」，不能渲染出一个 src="" 的 img。"""
    assert "<img" not in _thumb(_product(image_url=""))
    assert "<img" not in _thumb(_product(image_url="   "))
