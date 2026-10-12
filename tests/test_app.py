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
from src.ui import icons, state, theme

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


def _raw_text(at: AppTest) -> str:
    """不剥 style 的版本，用于断言注入的样式确实包含某条规则。"""
    return "\n".join(str(getattr(el, "value", "")) for el in at.markdown)


def _go_to_page(at: AppTest, page: str) -> None:
    """导航已经从 st.radio 改成 st.button，用点击代替 set_value。"""
    _button(at, page).click().run()


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
    labels = [b.label for b in at.button]
    for expected in ("首页", "智能分析", "商品比较", "历史记录", "个人设置", "项目说明"):
        assert expected in labels, f"侧栏缺少导航项「{expected}」"


def test_sidebar_is_dark():
    """守住那处 data-testid 依赖。

    深色侧栏是唯一一处用到 Streamlit 非公开结构的地方
    （`[data-testid="stSidebar"]`）。升级 Streamlit 把它改坏了，
    这条测试会失败，而不是悄悄退化成浅色。
    """
    at = _run()
    css = _raw_text(at)
    assert 'data-testid="stSidebar"' in css, "侧栏样式选择器不见了"
    assert theme.NAVY_900 in css, "侧栏深色令牌没有注入"


@pytest.mark.parametrize(
    "page", ["首页", "智能分析", "商品比较", "历史记录", "项目说明"]
)
def test_every_page_renders_without_exception(page):
    at = _run()
    _go_to_page(at, page)
    _assert_clean(at)


# --------------------------------------------------------------------------
# 快速开始 → 分析 → 比较（这条链路踩坑最多）
# --------------------------------------------------------------------------


def test_quick_start_prefills_the_analysis_page():
    at = _run()
    at.button(key="quick_大学生买笔记本").click().run()
    _assert_clean(at)

    assert _state(at, "zg_current_page") == "智能分析"
    assert "预算 3000 元" in at.text_area[0].value


def test_quick_start_then_analysis_produces_recommendations():
    at = _run()
    at.button(key="quick_大学生买笔记本").click().run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "需求摘要" in body
    assert "为你推荐" in body

    result = at.session_state["zg_result"]
    assert result.has_results
    assert result.within_budget


def test_filling_comparison_from_analysis_does_not_blow_up():
    """这条曾经真的炸过：控件创建之后写它的 session_state 键。"""
    at = _run()
    at.button(key="quick_大学生买笔记本").click().run()
    _button(at, "开始分析").click().run()

    _go_to_page(at, "商品比较")
    _assert_clean(at)

    _button(at, "用上次分析的推荐").click().run()
    _assert_clean(at)

    picked = at.session_state["zg_compare_pick"]
    assert len(picked) >= 3, f"填充后应至少选中 3 件，实际 {len(picked)}"
    assert "横向比较" in _all_text(at)


def test_clearing_conditions_does_not_blow_up():
    """这条也炸过：清空按钮在输入控件创建之后动它们的键。"""
    at = _run()
    at.button(key="quick_大学生买笔记本").click().run()
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
    _go_to_page(at, "智能分析")
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert "请先描述你的购买需求" in _all_text(at)


def test_invalid_budget_shows_a_chinese_error():
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_input[0].set_value("三千块").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "格式不正确" in body
    assert _state(at, "zg_result") is None


def test_unsupported_category_is_rejected_explicitly():
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("想买个平板，预算 2000").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "还不支持" in body
    assert "平板" in body


def test_missing_key_field_triggers_a_targeted_follow_up():
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("想买台笔记本").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "还需要一点信息" in body
    assert "预算" in body
    assert _state(at, "zg_result") is None


def test_no_match_gives_relaxation_advice():
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("预算 500 元买笔记本电脑").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    result = at.session_state["zg_result"]
    assert result.relaxations
    assert "放宽条件的建议" in _all_text(at)


def test_comparison_with_too_few_products_shows_hint():
    at = _run()
    _go_to_page(at, "商品比较")
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
        _go_to_page(at, page)
        _assert_clean(at)
        _assert_only_negated(_all_text(at), _MARKET_CLAIM_TERMS, page)


def test_score_display_name_is_shown_with_results():
    at = _run()
    at.button(key="quick_大学生买笔记本").click().run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)
    assert config.SCORE_DISPLAY_NAME in _all_text(at)


# --------------------------------------------------------------------------
# 图标
# --------------------------------------------------------------------------


def test_every_icon_name_is_defined():
    """图标表里不能有返回空内容的条目。"""
    for name in icons.available_icons():
        assert icons.icon(name), f"图标「{name}」渲染为空"


def test_unknown_icon_falls_back_instead_of_leaving_a_hole():
    rendered = icons.icon("definitely_not_an_icon")
    assert rendered.startswith("<svg"), "未知图标名应回退到通用图标，而不是返回空串"


