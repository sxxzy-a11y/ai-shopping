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

import httpx

import pytest
from streamlit.testing.v1 import AppTest

from src import config
from src.ui import icons, state, theme

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_FILE = str(PROJECT_ROOT / "app.py")

#: app.py 兜底处理未预期异常时的文案。出现它就说明有东西炸了。
FALLBACK_TEXT = "操作未能完成，请稍后重试"


EXAMPLE_TEXT = (
    "我是一名大学生，预算 3000 元，想买一台主要用于 Python 编程、"
    "日常学习和偶尔玩游戏的笔记本电脑。我比较看重性能和性价比，"
    "不希望电脑太重。"
)


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

    # 控件上的文案（toogle 的说明、输入框的标题、按钮的字）也是"页面上可见文本"，
    # 不收进来会漏判——曾经因此以为「AI 开关没渲染」，其实只是断言取不到。
    for attr in (
        "selectbox", "multiselect", "text_input", "text_area", "toggle",
        "radio", "checkbox", "button", "slider", "number_input",
    ):
        for element in getattr(at, attr, []):
            label = getattr(element, "label", "")
            if label:
                chunks.append(str(label))

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
    "page",
    ["首页", "智能分析", "商品比较", "知识问答", "历史记录", "个人设置", "项目说明"],
)
def test_every_page_renders_without_exception(page):
    at = _run()
    _go_to_page(at, page)
    _assert_clean(at)


def test_navigation_lists_every_page():
    """导航项与规格里的页面清单必须一致——加页忘挂导航是很容易漏的。"""
    from app import NAV_ITEMS

    assert [name for name, _icon, _renderer in NAV_ITEMS] == [
        "首页",
        "智能分析",
        "商品比较",
        "知识问答",
        "历史记录",
        "个人设置",
        "项目说明",
    ]


# --------------------------------------------------------------------------
# 首页输入 → 分析 → 比较（这条链路踩坑最多）
# --------------------------------------------------------------------------


