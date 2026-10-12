"""界面层的回归测试。

用 Streamlit 自带的 `AppTest` 无头运行整个应用。这个文件存在的理由很具体：
开发过程中连续踩了三次同一个坑——**在控件实例化之后修改它绑定的
session_state 键**（侧栏导航、清空条件、填入推荐）。这类错误在纯业务层的
单元测试里完全看不见，只有真跑一遍页面才会暴露。

不联网、不需要密钥。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_FILE = str(PROJECT_ROOT / "app.py")

#: app.py 兜底处理未预期异常时的文案。出现它就说明有东西炸了。
FALLBACK_TEXT = "操作未能完成，请稍后重试"


def _run(timeout: float = 60) -> AppTest:
    at = AppTest.from_file(APP_FILE, default_timeout=timeout)
    at.run()
    return at


def _button(at: AppTest, label: str):
    """按文案取按钮。AppTest 没有按 label 查询的接口，自己找。"""
    for button in at.button:
        if button.label == label:
            return button
    raise AssertionError(f"找不到按钮「{label}」，现有：{[b.label for b in at.button]}")


def _all_text(at: AppTest) -> str:
    """把页面上所有可见文本拼起来，用于关键词断言。

    会先剥掉注入的 `<style>` 块——里面全是 CSS，混进来会造成误判。
    """
    chunks: list[str] = []

    for attr in ("markdown", "caption", "title", "header", "subheader", "text", "info", "warning"):
        for element in getattr(at, attr, []):
            chunks.append(str(getattr(element, "value", "")))

    for element in at.selectbox:
        chunks.append(str(element.label))

    combined = "\n".join(chunks)
    return re.sub(r"<style>.*?</style>", "", combined, flags=re.DOTALL)


def _state(at: AppTest, key: str, default=None):
    """AppTest 的 session_state 不支持 `.get()`，这里补一个。"""
    try:
        return at.session_state[key]
    except (KeyError, AttributeError):
        return default


def _assert_clean(at: AppTest) -> None:
    """没有未捕获异常，也没有兜底错误提示。"""
    assert not at.exception, f"页面抛出异常：{[e.value for e in at.exception]}"
    body = _all_text(at)
    assert "Traceback" not in body, "页面上出现了 Traceback"
    assert FALLBACK_TEXT not in body, "出现了兜底错误提示，说明有异常被捕获"
    assert "cannot be modified after the widget" not in body


# --------------------------------------------------------------------------
# 基本可运行性
# --------------------------------------------------------------------------


def test_app_starts_without_exception():
    at = _run()
    _assert_clean(at)


def test_app_uses_the_expected_page_layout():
    at = _run()
    assert at.radio[0].options == ["首页", "智能分析", "商品比较", "历史记录", "项目说明"]


@pytest.mark.parametrize(
    "page", ["首页", "智能分析", "商品比较", "历史记录", "项目说明"]
)
def test_every_page_renders_without_exception(page):
    at = _run()
    at.radio[0].set_value(page).run()
    _assert_clean(at)


# --------------------------------------------------------------------------
# 快速开始 → 分析 → 比较（这条链路踩坑最多）
# --------------------------------------------------------------------------


def test_quick_start_prefills_the_analysis_page():
    at = _run()
    _button(at, "用这个示例").click().run()
    _assert_clean(at)

    assert at.radio[0].value == "智能分析"
    assert "预算 3000 元" in at.text_area[0].value


def test_quick_start_then_analysis_produces_recommendations():
    at = _run()
    _button(at, "用这个示例").click().run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "需求摘要" in body
    assert "预算内推荐" in body

    result = at.session_state["zg_result"]
    assert result.has_results
    assert result.within_budget


def test_filling_comparison_from_analysis_does_not_blow_up():
    """这条曾经真的炸过：控件创建之后写它的 session_state 键。"""
    at = _run()
    _button(at, "用这个示例").click().run()
    _button(at, "开始分析").click().run()

    at.radio[0].set_value("商品比较").run()
    _assert_clean(at)

    _button(at, "用上次分析的推荐").click().run()
    _assert_clean(at)

    picked = at.session_state["zg_compare_pick"]
    assert len(picked) >= 3, f"填充后应至少选中 3 件，实际 {len(picked)}"
    assert "横向比较" in _all_text(at)


def test_clearing_conditions_does_not_blow_up():
    """这条也炸过：清空按钮在输入控件创建之后动它们的键。"""
    at = _run()
    _button(at, "用这个示例").click().run()
    _button(at, "开始分析").click().run()
    assert at.session_state["zg_result"] is not None

    _button(at, "清空条件").click().run()
    _assert_clean(at)

    assert at.text_area[0].value == ""
    assert _state(at, "zg_result") is None


# --------------------------------------------------------------------------
# 异常路径
# --------------------------------------------------------------------------


def test_analysis_without_any_input_shows_chinese_hint():
    at = _run()
    at.radio[0].set_value("智能分析").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert "请先描述你的购买需求" in _all_text(at)


def test_invalid_budget_shows_a_chinese_error():
    at = _run()
    at.radio[0].set_value("智能分析").run()
    at.text_input[0].set_value("三千块").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "格式不正确" in body
    assert _state(at, "zg_result") is None


def test_unsupported_category_is_rejected_explicitly():
    at = _run()
    at.radio[0].set_value("智能分析").run()
    at.text_area[0].set_value("想买个平板，预算 2000").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "还不支持" in body
    assert "平板" in body


def test_missing_key_field_triggers_a_targeted_follow_up():
    at = _run()
    at.radio[0].set_value("智能分析").run()
    at.text_area[0].set_value("想买台笔记本").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "还需要一点信息" in body
    assert "预算" in body
    assert _state(at, "zg_result") is None


def test_no_match_gives_relaxation_advice():
    at = _run()
    at.radio[0].set_value("智能分析").run()
    at.text_area[0].set_value("预算 500 元买笔记本电脑").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    result = at.session_state["zg_result"]
    assert result.relaxations
    assert "放宽条件的建议" in _all_text(at)


def test_comparison_with_too_few_products_shows_hint():
    at = _run()
    at.radio[0].set_value("商品比较").run()
    _assert_clean(at)
    assert "无法进行横向比较" in _all_text(at)


# --------------------------------------------------------------------------
# 数据与提示
# --------------------------------------------------------------------------


def test_demo_data_disclaimer_is_visible_on_home():
    at = _run()
    body = _all_text(at)
    assert "演示数据" in body


#: 这些词如果出现在**肯定**语境里，就等于把系统评分冒充成了真实市场数据。
_MARKET_CLAIM_TERMS = ("好评率", "用户评分", "销量排名", "口碑排行", "市场口碑")

#: 否定标记。词出现在这些字眼附近才算「在声明这不是市场数据」。
_NEGATIONS = ("不是", "并非", "非", "不", "无", "而非", "没有")

#: 按分句切分。中文标点 + HTML 块级标签都算边界。
_CLAUSE_SPLIT = re.compile(r"[。！？；;\n]|</li>|<br\s*/?>|</div>|</p>|<li>|<div[^>]*>")


def _assert_only_negated(body: str, terms: tuple[str, ...], where: str) -> None:
    """断言这些词只出现在否定语境中。

    简单地把词拉黑是错的——免责声明里写「它不是用户评分」恰恰是**正确**的。
    真正要禁的是肯定式表述，比如卡片上直接印一个「用户评分 4.8」。

    判定粒度是**分句**：否定词可以出现在同一个小句的任意位置，
    例如「不伪造用户评价、销量或市场口碑」里的「不」离最后一个词很远。
    """
    for segment in _CLAUSE_SPLIT.split(body):
        if not segment.strip():
            continue
        for term in terms:
            if term not in segment:
                continue
            assert any(neg in segment for neg in _NEGATIONS), (
                f"{where} 页出现肯定语境的「{term}」，所在分句："
                f"{segment.strip()[:120]}"
            )


def test_score_is_never_presented_as_market_reputation():
    """系统评分只能以「需求匹配度」的口径出现，不能冒充市场数据。"""
    at = _run()
    for page in ("首页", "智能分析", "商品比较", "历史记录", "项目说明"):
        at.radio[0].set_value(page).run()
        _assert_clean(at)
        _assert_only_negated(_all_text(at), _MARKET_CLAIM_TERMS, page)


def test_score_display_name_is_shown_with_results():
    at = _run()
    _button(at, "用这个示例").click().run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)
    assert config.SCORE_DISPLAY_NAME in _all_text(at)