def test_no_page_uses_an_undefined_icon(caplog):
    """跑遍所有页面，断言没有任何图标名回退。

    这条测试是有来历的：统计卡上写了 `view_column`，而这个名字在自绘图标表里
    并不存在（那是 Material 的名字），结果那一格渲染出了一个空洞——
    而且没有任何报错。
    """
    import logging

    with caplog.at_level(logging.WARNING, logger="zhigou.icons"):
        at = _run()
        for page in ("首页", "智能分析", "商品比较", "历史记录", "个人设置", "项目说明"):
            _go_to_page(at, page)
            _assert_clean(at)

        # 也跑一遍有结果的路径，那里图标更多
        _go_to_page(at, "首页")
        at.button(key="quick_大学生买笔记本").click().run()
        _button(at, "开始分析").click().run()
        _assert_clean(at)
        _go_to_page(at, "商品比较")
        _button(at, "用上次分析的推荐").click().run()

    fallbacks = [r.message for r in caplog.records if "未知图标名" in str(r.message)]
    assert fallbacks == [], f"有页面用了不存在的图标名：{fallbacks}"


# --------------------------------------------------------------------------
# 设置页
# --------------------------------------------------------------------------


def test_settings_page_renders_and_exposes_the_real_options(catalog):
    at = _run()
    _go_to_page(at, "个人设置")
    _assert_clean(at)

    assert "品牌偏好" in _all_text(at)
    assert "价格取向" in _all_text(at)
    assert "长期关注项" in _all_text(at)


def test_preference_notice_is_not_shown_when_nothing_was_applied():
    """没设过任何偏好时，不能显示「已自动带上偏好」——那是假话。"""
    at = _run()
    at.button(key="quick_大学生买笔记本").click().run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert _state(at, "zg_prefs_applied") is False
    assert "已自动带上" not in _all_text(at)


def test_preferences_are_applied_and_reported():
    """设了偏好之后，提示必须出现，且核心需求确实被补进了需求里。

    经会话状态驱动而不是操作 pills 控件：AppTest 对 `st.pills` 的选项
    表示形式不稳定（set_value 会报 `content: "p" is not in list`），
    而保存按钮本来就是从会话状态读值的，这条路径覆盖的正是真实逻辑。
    """
    at = _run()
    _go_to_page(at, "个人设置")

    at.session_state["zg_pref_focus"] = ["续航", "便携"]
    at.run()
    _button(at, "保存设置").click().run()
    _assert_clean(at)

    _go_to_page(at, "首页")
    at.button(key="quick_大学生买笔记本").click().run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert _state(at, "zg_prefs_applied") is True
    assert "已自动带上" in _all_text(at)

    demand = _state(at, "zg_demand")
    assert "续航" in demand.core_needs
    assert "便携" in demand.core_needs


# --------------------------------------------------------------------------
# 历史记录与收藏（阶段四）
# --------------------------------------------------------------------------


def _analyze_laptop(at: AppTest) -> AppTest:
    """从首页快速开始跑一次完整分析。"""
    _go_to_page(at, "首页")
    at.button(key="quick_大学生买笔记本").click().run()
    _button(at, "开始分析").click().run()
    return at


def test_analysis_is_saved_to_history():
    at = _analyze_laptop(_run())
    _assert_clean(at)

    assert _state(at, state.KEY_REPORT) is not None

    _go_to_page(at, "历史记录")
    _assert_clean(at)
    assert "共 1 条记录" in _all_text(at)


def test_repeated_submit_does_not_duplicate_the_record():
    """spec：快速重复点击只产生一条历史记录。"""
    at = _analyze_laptop(_run())

    for _ in range(3):
        _button(at, "开始分析").click().run()
    _assert_clean(at)

    _go_to_page(at, "历史记录")
    assert "共 1 条记录" in _all_text(at), "重复提交产生了重复记录"


def test_changing_conditions_creates_a_second_record():
    """去重是按条件指纹的，换了条件必须另存一条。"""
    at = _analyze_laptop(_run())

    _go_to_page(at, "智能分析")
    at.text_input[0].set_value("5000").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    _go_to_page(at, "历史记录")
    assert "共 2 条记录" in _all_text(at)


def test_history_report_can_be_reopened():
    at = _analyze_laptop(_run())
    _go_to_page(at, "历史记录")

    _button(at, "查看详情").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "需求摘要" in body
    assert "最终决策建议" in body
    assert "需要进一步核实的信息" in body


def test_reopened_report_is_marked_with_its_generation_time():
    at = _analyze_laptop(_run())
    _go_to_page(at, "历史记录")
    _button(at, "查看详情").click().run()
    _assert_clean(at)

    assert "生成时间：" in _all_text(at)