def test_home_input_jumps_to_analysis_and_runs_it():
    """首页的按钮不再只是跳转——它带着需求过去并**立即执行**。

    去掉快速开始的示例按钮之后，这是首页唯一的入口，只点一次就该出结果。
    """
    at = _run()
    _go_to_page(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert _state(at, "zg_current_page") == "智能分析"
    assert "预算 3000 元" in at.text_area[0].value, "需求没有带过去"

    body = _all_text(at)
    assert "需求摘要" in body
    assert "为你推荐" in body, "跳过去了但没有直接出结果"

    result = _state(at, "zg_result")
    assert result is not None and result.has_results
    assert result.within_budget


def test_home_button_with_empty_input_just_navigates():
    """首页没填内容时，跳到分析页等着，不跑空分析、也不弹错误。

    这里刻意**不**显示红色报错：用户落到分析页，输入框就在眼前空着，
    一看就明白。真正该报错的是「在分析页点了开始分析却什么都没填」，
    那条由 test_analysis_without_any_input_shows_chinese_hint 覆盖。
    """
    at = _run()
    _go_to_page(at, "首页")
    at.text_area[0].set_value("").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert _state(at, "zg_current_page") == "智能分析"
    assert _state(at, "zg_result") is None, "空输入不该跑出结果"

    body = _all_text(at)
    assert "还没有分析结果" in body
    assert "请先描述你的购买需求" not in body, "空输入跳转不该弹错误"


def test_filling_comparison_from_analysis_does_not_blow_up(catalog):
    """这条曾经真的炸过：控件创建之后写它的 session_state 键。"""
    at = _run()
    _go_to_page(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
    _button(at, "开始分析").click().run()

    _go_to_page(at, "商品比较")
    _assert_clean(at)

    _button(at, "用上次分析的推荐").click().run()
    _assert_clean(at)

    picked = at.session_state["zg_compare_pick"]
    assert len(picked) >= config.MIN_COMPARE_COUNT, (
        f"填充后应至少选中 {config.MIN_COMPARE_COUNT} 件，实际 {len(picked)}"
    )
    assert "横向比较" in _all_text(at)

    # 预填必须是一组**同类**商品：比较只在同类之间有意义
    category_by_label = {
        _label_of(p): p.category for p in catalog.products
    }
    categories = {category_by_label[label] for label in picked}
    assert len(categories) == 1, f"预填混选了多个类别：{categories}"


def _label_of(product) -> str:
    """与比较页 `_label` 一致的展示文案，用于把选项标签映射回商品。"""
    return f"{product.name or product.id}（{product.price_label}）"


def test_compare_options_are_scoped_to_the_chosen_category(catalog):
    """spec：比较限定在同一类别——候选里只有所选类别的商品。"""
    at = _run()
    _go_to_page(at, "商品比较")
    _assert_clean(at)

    # 换到手机类别：候选应只剩手机
    at.selectbox[0].set_value(config.category_label("phone")).run()
    _assert_clean(at)

    phone_labels = {_label_of(p) for p in catalog.by_category("phone")}
    assert set(at.multiselect[0].options) == phone_labels

    # 选两件手机，再换到服饰：上一类别的选择应被清掉，候选换成服饰
    picks = sorted(phone_labels)[: config.MIN_COMPARE_COUNT]
    at.multiselect[0].set_value(picks).run()
    _assert_clean(at)
    assert list(at.session_state["zg_compare_pick"]) == picks

    at.selectbox[0].set_value(config.category_label("apparel")).run()
    _assert_clean(at)
    assert list(at.session_state["zg_compare_pick"]) == [], (
        "换类别后应清空上一类别的选择，否则会留下不在候选里的幽灵选中项"
    )
    apparel_labels = {_label_of(p) for p in catalog.by_category("apparel")}
    assert set(at.multiselect[0].options) == apparel_labels


def test_clearing_conditions_does_not_blow_up():
    """这条也炸过：清空按钮在输入控件创建之后动它们的键。"""
    at = _run()
    _go_to_page(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
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

    result = _state(at, "zg_result")
    assert result.relaxations
    assert "放宽条件的建议" in _all_text(at)


def test_comparison_with_too_few_products_shows_hint():
    at = _run()
    _go_to_page(at, "商品比较")
    _assert_clean(at)
    assert "无法进行横向比较" in _all_text(at)


def test_two_products_can_be_compared():
    """spec：两件商品比较表生成——「二选一」是最常见的比较场景。"""
    at = _run()
    _go_to_page(at, "商品比较")
    _assert_clean(at)

    options = at.multiselect[0].options
    at.multiselect[0].set_value(list(options[: config.MIN_COMPARE_COUNT])).run()

    _assert_clean(at)
    body = _all_text(at)
    assert "横向比较" in body, "两件商品应该能生成比较表"
    assert "无法进行横向比较" not in body


# --------------------------------------------------------------------------
# 数据与提示
# --------------------------------------------------------------------------


def test_catalog_reloads_after_the_data_file_is_refreshed(tmp_path, monkeypatch):
    """接入脚本刷新数据文件后，应用应自动加载新数据，不用重启。

    缓存键里带着文件修改时间，所以同一个进程内也能观察到重新加载。
    """
    import json
    import os

    data_file = tmp_path / "products.json"

    def write(products):
        data_file.write_text(
            json.dumps({"products": products}, ensure_ascii=False), encoding="utf-8"
        )

    def product(pid: str, name: str) -> dict:
        return {
            "id": pid,
            "name": name,
            "category": "laptop",
            "price": 3000,
            "brand": "测试品牌",
            "specs": {"cpu_tier": 3},
            "use_cases": ["办公"],
            "pros": ["测试"],
            "cons": ["测试"],
            "data_source": "演示数据 · 测试夹具",
            "updated_at": "2026-01-01",
        }

    monkeypatch.setenv("ZHIGOU_PRODUCTS_PATH", str(data_file))

    write([product("T1", "一号")])
    os.utime(data_file, (1_000_000, 1_000_000))
    assert len(state.get_catalog()) == 1

    write([product("T1", "一号"), product("T2", "二号")])
    os.utime(data_file, (2_000_000, 2_000_000))
    assert len(state.get_catalog()) == 2, "数据文件刷新后应自动加载新数据"


def test_data_issue_marker_reaches_the_screen(tmp_path, monkeypatch):
    """记录内部矛盾的商品，界面上必须出现「资料存疑」标记。

    只在业务层断言 `data_issues` 非空，不能说明它真的渲染出来了——
    这个文件存在的理由就是这类「业务层看不见、只有跑页面才暴露」的问题。
    """
    import json

    data_file = tmp_path / "products.json"
    data_file.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "id": "FLAG1",
                        "name": "存疑笔记本",
                        "category": "laptop",
                        "price": 3999,
                        "brand": "测试品牌",
                        "specs": {"cpu_tier": 3},
                        "use_cases": ["办公"],
                        "pros": ["续航长", "屏幕一般"],
                        "cons": ["屏幕一般"],  # 与优点重复 → 触发内部矛盾
                        "data_source": "演示数据 · 测试夹具",
                        "updated_at": "2026-01-01",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ZHIGOU_PRODUCTS_PATH", str(data_file))

    at = _run()
    _go_to_page(at, "首页")
    at.text_area[0].set_value("预算 5000 元，买一台办公用的笔记本电脑").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "资料存疑" in body, "标记没有渲染到页面上"
    assert "屏幕一般" in body, "标记只给了标签，没有说明为什么存疑"


def test_clean_catalog_shows_no_data_issue_marker():
    """正常数据不该出现标记——否则这个标记会变成人人都忽略的装饰。"""
    at = _run()
    _go_to_page(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert "资料存疑" not in _all_text(at)


# --------------------------------------------------------------------------
# 知识问答页
# --------------------------------------------------------------------------


def _ask_knowledge(at: AppTest, question: str):
    """在知识问答页提问并返回渲染后的页面对象。"""
    _go_to_page(at, "知识问答")
    at.text_area[0].set_value(question).run()
    _button(at, "查找资料").click().run()
    return at


def test_knowledge_page_shows_passages_with_sources():
    """本地模式展示**原文片段与来源**，不做生成。"""
    at = _ask_knowledge(_run(), "主动降噪和被动降噪有什么区别")
    _assert_clean(at)

    body = _all_text(at)
    assert "找到的资料" in body
    assert "来源：" in body, "结果必须带出处"
    assert "更新于" in body, "需求明确要求展示资料来源与更新时间"


def test_knowledge_page_says_so_when_nothing_is_found():
    """检索不到时明确说明，且**不展示任何来源**——没资料就没有可引用的来源。"""
    at = _ask_knowledge(_run(), "今天天气怎么样")
    _assert_clean(at)

    body = _all_text(at)
    assert "没有找到" in body
    assert "来源：" not in body, "没有资料却给出了来源"
    assert "更新于" not in body


def test_knowledge_page_refuses_price_questions():
    """价格类问题不给检索结论，改为引导去筛选——检索不理解数值约束。"""
    at = _ask_knowledge(_run(), "500 元以内有什么降噪耳机")
    _assert_clean(at)

    body = _all_text(at)
    assert "价格" in body and "筛选" in body
    assert "找到的资料" not in body, "价格问题不该走检索"


def test_knowledge_page_guides_to_analysis_on_click():
    at = _ask_knowledge(_run(), "预算 2000 的耳机推荐")
    _button(at, "带着这个问题去筛选商品").click().run()
    _assert_clean(at)

    assert _state(at, "zg_current_page") == "智能分析"


def test_knowledge_page_empty_input_is_rejected():
    at = _run()
    _go_to_page(at, "知识问答")
    _button(at, "查找资料").click().run()
    _assert_clean(at)

    assert "请先输入" in _all_text(at)


def test_knowledge_page_example_buttons_work():
    at = _run()
    _go_to_page(at, "知识问答")
    _button(at, "通勤戴的耳机怎么选").click().run()
    _assert_clean(at)

    assert "找到的资料" in _all_text(at)


def test_knowledge_index_reloads_after_corpus_edit(tmp_path, monkeypatch):
    """编辑语料后，应用下一次渲染就用新语料——不用重启。

    缓存键里带着语料文件的修改时间。只取目录 mtime 是不够的：
    **改文件内容不会改目录的 mtime**，那是最常见的编辑方式。
    """
    import os

    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()

    def write(body: str, stamp: float) -> None:
        path = knowledge / "guide.md"
        path.write_text(
            "---\ntitle: 测试指南\ntype: service\nsource: 测试\n"
            "updated_at: 2026-01-01\n---\n" + body,
            encoding="utf-8",
        )
        os.utime(path, (stamp, stamp))

    monkeypatch.setenv("ZHIGOU_KNOWLEDGE_DIR", str(knowledge))

    def written_bodies() -> list[str]:
        """只看**手写文档**的正文。

        索引里还始终含 112 条商品级合成条目（它们来自商品数据，不受语料目录
        影响），所以判断「语料换了没有」必须把手写部分单独拎出来。
        """
        return [
            document.body
            for document in corpus_documents()
            if document.doc_type != "product"
        ]

    def corpus_documents():
        import src.knowledge.corpus as corpus_module
        from src import config as config_module

        return corpus_module.load_documents(config_module.knowledge_dir())

    write("关于折叠屏手机的转轴寿命。", 1_000_000)
    state.get_knowledge_index()  # 建一次，让缓存生效
    assert any("折叠屏" in body for body in written_bodies())

    write("关于机械键盘的轴体手感。", 2_000_000)
    state.get_knowledge_index()  # 缓存键变了，应当重建
    bodies = written_bodies()
    assert any("机械键盘" in body for body in bodies), "改语料后没有重新加载"
    assert not any("折叠屏" in body for body in bodies), "旧语料还在索引里"


def test_knowledge_index_survives_missing_corpus(tmp_path, monkeypatch):
    """语料目录不存在时，手写部分为空、页面提示无资料，**其余功能不受影响**。

    注意索引**不是空的**：112 条商品级条目来自商品数据，与语料目录无关。
    """
    monkeypatch.setenv("ZHIGOU_KNOWLEDGE_DIR", str(tmp_path / "不存在"))

    import src.knowledge.corpus as corpus_module
    from src import config as config_module

    assert corpus_module.load_documents(config_module.knowledge_dir()) == []
    assert state.get_knowledge_index().size == 112, "商品级条目不该受语料目录影响"


def test_knowledge_page_degrades_when_ai_fails(monkeypatch):
    """AI 作答失败时**降级为直接展示片段**，并说明已降级。

    片段展示本来就是本地模式的形态——失败只丢掉「组织好的回答」，
    不是把整个问答功能弄没了。
    """
    from src import ai_enhance, config
    from src.errors import UpstreamUnavailable

    monkeypatch.setenv(config.LLM_API_KEY_ENV, "sk-test-not-real")

    def _boom(*_args, **_kwargs):
        raise UpstreamUnavailable("模型服务暂时不可用。")

    monkeypatch.setattr(ai_enhance, "answer_from_knowledge", _boom)

    at = _run()
    _go_to_page(at, "知识问答")
    at.toggle[0].set_value(True).run()
    at.text_area[0].set_value("通勤戴的耳机怎么选").run()
    _button(at, "查找资料").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "降级" in body, "没有告知用户已降级"
    assert "找到的资料" in body, "AI 失败把片段展示也一起弄没了"
    assert "基于资料的回答" not in body, "作答失败了却还是展示了回答区"


# --------------------------------------------------------------------------
# Agent 执行轨迹（界面）
# --------------------------------------------------------------------------


def _agent_reply_with_tools(calls: list[dict], answer: str = "好了") -> httpx.Response:
    import json

    return httpx.Response(
        200,
        json={
            "model": "stub-model",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": call["id"],
                                "type": "function",
                                "function": {
                                    "name": call["name"],
                                    "arguments": json.dumps(call["args"], ensure_ascii=False),
                                },
                            }
                            for call in calls
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"total_tokens": 10},
        },
    )


def _run_agent_analysis(enable_ai, handler) -> AppTest:
    enable_ai(handler)
    at = _run()
    _go_to_page(at, "智能分析")
    at.toggle[0].set_value(True).run()
    at.text_area[0].set_value("预算 3000 买笔记本，主要编程，看重性能").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)
    return at


def test_trace_shows_real_tool_calls(enable_ai):
    """轨迹展示**真实发生过的调用**：工具名、参数、结果摘要。"""
    state = {"n": 0}

    def handler(request):
        if _is_parse_request(request):
            return _ai_reply(_parse_payload())
        if _is_agent_request(request):
            state["n"] += 1
            if state["n"] == 1:
                return _agent_reply_with_tools(
                    [{"id": "c1", "name": "search_products",
                      "args": {"category": "laptop", "budget_max": 3000}}]
                )
            return _agent_reply("综合筛选结果给出建议。")
        return _ai_reply("{}")

    at = _run_agent_analysis(enable_ai, handler)
    body = _all_text(at)

    assert "AI 执行过程" in body
    assert "search_products" in body
    assert "参数：" in body, "要展示模型给的参数，否则看不出它调了什么"
    assert "结果：" in body


def test_rejected_call_is_marked_in_the_trace(enable_ai):
    """被参数校验拒绝的调用也要展示，并标成醒目状态。

    那不是失败展示——是**校验在起作用的证据**。
    """
    state = {"n": 0}

    def handler(request):
        if _is_parse_request(request):
            return _ai_reply(_parse_payload())
        if _is_agent_request(request):
            state["n"] += 1
            if state["n"] == 1:
                # 编造一个不存在的品类
                return _agent_reply_with_tools(
                    [{"id": "c1", "name": "search_products", "args": {"category": "平板"}}]
                )
            return _agent_reply("换个说法再试。")
        return _ai_reply("{}")

    at = _run_agent_analysis(enable_ai, handler)
    body = _all_text(at)

    assert "参数被拒" in body
    assert "平板" in body, "要能看到模型给错了什么"


def test_trace_is_empty_note_when_no_tools_used(enable_ai):
    """没调工具时说明「本次未使用工具」，不展示伪造的流程。"""

    def handler(request):
        if _is_parse_request(request):
            return _ai_reply(_parse_payload())
        if _is_agent_request(request):
            return _agent_reply("直接回答。")
        return _ai_reply("{}")

    at = _run_agent_analysis(enable_ai, handler)
    body = _all_text(at)

    assert "未使用工具" in body
    # 「第 N 轮」是轨迹步骤独有的标记——评分说明里也会出现「参数：」，
    # 拿它做断言会误判。
    assert "第 1 轮" not in body, "没调工具却渲染出了轨迹步骤"


def test_agent_failure_degrades_with_full_results(enable_ai):
    """编排失败时降级：给出提示，且**筛选、评分、排序结果一个不少**。"""
    state = {"n": 0}

    def handler(request):
        if _is_parse_request(request):
            return _ai_reply(_parse_payload())
        if _is_agent_request(request):
            state["n"] += 1
            return httpx.Response(500, json={"error": "boom"})
        return _ai_reply("{}")

    at = _run_agent_analysis(enable_ai, handler)
    body = _all_text(at)

    assert "为你推荐" in body, "降级后推荐结果不能少"
    assert "系统匹配评分" in body, "评分还在"
    assert "AI 执行过程" not in body


def test_local_mode_does_not_show_any_ai_section():
    """不配密钥时整条 AI 路径都不出现——这是断网也能演示的保障。"""
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("预算 3000 买笔记本，主要编程").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "为你推荐" in body
    assert "AI 执行过程" not in body
    assert "AI 的分析结论" not in body




# --------------------------------------------------------------------------
# 超预算条数如实展示（变更 fix-over-budget-count）
# --------------------------------------------------------------------------


def test_over_budget_count_shown_is_the_real_total(catalog):
    """界面展示的是**真实总数**，不是截断后的列表长度。

    原问题：10 件超预算只显示 6 件，界面还说成 6 件，账面对不上。
    """
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("预算 500 元的通勤降噪耳机").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    result = _state(at, "zg_result")
    assert result is not None
    body = _all_text(at)

    # 统计行与小节标题都用真实总数
    assert f"{result.over_budget_total} 件" in body
    # 预算内 + 超预算真实总数 == 候选总数（账面要闭合）
    assert len(result.within_budget) + result.over_budget_total == result.candidate_count


def test_no_extra_note_when_all_over_budget_shown(catalog):
    """全部展示时不出「还有 N 件未列出」——那是噪音。"""
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("预算 500 元的通勤降噪耳机").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    result = _state(at, "zg_result")
    assert result.over_budget_hidden == 0
    assert "没有列出" not in _all_text(at)


def test_truncation_is_disclosed(catalog):
    """截断时说明还有多少件未列出。"""
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("预算 100 元的耳机").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    result = _state(at, "zg_result")
    assert result.over_budget_hidden > 0
    body = _all_text(at)
    assert "没有列出" in body
    assert str(result.over_budget_hidden) in body
    assert "调高" in body, "要告诉用户怎么办"

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
    _go_to_page(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
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
        _go_to_page(at, "首页")
        at.text_area[0].set_value(EXAMPLE_TEXT).run()
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
    _go_to_page(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
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
    _go_to_page(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
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
    """在首页输入需求并直接跑出结果，供后面的界面测试复用。"""
    _go_to_page(at, "首页")
    _go_to_page(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
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


# --------------------------------------------------------------------------
# AI 增强模式（全部走打桩服务，不碰真实 API）
# --------------------------------------------------------------------------


def _stub_service(handler, *, key: str = "sk-test-000000000000"):
    """造一个走打桩传输的 AI 服务。"""
    from src.ai_service import AIService

    return AIService(
        api_key=key,
        base_url="https://example.invalid/v1",
        model="stub-model",
        timeout_s=5,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _ai_reply(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "stub-model",
            "choices": [
                {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"total_tokens": 10},
        },
    )


@pytest.fixture
def enable_ai(monkeypatch):
    """打开 AI 通路，用打桩服务替换真实服务。

    conftest 已经删掉了环境变量里的密钥，就算不打桩也只会走本地模式；
    打桩是为了覆盖「模型确实返回了东西」的那条分支。
    """
    from src import ai_service

    def install(handler) -> None:
        monkeypatch.setattr(ai_service, "get_service", lambda: _stub_service(handler))

    return install


def _parse_payload(**overrides) -> str:
    import json

    payload = {
        "category": "laptop",
        "budget": 3000,
        "use_cases": ["编程"],
        "core_needs": ["性能"],
        "compromises": [],
        "brand_preferences": [],
        "hard_constraints": [],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def _is_parse_request(request) -> bool:
    """靠系统提示里的关键词区分请求类型。

    三类请求的系统提示各不相同：需求解析用「解析器」，Agent 编排用
    「可以调用工具」，其余是单轮解读/作答。
    """
    import json

    body = json.loads(request.content)
    return "解析器" in body["messages"][0]["content"]


def _is_agent_request(request) -> bool:
    """Agent 编排请求——它带着 `tools` 声明。"""
    import json

    return "tools" in json.loads(request.content)


def _agent_reply(content: str) -> httpx.Response:
    """Agent 的最终作答（不请求工具）。"""
    return _ai_reply(content)


def test_ai_toggle_is_hidden_when_not_configured():
    """没配密钥时不该出现 AI 开关——出现了点开也是坏的。"""
    at = _run()
    _go_to_page(at, "智能分析")
    _assert_clean(at)

    assert "启用 AI 增强" not in _all_text(at)
    assert "本地演示模式" in _all_text(at)


def test_ai_toggle_appears_when_configured(enable_ai):
    enable_ai(lambda r: _ai_reply(_parse_payload()))

    at = _run()
    _go_to_page(at, "智能分析")
    _assert_clean(at)
    assert "启用 AI 增强" in _all_text(at)


def test_enabling_ai_shows_the_data_sharing_notice(enable_ai):
    """spec：调用外部服务前须说明发送的数据范围。"""
    enable_ai(lambda r: _ai_reply(_parse_payload()))

    at = _run()
    _go_to_page(at, "智能分析")
    at.toggle[0].set_value(True).run()
    _assert_clean(at)

    body = _all_text(at)
    assert "需求原文" in body
    assert "不会发送" in body


def test_ai_parse_is_used_when_enabled(enable_ai):
    seen: list = []

    def handler(request):
        seen.append(request)
        return _ai_reply(_parse_payload(category="headphone", budget=800, core_needs=["降噪"]))

    enable_ai(handler)

    at = _run()
    _go_to_page(at, "智能分析")
    at.toggle[0].set_value(True).run()
    at.text_area[0].set_value("想买副通勤用的耳机，预算 800").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert _state(at, "zg_parse_engine") == "ai", "没有走 AI 解析"
    demand = _state(at, "zg_demand")
    assert demand.category == "headphone"
    assert demand.core_needs == ["降噪"]
    assert seen, "没有向模型发出请求"


def test_ai_failure_degrades_to_rules_with_a_notice(enable_ai):
    """spec：AI 调用失败时降级到本地规则模式，不崩溃，且告知用户。"""
    enable_ai(lambda r: httpx.Response(500, text="upstream boom"))

    at = _run()
    _go_to_page(at, "智能分析")
    at.toggle[0].set_value(True).run()
    at.text_area[0].set_value("预算 3000 买笔记本电脑，主要编程").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert "本地规则" in _all_text(at), "降级了但没告诉用户"

    assert _state(at, "zg_parse_engine") == "rule", "失败后没有回退到规则解析"
    demand = _state(at, "zg_demand")
    assert demand.category == "laptop", "降级后规则解析应当仍然认得类别"
    assert _state(at, state.KEY_RESULT) is not None, "降级后结果应当可用"


def test_ai_timeout_degrades_gracefully(enable_ai):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    enable_ai(handler)

    at = _run()
    _go_to_page(at, "智能分析")
    at.toggle[0].set_value(True).run()
    at.text_area[0].set_value("预算 3000 买笔记本电脑").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert "超时" in _all_text(at)
    assert _state(at, state.KEY_RESULT) is not None


def test_ai_agent_answer_and_trace_are_shown(enable_ai):
    """AI 路径展示「分析结论」与「执行过程」，且都标明来自 AI。"""
    def handler(request):
        if _is_parse_request(request):
            return _ai_reply(_parse_payload())
        if _is_agent_request(request):
            return _agent_reply("综合工具返回的数据，这几款适合编程。")
        return _ai_reply("{}")

    enable_ai(handler)

    at = _run()
    _go_to_page(at, "智能分析")
    at.toggle[0].set_value(True).run()
    at.text_area[0].set_value("预算 3000 买笔记本，主要编程，看重性能").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "AI 的分析结论" in body
    assert "适合编程" in body
    assert "AI 执行过程" in body
    assert "未使用工具" in body, "模型没调工具时要如实说明，不能伪造流程"


def test_ai_agent_not_used_when_switch_is_off():
    """没打开 AI 开关时不出现执行过程——那条路径根本没跑编排。"""
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("预算 3000 买笔记本，主要编程").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "AI 执行过程" not in body
    assert "AI 的分析结论" not in body


def test_explanation_failure_keeps_the_recommendations(enable_ai):
    """解读失败只丢解读，规则算出的推荐结果必须原样保留。"""

    def handler(request):
        if _is_parse_request(request):
            return _ai_reply(_parse_payload())
        return _ai_reply("我拒绝输出 JSON")

    enable_ai(handler)

    at = _run()
    _go_to_page(at, "智能分析")
    at.toggle[0].set_value(True).run()
    at.text_area[0].set_value("预算 3000 买笔记本，主要编程").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    result = _state(at, state.KEY_RESULT)
    assert result is not None and result.within_budget, "解读失败把推荐也弄丢了"
    assert "为你推荐" in _all_text(at)
    assert _state(at, "zg_ai_explanation") is None


def test_ai_explanations_never_reach_the_stored_report(enable_ai, catalog):
    """报告存的是规则快照。

    AI 解读不进报告，这样历史结论不会因为模型换了、超时了而前后不一致。
    """
    import json

    every_id = [p.id for p in catalog.by_category("laptop")]

    def handler(request):
        if _is_parse_request(request):
            return _ai_reply(_parse_payload())
        return _ai_reply(
            json.dumps(
                {"overview": "总述", "per_product": [{"product_id": i, "why": "理由"} for i in every_id]},
                ensure_ascii=False,
            )
        )

    enable_ai(handler)

    at = _run()
    _go_to_page(at, "智能分析")
    at.toggle[0].set_value(True).run()
    at.text_area[0].set_value("预算 3000 买笔记本，主要编程").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    from src import report_service

    report = _state(at, state.KEY_REPORT)
    assert report is not None
    assert "AI 解读" not in report_service.to_markdown(report)


# --------------------------------------------------------------------------
# 追溯表补缺：这几条 Scenario 之前只有手工验证，没有自动化断言
# --------------------------------------------------------------------------


def test_product_card_carries_the_demo_data_source():
    """spec：商品卡片要显示演示数据来源标注。

    之前只在首页断言过免责声明，卡片本身的标注没测。
    """
    at = _analyze_laptop(_run())
    _assert_clean(at)

    body = _all_text(at)
    assert "数据来源" in body
    assert "演示数据" in body
    assert "更新时间" in body


def test_reset_preferences_restores_defaults():
    """spec：恢复默认 —— 所有偏好回到初始状态并落盘。"""
    at = _run()
    _go_to_page(at, "个人设置")

    at.session_state["zg_pref_focus"] = ["续航", "便携"]
    at.session_state["zg_pref_priority"] = "performance"
    at.run()
    _button(at, "保存设置").click().run()
    _assert_clean(at)

    from src import settings

    saved = settings.load_preferences()
    assert saved.focus_areas == ["续航", "便携"]
    assert saved.price_priority == "performance"

    _button(at, "恢复默认").click().run()
    _assert_clean(at)

    restored = settings.load_preferences()
    assert restored.focus_areas == []
    assert restored.price_priority == "none", "恢复默认后没有回到初始状态"


def test_analysis_shows_a_processing_indicator():
    """spec：处理中给出状态反馈。

    `st.spinner` 在 AppTest 里不产生可断言的元素，所以这里断言
    「分析确实在按钮点击的那一次运行里同步完成」——它就是那个反馈的前提。
    视觉上的 spinner 由 Playwright 实测覆盖。
    """
    at = _run()
    _go_to_page(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()

    assert _state(at, state.KEY_RESULT) is None, "还没点分析就有结果了"
    _button(at, "开始分析").click().run()
    assert _state(at, state.KEY_RESULT) is not None, "点击后结果没有同步产出"