def test_history_empty_state():
    at = _run()
    _go_to_page(at, "历史记录")
    _assert_clean(at)
    assert "还没有分析记录" in _all_text(at)


def test_corrupt_database_reports_but_does_not_block_analysis(tmp_path, monkeypatch):
    """spec：数据库损坏时历史页给出提示，智能分析页仍可正常分析。"""
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"definitely not a sqlite file" * 60)
    monkeypatch.setenv("ZHIGOU_DB_PATH", str(broken))

    at = _run()
    _go_to_page(at, "历史记录")
    _assert_clean(at)
    assert "暂不可用" in _all_text(at)

    # 关键：分析仍然可用，而且不能把 traceback 或兜底错误抛出来
    _analyze_laptop(at)
    _assert_clean(at)
    assert _state(at, state.KEY_RESULT) is not None


def test_export_buttons_are_available_after_analysis():
    """导出入口用的是 st.download_button。

    它不在 `at.button` 里（AppTest 把下载按钮单独归类），
    要用 `at.get("download_button")` 取。
    """
    at = _analyze_laptop(_run())
    _assert_clean(at)

    downloads = at.get("download_button")
    labels = [d.label for d in downloads]
    assert len(downloads) == 2, f"应有 Markdown 与 CSV 两个导出入口，实际 {labels}"
    assert any("Markdown" in label for label in labels), labels
    assert any("CSV" in label for label in labels), labels


def test_exported_content_covers_the_whole_report():
    """导出的是报告本身，不是空文件——按钮在不在是一回事，内容对不对是另一回事。"""
    from src import report_service

    at = _analyze_laptop(_run())
    report = _state(at, state.KEY_REPORT)
    assert report is not None

    markdown = report_service.to_markdown(report)
    for section in ("需求摘要", "推荐商品及排序", "最终决策建议", "数据说明"):
        assert section in markdown

    csv_text = report_service.to_csv(report)
    assert csv_text.splitlines()[0]
    assert "商品名称" in csv_text


def test_favorite_round_trip():
    at = _analyze_laptop(_run())

    labels = [b.label for b in at.button]
    assert "收藏这件商品" in labels, f"推荐列表里没有收藏按钮：{labels}"

    _button(at, "收藏这件商品").click().run()
    _assert_clean(at)

    _go_to_page(at, "历史记录")
    body = _all_text(at)
    assert "共收藏 1 件商品" in body


def test_unfavorite_removes_it():
    at = _analyze_laptop(_run())
    _button(at, "收藏这件商品").click().run()

    _go_to_page(at, "历史记录")
    _button(at, "取消收藏").click().run()
    _assert_clean(at)

    assert "还没有收藏任何商品" in _all_text(at)


def test_favorite_of_a_missing_product_is_labelled():
    """spec：收藏的商品已从数据文件移除时，界面标注且不崩溃。"""
    from src import database

    database.add_favorite("GONE-9999")

    at = _run()
    _go_to_page(at, "历史记录")
    _assert_clean(at)

    body = _all_text(at)
    assert "GONE-9999" in body
    assert "已不在当前数据集" in body


def test_typed_demand_survives_a_page_switch():
    """切页回来后输入还在。

    这条测试锁的是一个真实缺陷：侧栏导航按钮的处理器里调了 `st.rerun()`，
    那次运行渲染完侧栏就中断了，正文控件没被「看到」，Streamlit 会清掉它们的
    session 状态。表现出来就是用户写了一半的需求，去历史页看一眼再回来就没了。
    修法是给输入做一份不绑控件的镜像，键不见了就恢复。
    """
    at = _run()
    _go_to_page(at, "智能分析")

    typed = "预算 2500，想买一副通勤用的降噪耳机"
    at.text_area[0].set_value(typed).run()
    assert at.text_area[0].value == typed

    _go_to_page(at, "历史记录")
    _go_to_page(at, "智能分析")

    assert at.text_area[0].value == typed, "切页之后输入被清掉了"


def test_selected_products_survive_a_page_switch():
    """比较页选中的商品同样不能被切页清掉。"""
    at = _analyze_laptop(_run())
    _go_to_page(at, "商品比较")

    _button(at, "用上次分析的推荐").click().run()
    picked = list(_state(at, "zg_compare_pick"))
    assert len(picked) >= 3

    _go_to_page(at, "首页")
    _go_to_page(at, "商品比较")

    assert list(_state(at, "zg_compare_pick")) == picked, "切页之后选中的商品被清掉了"


def test_clearing_conditions_does_not_get_undone_by_the_mirror():
    """清空是用户的明确意图，镜像不能把旧值恢复回来。"""
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("随便写点什么").run()
    assert at.text_area[0].value

    _button(at, "清空条件").click().run()
    _assert_clean(at)

    assert at.text_area[0].value == "", "镜像把已清空的内容又恢复了"
