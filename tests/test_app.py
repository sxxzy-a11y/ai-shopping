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

from src import config, data_loader
from src.auth import ROLE_ADMIN, ROLE_USER, User
from src.ui import icons, state, theme

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_FILE = str(PROJECT_ROOT / "app.py")

#: app.py 兜底处理未预期异常时的文案。出现它就说明有东西炸了。
FALLBACK_TEXT = "操作未能完成，请稍后重试"

#: 这些用例测的是**页面本身**，所以直接从一个「已登录」的会话起步。
#: 登录流程有自己的用例（见文件末的登录/越权小节），那些用 `_run(user=None)`
#: 从登录页开始走。这样分工的好处是：页面回归测试不必每次都先跑一遍登录，
#: 而登录本身也不会因为「反正都会被跳过」而失去覆盖。
TEST_USERNAME = "tester"
DEFAULT_USER = User(username=TEST_USERNAME, role=ROLE_USER)

#: 管理员会话。账号本身要不要真的建在库里，由各条用例自己决定——
#: 有些只关心「侧边栏露不露入口」，那只需要一个身份对象。
ADMIN_USERNAME = "root"
ADMIN_USER = User(username=ADMIN_USERNAME, role=ROLE_ADMIN)


EXAMPLE_TEXT = (
    "我是一名大学生，预算 6000 元，想买一台主要用于 Python 编程、"
    "日常学习和偶尔玩游戏的笔记本电脑。我比较看重性能和性价比，"
    "不希望电脑太重。"
)


def _ensure_account(user: User) -> None:
    """保证会话里那个账号在库里**真的存在且启用**。

    以前不需要这一步——会话里的用户对象就是全部依据。现在 `app.py` 每轮会
    查库校验（被停用/被删除的账号要让它的会话失效），所以夹具必须把账号真的
    建出来，否则应用会把测试会话当成「幽灵账号」踢回登录页。

    库坏了时**跳过**：那几条「损坏的库不该让应用停摆」的用例会先把库弄坏再启动，
    夹具在这里抛错就变成「夹具把用例搞挂了」。应用侧对读库失败是 fail-open
    （按仍然有效处理），所以跳过不会把会话踢掉。
    """
    from src import database
    from src.errors import ZhigouError

    try:
        if database.get_user(user.username) is None:
            database.create_user(user.username, "fixture-pass-1", role=user.role)
    except ZhigouError:
        return


def _run(timeout: float = 60, user: User | None = DEFAULT_USER) -> AppTest:
    """跑一次应用。**默认已登录**（见 `DEFAULT_USER` 的说明）。

    未登录的用例显式传 `user=None`。
    """
    at = AppTest.from_file(APP_FILE, default_timeout=timeout)
    if user is not None:
        _ensure_account(user)
        at.session_state[state.KEY_USER] = user
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
    #
    # `expander` 同理，而且它更隐蔽：折叠面板的标题在浏览器里明明白白
    # 显示着，但不在上面那些集合里。漏收它的代价是实测过的——管理页
    # 「已停用」与分类展示名两处断言都因此误判成「没生效」。
    for attr in (
        "selectbox", "multiselect", "text_input", "text_area", "toggle",
        "radio", "checkbox", "button", "slider", "number_input", "expander",
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
    for expected in ("首页", "智能分析", "商品比较", "历史记录", "个人设置", "关于"):
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
    ["首页", "智能分析", "商品比较", "AI 问答", "历史记录", "个人设置", "关于"],
)
def test_every_page_renders_without_exception(page):
    at = _run()
    _go_to_page(at, page)
    _assert_clean(at)


def test_navigation_lists_every_page():
    """导航项与顺序：「项目说明」稳定排在最后。

    它原先排在管理员三项**之前**，于是管理员看到的顺序里它被挤到中间——
    同一项在不同角色下的位置不一样。放到最后对两种角色都是一致的。
    """
    from app import NAV_ITEMS

    assert [item.name for item in NAV_ITEMS] == [
        "首页",
        "智能分析",
        "商品比较",
        "AI 问答",
        "历史记录",
        "用户管理",
        "全站概览",
        "商品维护",
        "知识库管理",
        "个人设置",
        "关于",
    ]
    assert NAV_ITEMS[-2].name == "个人设置", "个人设置应紧挨项目说明"
    assert NAV_ITEMS[-1].name == "关于"
    assert NAV_ITEMS[-1].admin_only is False, "它对所有角色可见，只是排在最后"


def test_admin_pages_are_marked_admin_only():
    """三个管理页必须挂上 `admin_only`，否则普通用户的侧边栏会露出它们。"""
    from app import NAV_ITEMS

    admin_only = {item.name for item in NAV_ITEMS if item.admin_only}
    assert admin_only == {"用户管理", "全站概览", "商品维护", "知识库管理"}


def test_knowledge_admin_page_renders_without_embedding_config():
    """知识库管理页：未配置向量服务时给出配置指引，而不是报错。"""
    at = _run(user=ADMIN_USER)
    _go_to_page(at, "知识库管理")
    _assert_clean(at)

    body = _all_text(at)
    assert "篇资料" in body
    assert "个切片" in body
    assert "ZHIGOU_EMBEDDING_API_KEY" in body, "要说明需要配置哪个环境变量"
    assert "尚未配置向量化服务" in body


def test_catalog_detail_tab_edits_product_fields():
    """参数 / 适用场景 / 亮点 / 不足 在「商品维护 → 详情与参数」里维护。"""
    from src import product_store

    at = _run(user=ADMIN_USER)
    _go_to_page(at, "商品维护")
    _assert_clean(at)

    body = _all_text(at)
    assert "选择商品" in body, "详情与参数标签页应可编辑商品详细字段"
    assert "适用场景" in body

    # 选择第一件商品，改四个字段后保存
    picker = at.selectbox("zg_cat_detail_pick")
    target = picker.options[0]
    picker.set_value(target).run()
    _assert_clean(at)

    product_id = target.split(" · ")[1].split("（")[0]

    at.text_area(f"zg_cat_detail_specs_{product_id}").set_value("cpu_tier: 4\nram_gb: 16")
    at.text_area(f"zg_cat_detail_use_{product_id}").set_value("办公\n学习")
    at.text_area(f"zg_cat_detail_pros_{product_id}").set_value("测试亮点")
    at.text_area(f"zg_cat_detail_cons_{product_id}").set_value("测试不足")
    _button(at, "保存详情").click().run()
    _assert_clean(at)

    saved = next(
        record
        for record in product_store.load_product_records()
        if str(record.get("id")) == product_id
    )
    assert saved["specs"]["cpu_tier"] == 4
    assert saved["use_cases"] == ["办公", "学习"]
    assert saved["pros"] == ["测试亮点"]
    assert saved["cons"] == ["测试不足"]
    # 来源与核验状态不因内容编辑而变化
    assert saved.get("data_status") != "verified"
    assert "测试亮点" in str(saved.get("pros"))


def test_catalog_edit_form_links_to_knowledge_content():
    """商品维护的编辑区不再重复提供这四个字段，而是指向知识库管理。"""
    at = _open_catalog_page(_run(user=ADMIN_USER))

    body = _all_text(at)
    assert "「详情与参数」中维护" in body

    keys = [widget.key for widget in at.text_area]
    assert not any(str(key).startswith("zg_cat_specs_") for key in keys), (
        "参数编辑已移到知识库管理，商品维护不应再有这个输入框"
    )


def test_knowledge_admin_adds_and_deletes_a_document(tmp_path, monkeypatch):
    """管理员可在知识库管理页新增与删除文件型资料。"""
    from src.knowledge.corpus import load_documents

    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    monkeypatch.setenv("ZHIGOU_KNOWLEDGE_DIR", str(knowledge))

    at = _run(user=ADMIN_USER)
    _go_to_page(at, "知识库管理")
    _assert_clean(at)

    # 新增
    at.text_input("zg_kb_new_title").set_value("测试资料")
    at.selectbox("zg_kb_new_type").set_value("service")
    at.text_input("zg_kb_new_source").set_value("测试来源")
    at.text_area("zg_kb_new_body").set_value("## 测试\n\n正文内容。")
    _button(at, "新增资料").click().run()
    _assert_clean(at)

    docs = load_documents(knowledge)
    created = next(d for d in docs if d.title == "测试资料")
    assert created.body.startswith("## 测试")

    # 删除
    at.checkbox("zg_kb_delete_confirm").set_value(True).run()
    _button(at, "删除资料").click().run()
    _assert_clean(at)

    assert all(d.title != "测试资料" for d in load_documents(knowledge))


def test_knowledge_admin_requires_admin():
    """界面隐藏之外，直接跳页也必须被挡住。"""
    at = _run()
    at.session_state[state.KEY_PAGE] = "知识库管理"
    at.run()
    _assert_clean(at)

    assert "没有执行该操作的权限" in _all_text(at)


# --------------------------------------------------------------------------
# 项目说明页的 API 配置
# --------------------------------------------------------------------------


def test_api_config_is_editable_for_admins():
    at = _run(user=ADMIN_USER)
    _go_to_page(at, "个人设置")
    _assert_clean(at)

    body = _all_text(at)
    assert "API 配置" in body, "管理员应看到完整配置区"
    labels = [item.label for item in at.text_input]
    assert "对话模型名" in labels
    assert "向量模型名" in labels
    assert "向量维度" in [item.label for item in at.number_input]
    assert "保存配置" in [b.label for b in at.button]


def test_api_config_is_read_only_for_regular_users():
    at = _run()
    _go_to_page(at, "个人设置")
    _assert_clean(at)

    body = _all_text(at)
    assert "API 配置" not in body, "普通用户不应看到服务配置"
    assert not any(item.label == "对话模型名" for item in at.text_input)


def test_saving_api_config_takes_effect_without_restart():
    from src import api_config, config

    at = _run(user=ADMIN_USER)
    _go_to_page(at, "个人设置")
    at.text_input(key="zg_api_llm_model").set_value("custom-model").run()

    _button(at, "保存配置").click().run()
    _assert_clean(at)

    assert api_config.load().get("llm_model") == "custom-model"
    assert config.llm_model() == "custom-model"


def test_api_config_never_shows_the_full_key():
    """保存过的密钥只能以脱敏形式出现——整串不得出现在页面里。"""
    from src import api_config

    secret = "sk-ws-H.PYILREX.Osb8.MEUCIQ-super-long-secret-value"
    api_config.save({"llm_api_key": secret})

    at = _run(user=ADMIN_USER)
    _go_to_page(at, "个人设置")
    _assert_clean(at)

    body = _all_text(at)
    assert secret not in body
    assert "****" in body


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
    assert "预算 6000 元" in at.text_area[0].value, "需求没有带过去"

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

    # 选两件手机，再换到笔记本电脑：上一类别的选择应被清掉，候选换成笔记本
    picks = sorted(phone_labels)[: config.MIN_COMPARE_COUNT]
    at.multiselect[0].set_value(picks).run()
    _assert_clean(at)
    assert list(at.session_state["zg_compare_pick"]) == picks

    at.selectbox[0].set_value(config.category_label("laptop")).run()
    _assert_clean(at)
    assert list(at.session_state["zg_compare_pick"]) == [], (
        "换类别后应清空上一类别的选择，否则会留下不在候选里的幽灵选中项"
    )
    laptop_labels = {_label_of(p) for p in catalog.by_category("laptop")}
    assert set(at.multiselect[0].options) == laptop_labels


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


def test_catalog_reloads_after_the_database_is_refreshed(tmp_path, monkeypatch):
    """接入脚本刷新商品库后，应用应自动加载新数据，不用重启。

    缓存键里带着**数据库文件**的修改时间——数据源从文件换成库之后，
    盯的还是「数据源变了没有」这件事，只是换了个文件盯。
    """
    import os

    from src import product_store

    db = tmp_path / "products.db"

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

    monkeypatch.setenv("ZHIGOU_PRODUCTS_DB_PATH", str(db))

    product_store.save_products([product("T1", "一号")], path=db)
    os.utime(db, (1_000_000, 1_000_000))
    assert len(state.get_catalog()) == 1

    product_store.save_products([product("T2", "二号")], path=db)
    os.utime(db, (2_000_000, 2_000_000))
    assert len(state.get_catalog()) == 2, "商品库刷新后应自动加载新数据"


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


def _ask_ai_qa(at: AppTest, question: str):
    """在 AI 问答页提问并返回渲染后的页面对象。"""
    _go_to_page(at, "AI 问答")
    at.text_area[0].set_value(question).run()
    _button(at, "提问").click().run()
    return at


def _answer_reply(text: str) -> httpx.Response:
    """打桩一条知识问答作答（模型输出 JSON）。"""
    import json

    return _ai_reply(json.dumps({"answer": text, "used_fragment_indexes": [1]}, ensure_ascii=False))


def test_ai_qa_shows_answer_without_passages(enable_ai):
    """恒开 AI：只展示回答，**不展示片段与来源**，页面上也没有 AI 开关。"""
    enable_ai(lambda request: _answer_reply("先看内存和整机重量，这两项每天都在影响体验。"))

    at = _ask_ai_qa(_run(), "笔记本多重适合带出门")
    _assert_clean(at)

    body = _all_text(at)
    assert "先看内存和整机重量" in body, "没有展示回答"
    assert "找到的资料" not in body, "按要求不再展示检索片段"
    assert "来源：" not in body and "更新于" not in body, "不应再出现来源引用"


def test_ai_qa_has_no_ai_toggle(enable_ai):
    """该页恒开 AI，不再提供开关。"""
    enable_ai(lambda request: _answer_reply("看内存。"))

    at = _run()
    _go_to_page(at, "AI 问答")
    _assert_clean(at)

    assert "启用 AI 增强" not in _all_text(at)
    assert len(at.toggle) == 0, "AI 问答页不应再有开关控件"


def test_ai_qa_without_key_explains_how_to_configure():
    """未配置密钥：说明怎么配（可行动），并给出走筛选的入口——不是报错。"""
    at = _ask_ai_qa(_run(), "笔记本多重适合带出门")
    _assert_clean(at)

    body = _all_text(at)
    assert "需要配置模型密钥" in body
    assert "ZHIGOU_LLM_API_KEY" in body, "要写清配置项名称"
    assert "智能分析" in body, "要给出去筛选的入口"
    assert "找到的资料" not in body


def test_ai_qa_falls_back_to_general_knowledge(enable_ai):
    """知识库没有资料时，用 AI 通用知识补答，并明确标注。"""
    enable_ai(
        lambda request: _ai_reply("先明确使用场景和预算，再比较重量、续航与售后。")
    )

    at = _ask_ai_qa(_run(), "今天天气怎么样")
    _assert_clean(at)

    body = _all_text(at)
    assert "先明确使用场景和预算" in body, "应展示通用知识回答"
    assert "通用知识" in body, "必须标注这不是知识库结论"
    assert "不是本项目知识库或商品数据" in body, "必须说明回答边界"


def test_ai_qa_reports_failure_without_partial_output(monkeypatch):
    """作答失败：说明失败并建议重试，不展示任何半成品。"""
    from src import ai_enhance, config
    from src.errors import UpstreamUnavailable

    monkeypatch.setenv(config.LLM_API_KEY_ENV, "sk-test-not-real")

    def _boom(*_args, **_kwargs):
        raise UpstreamUnavailable("模型服务暂时不可用。")

    monkeypatch.setattr(ai_enhance, "answer_from_knowledge", _boom)

    at = _ask_ai_qa(_run(), "笔记本多重适合带出门")
    _assert_clean(at)

    body = _all_text(at)
    assert "没能生成回答" in body
    assert "重试" in body, "要告诉用户可以怎么办"
    assert "找到的资料" not in body, "不应回退成片段展示"


def test_ai_qa_refuses_price_questions():
    """价格类问题不给问答答案，改为引导去筛选。"""
    at = _ask_ai_qa(_run(), "500 元以内有什么手机")
    _assert_clean(at)

    body = _all_text(at)
    assert "价格" in body and "筛选" in body
    assert "找到的资料" not in body


def test_ai_qa_guides_to_analysis_on_click():
    at = _ask_ai_qa(_run(), "预算 2000 的手机推荐")
    _button(at, "带着这个问题去筛选商品").click().run()
    _assert_clean(at)

    assert _state(at, "zg_current_page") == "智能分析"


def test_ai_qa_empty_input_is_rejected():
    at = _run()
    _go_to_page(at, "AI 问答")
    _button(at, "提问").click().run()
    _assert_clean(at)

    assert "请先输入" in _all_text(at)


def test_ai_qa_example_buttons_work(enable_ai):
    enable_ai(lambda request: _answer_reply("示例回答：先看内存与重量。"))

    at = _run()
    _go_to_page(at, "AI 问答")
    _button(at, "笔记本多重适合带出门").click().run()
    _assert_clean(at)

    assert "示例回答" in _all_text(at)

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
    at.text_area[0].set_value("预算 6000 买笔记本，主要编程，看重性能").run()
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
    at.text_area[0].set_value("预算 6000 买笔记本，主要编程").run()
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
    at.text_area[0].set_value("预算 2000 元的手机").run()
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
    at.text_area[0].set_value("预算 2000 元的手机").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    result = _state(at, "zg_result")
    assert result.over_budget_hidden == 0
    assert "没有列出" not in _all_text(at)


def test_truncation_is_disclosed(tmp_path, monkeypatch):
    """截断时说明还有多少件未列出。

    候选集**自造**并写进临时商品库，让应用真的读到它：截断只在候选数超过
    展示上限时才发生，而真实数据集每个类别恰好 10 件、上限也正好是 10——
    走真数据这条永远到不了截断，界面上那句「还有 N 件没有列出」也就
    从来不会被渲染出来验收。
    """
    from src import product_store

    db = tmp_path / "big.db"
    product_store.save_products(
        [p.model_dump() for p in _fake_laptops(config.MAX_OVER_BUDGET_SHOWN + 5)],
        path=db,
    )
    monkeypatch.setenv("ZHIGOU_PRODUCTS_DB_PATH", str(db))

    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("预算 100 元的笔记本电脑").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    result = _state(at, "zg_result")
    assert result.over_budget_hidden > 0
    body = _all_text(at)
    assert "没有列出" in body
    assert str(result.over_budget_hidden) in body
    assert "调高" in body, "要告诉用户怎么办"


def _fake_laptops(count: int) -> list:
    """一批自造笔记本电脑，价格 800 元起、每件递增 100 元。"""
    from src.data_loader import Product

    return [
        Product(
            id=f"FL{index:03d}",
            name=f"测试笔记本 {index}",
            category="laptop",
            price=800.0 + index * 100,
            brand="测试品牌",
            specs={
                "cpu_tier": 3, "ram_gb": 16, "battery_h": 8,
                "weight_kg": 1.4, "storage_gb": 512,
            },
            use_cases=["办公"],
            pros=["测试用"],
            cons=["测试用"],
            data_source="测试夹具 · 非真实数据",
            updated_at="2026-10-15",
        )
        for index in range(count)
    ]


def test_data_boundary_notice_is_visible_on_home():
    """首页要把数据边界说清楚——品牌是真的，价格与参数是整理的。"""
    at = _run()
    body = _all_text(at)
    assert "未核验" in body or "不是实时价格" in body


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
    for page in ("首页", "智能分析", "商品比较", "历史记录", "关于"):
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
        for page in ("首页", "智能分析", "商品比较", "历史记录", "个人设置", "关于"):
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

    assert "价格取向" in _all_text(at)
    assert "AI 增强模式" in _all_text(at)
    assert "品牌偏好" not in _all_text(at), "品牌偏好设置项已移除"
    assert "长期关注项" not in _all_text(at), "长期关注项设置项已移除"


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

    at.session_state["zg_pref_priority"] = "value"
    at.session_state["zg_pref_show_over"] = False
    at.run()
    _button(at, "保存设置").click().run()
    _assert_clean(at)

    from src import settings as _settings

    saved = _settings.load_preferences(DEFAULT_USER)
    assert saved.price_priority == "value", "价格取向没有保存成功"
    assert saved.show_over_budget is False

    _go_to_page(at, "首页")
    _go_to_page(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert _state(at, "zg_prefs_applied") is True
    assert "已自动带上" in _all_text(at)

    demand = _state(at, "zg_demand")
    assert "性价比" in demand.core_needs


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

    database.add_favorite(TEST_USERNAME, "GONE-9999")

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

    typed = "预算 2500，想买一台办公用的笔记本电脑"
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
        # 预算要能真的买到东西：真实数据里最便宜的笔记本 3519 元，
        # 填 3000 会让 AI 路径下的分析一件都推不出来，AI 那一段区块
        # 整个不渲染，下面一串断言集体失败在无关的地方。
        "budget": 6000,
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
    assert "AI 增强已开启" in _all_text(at)


def test_enabling_ai_shows_the_data_sharing_notice(enable_ai):
    """spec：调用外部服务前须说明发送的数据范围。"""
    enable_ai(lambda r: _ai_reply(_parse_payload()))

    at = _run()
    _go_to_page(at, "智能分析")
    _assert_clean(at)

    body = _all_text(at)
    assert "需求描述" in body, "要说明发送的数据范围"
    assert "发送给模型服务" in body


def test_ai_parse_is_used_when_enabled(enable_ai):
    seen: list = []

    def handler(request):
        seen.append(request)
        return _ai_reply(_parse_payload(category="phone", budget=4000, core_needs=["拍照"]))

    enable_ai(handler)

    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("想买台拍照好的手机，预算 4000").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert _state(at, "zg_parse_engine") == "ai", "没有走 AI 解析"
    demand = _state(at, "zg_demand")
    assert demand.category == "phone"
    assert demand.core_needs == ["拍照"]
    assert seen, "没有向模型发出请求"


def test_ai_failure_degrades_to_rules_with_a_notice(enable_ai):
    """spec：AI 调用失败时降级到本地规则模式，不崩溃，且告知用户。"""
    enable_ai(lambda r: httpx.Response(500, text="upstream boom"))

    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("预算 6000 买笔记本电脑，主要编程").run()
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
    at.text_area[0].set_value("预算 6000 买笔记本电脑").run()
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
    at.text_area[0].set_value("预算 6000 买笔记本，主要编程，看重性能").run()
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
    at.text_area[0].set_value("预算 6000 买笔记本，主要编程").run()
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
    at.text_area[0].set_value("预算 6000 买笔记本，主要编程").run()
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
    at.text_area[0].set_value("预算 6000 买笔记本，主要编程").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    from src import report_service

    report = _state(at, state.KEY_REPORT)
    assert report is not None
    assert "AI 解读" not in report_service.to_markdown(report)


# --------------------------------------------------------------------------
# 追溯表补缺：这几条 Scenario 之前只有手工验证，没有自动化断言
# --------------------------------------------------------------------------


def test_product_card_carries_the_data_source_label():
    """spec：商品卡片要显示数据来源标注与核验状态。

    **断言的是数据集里真实那句 `data_source`。** 这条用例早先找的是
    「演示数据」这个词，而它其实来自侧边栏的声明——卡片一个字都不渲染
    也照样通过，是一条假绿的断言。数据换成真实型号之后侧边栏那句改了，
    它才露出来。
    """
    at = _analyze_laptop(_run())
    _assert_clean(at)

    body = _all_text(at)
    assert "数据来源" in body
    assert "公开资料整理" in body, "卡片上没有渲染数据集里的来源标注"
    assert "未核验" in body
    assert "更新时间" in body


def test_reset_preferences_restores_defaults():
    """spec：恢复默认 —— 所有偏好回到初始状态并落盘。"""
    at = _run()
    _go_to_page(at, "个人设置")

    at.session_state["zg_pref_ai"] = False
    at.session_state["zg_pref_priority"] = "performance"
    at.run()
    _button(at, "保存设置").click().run()
    _assert_clean(at)

    from src import settings

    saved = settings.load_preferences(DEFAULT_USER)
    assert saved.ai_enhanced is False
    assert saved.price_priority == "performance"

    _button(at, "恢复默认").click().run()
    _assert_clean(at)

    restored = settings.load_preferences(DEFAULT_USER)
    assert restored.ai_enhanced is True, "恢复默认后 AI 增强没有回到默认开启"
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


# --------------------------------------------------------------------------
# 溯源信息在界面上的呈现（变更 migrate-products-to-sqlite）
# --------------------------------------------------------------------------


def test_product_card_shows_verification_status():
    """核验状态必须显眼——不标注的话，用户会把演示数据当成核实过的信息。"""
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("预算 5000 元，买一台办公用的笔记本电脑").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "未核验" in body, "演示数据必须标出未核验状态"
    assert "数据来源：" in body, "来源说明仍在"
    assert "更新时间：" in body


def test_demo_data_cards_are_never_marked_verified():
    """反向断言：自造数据**不能**被标成已核验。"""
    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("预算 5000 元，买一台办公用的笔记本电脑").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    assert "已核验" not in _all_text(at), "演示数据被标成了已核验"


def test_product_without_price_record_is_marked_as_missing(tmp_path, monkeypatch):
    """没有价格记录的商品标注为信息缺失，**不当成 0 或任何数值**。"""
    from src import product_store

    db = tmp_path / "products.db"
    product_store.save_products(
        [
            {
                "id": "NOPRICE1",
                "name": "没有价格的商品",
                "brand": "测试品牌",
                "category": "laptop",
                "specs": {"cpu_tier": 3},
                "use_cases": ["办公"],
                "pros": ["测试"],
                "cons": ["测试"],
                "data_source": "演示数据 · 测试夹具",
                "updated_at": "2026-01-01",
            }
        ],
        path=db,
    )
    monkeypatch.setenv("ZHIGOU_PRODUCTS_DB_PATH", str(db))

    at = _run()
    _go_to_page(at, "智能分析")
    at.text_area[0].set_value("预算 5000 元，买一台办公用的笔记本电脑").run()
    _button(at, "开始分析").click().run()
    _assert_clean(at)

    body = _all_text(at)
    assert "价格未知" in body, "没有价格记录时应标注为价格未知"


# --------------------------------------------------------------------------
# 登录、注册与访问边界
# --------------------------------------------------------------------------
#
# 这一组用例从**未登录**的会话起步（`_run(user=None)`），把登录页真的走一遍。
# 上面的页面回归测试都从已登录起步，两组分工明确：登录流程不会因为
# 「反正都会被跳过」而失去覆盖。


def _text_input(at: AppTest, label: str):
    """按标签取输入框。AppTest 没有按 label 查询的接口，和 `_button` 一个手法。"""
    for widget in at.text_input:
        if widget.label == label:
            return widget
    raise AssertionError(
        f"找不到输入框「{label}」，现有：{[w.label for w in at.text_input]}"
    )


def _sign_up(username: str, password: str) -> None:
    """直接建一个账号（不走界面），供登录用例使用。"""
    from src import accounts

    accounts.register(username, password)


def test_unauthenticated_visitor_lands_on_the_login_page():
    at = _run(user=None)
    _assert_clean(at)

    body = _all_text(at)
    assert "登录" in body
    assert "开始分析" not in body, "未登录不该看到任何功能页的内容"
    assert _state(at, state.KEY_USER) is None


def test_unauthenticated_visitor_triggers_no_data_query(monkeypatch):
    """spec：未登录不触发任何数据查询。

    直接把取数据集的那一步换成「一调用就炸」，这样「查没查」是断言出来的，
    而不是靠读代码推断的。
    """
    from src.ui import state as state_module

    def explode(*_args, **_kwargs):
        raise AssertionError("未登录时不该去取数据集")

    monkeypatch.setattr(state_module, "get_catalog", explode)
    monkeypatch.setattr(state_module, "get_knowledge_index", explode)

    at = _run(user=None)
    _assert_clean(at)


def test_login_with_correct_credentials_enters_the_app():
    _sign_up("lisi", "good-pass-1")

    at = _run(user=None)
    _text_input(at, "用户名").set_value("lisi")
    _text_input(at, "密码").set_value("good-pass-1")
    _button(at, "登录").click().run()

    _assert_clean(at)
    assert _state(at, state.KEY_USER).username == "lisi"
    assert "开始分析" in _all_text(at), "登录后应当进入首页"


def test_failed_login_does_not_reveal_which_part_was_wrong():
    """两种失败在界面上必须完全一样——否则等于提供了枚举用户名的办法。"""
    _sign_up("lisi", "good-pass-1")

    at = _run(user=None)
    _text_input(at, "用户名").set_value("nobody")
    _text_input(at, "密码").set_value("good-pass-1")
    _button(at, "登录").click().run()
    unknown_user_body = _all_text(at)

    at = _run(user=None)
    _text_input(at, "用户名").set_value("lisi")
    _text_input(at, "密码").set_value("wrong-pass-1")
    _button(at, "登录").click().run()
    wrong_password_body = _all_text(at)

    assert "用户名或密码不正确" in unknown_user_body
    assert "用户名或密码不正确" in wrong_password_body
    assert "不存在" not in unknown_user_body, "不能透露用户名是否存在"
    assert "不存在" not in wrong_password_body


def test_disabled_account_cannot_log_in():
    _sign_up("lisi", "good-pass-1")
    from src import database
    from src.auth import ROLE_ADMIN, User

    # 停用是管理员操作，所以这里要装作管理员来调（守卫只看传入的对象）。
    database.set_user_active(
        "lisi", False, viewer=User(username="root", role=ROLE_ADMIN)
    )

    at = _run(user=None)
    _text_input(at, "用户名").set_value("lisi")
    _text_input(at, "密码").set_value("good-pass-1")
    _button(at, "登录").click().run()

    assert _state(at, state.KEY_USER) is None
    assert "用户名或密码不正确" in _all_text(at)


def test_registration_from_the_ui_creates_a_regular_user():
    at = _run(user=None)
    _button(at, "没有账号？注册一个").click().run()

    _text_input(at, "用户名").set_value("newcomer")
    _text_input(at, "密码").set_value("good-pass-1")
    _text_input(at, "确认密码").set_value("good-pass-1")
    _button(at, "注册").click().run()
    _assert_clean(at)

    from src import database

    created = database.get_user("newcomer")
    assert created is not None
    assert created.role == "user", "自助注册只能是普通用户"
    assert "注册成功" in _all_text(at)


def test_registration_refuses_mismatched_passwords():
    at = _run(user=None)
    _button(at, "没有账号？注册一个").click().run()

    _text_input(at, "用户名").set_value("newcomer")
    _text_input(at, "密码").set_value("good-pass-1")
    _text_input(at, "确认密码").set_value("good-pass-2")
    _button(at, "注册").click().run()

    from src import database

    assert database.get_user("newcomer") is None, "两次密码不一致不该建号"
    assert "不一致" in _all_text(at)


def test_registration_refuses_a_short_password():
    at = _run(user=None)
    _button(at, "没有账号？注册一个").click().run()

    _text_input(at, "用户名").set_value("newcomer")
    _text_input(at, "密码").set_value("short")
    _text_input(at, "确认密码").set_value("short")
    _button(at, "注册").click().run()

    from src import database

    assert database.get_user("newcomer") is None


def test_the_login_page_stays_clean():
    """界面保持简洁：登录页只保留必要信息与一行会话说明。

    详细的能力边界移到 `docs/auth-boundary.md`，不在界面上铺开。
    """
    at = _run(user=None)
    body = _all_text(at)

    assert "登录" in body
    assert "刷新页面需重新登录" in body, "spec 要求刷新需重新登录有界面说明"
    for noise in ("演示级鉴权", "没有会话过期", "没有 CSRF 防护", "账号体系"):
        assert noise not in body, f"登录页不应再铺开「{noise}」长文"


def test_signing_out_returns_to_the_login_page_and_clears_the_session():
    """spec：登出清空会话并回到登录页。

    **整个会话**都要清掉，不只是当前用户——上一个用户的推荐结果、
    完整报告、比较选择都还在内存里，换个账号登录就会看到上一个人的东西。
    """
    at = _run()
    assert _state(at, state.KEY_USER) is not None

    _button(at, "登出").click().run()
    _assert_clean(at)

    assert _state(at, state.KEY_USER) is None
    assert "登录" in _all_text(at)
    assert "开始分析" not in _all_text(at)


def test_sidebar_shows_the_current_account():
    at = _run()
    body = _all_text(at)

    assert TEST_USERNAME in body
    assert "普通用户" in body


# --------------------------------------------------------------------------
# 管理员页面：用户管理与全站概览
# --------------------------------------------------------------------------


def _selectbox(at: AppTest, label: str):
    for widget in at.selectbox:
        if widget.label == label:
            return widget
    raise AssertionError(
        f"找不到下拉框「{label}」，现有：{[w.label for w in at.selectbox]}"
    )


def test_regular_user_does_not_see_the_admin_entries():
    at = _run()
    _go_to_page(at, "首页")

    labels = [button.label for button in at.button]
    assert "用户管理" not in labels
    assert "全站概览" not in labels
    assert "知识库管理" not in labels


def test_admin_sees_the_admin_entries():
    at = _run(user=ADMIN_USER)
    _go_to_page(at, "首页")

    labels = [button.label for button in at.button]
    assert "用户管理" in labels
    assert "全站概览" in labels
    assert "知识库管理" in labels


def test_jumping_straight_to_an_admin_page_is_refused():
    """**界面隐藏不算权限。**

    普通用户点不到「用户管理」，但页面名只是 `session_state` 里的一个值——
    把它改成「用户管理」就能让应用跳到那个页面函数。这条用例就是那么干的，
    断言的是它被挡住。
    """
    at = _run()
    at.session_state[state.KEY_PAGE] = "用户管理"
    at.run()
    _assert_clean(at)

    assert "没有执行该操作的权限" in _all_text(at)


def test_user_management_page_has_no_create_form():
    """建号只在注册页——用户管理页**不再提供「新建账号」**。

    这与 `user-auth`「管理员 SHALL 能够创建账号」那句相反，所以本变更的 delta
    把那句话也去掉了。理由：注册本来就是开放的，管理员自己建号是个重复入口；
    而要造一个管理员，让对方向注册、再回到这里改角色即可。
    """
    at = _run(user=ADMIN_USER)
    _go_to_page(at, "用户管理")
    _assert_clean(at)

    body = _all_text(at)
    assert "新建账号" not in body
    assert not any("创建" in button.label for button in at.button)
    assert "自助注册" in body, "要去掉入口，就得说清新账号从哪来"


def test_admin_page_offers_a_delete_entry_for_others_but_not_for_you():
    """账号删除入口：别人有，自己那一行没有。

    这条用例**替换**了原先的 `test_admin_page_offers_no_way_to_delete_an_account`
    ——那条断言的是「页面上不得出现带『删除』字样的按钮」，
    而变更 `add-record-and-user-deletion` 恰好推翻了它（级联删除 + 禁删自己）。
    """
    from src import database

    database.create_user("lisi", "good-pass-1")
    at = _run(user=ADMIN_USER)
    _go_to_page(at, "用户管理")
    _assert_clean(at)

    labels = [button.label for button in at.button]
    assert labels.count("删除账号") == 1, (
        "只有 lisi 那一行该有删除入口；管理员自己那一行不该有"
    )
    assert "不能删除自己" in _all_text(at), "不渲染入口的同时要说明原因"


def test_the_delete_confirmation_states_how_much_data_goes(report):
    """确认文案必须写出**具体条数**——破坏性要看得见，不能只说「确定吗」。"""
    from src import database

    database.create_user("lisi", "good-pass-1")
    database.save_analysis(report, user_id="lisi")
    database.add_favorite("lisi", "LP001")

    at = _run(user=ADMIN_USER)
    _go_to_page(at, "用户管理")
    _assert_clean(at)

    assert "连同 1 条历史与 1 条收藏" in _all_text(at)


def test_admin_deletes_an_account_and_its_data(report):
    from src import database

    database.create_user("lisi", "good-pass-1")
    database.save_analysis(report, user_id="lisi")

    at = _run(user=ADMIN_USER)
    _go_to_page(at, "用户管理")
    at.checkbox("zg_admin_del_ok_lisi").set_value(True).run()
    _button(at, "删除账号").click().run()
    _assert_clean(at)

    assert database.get_user("lisi") is None
    assert database.list_analyses_of("lisi") == [], "数据要跟着账号一起没"
    assert "已删除账号" in _all_text(at)


def test_deleting_an_account_without_confirmation_is_refused():
    from src import database

    database.create_user("lisi", "good-pass-1")

    at = _run(user=ADMIN_USER)
    _go_to_page(at, "用户管理")
    _button(at, "删除账号").click().run()
    _assert_clean(at)

    assert database.get_user("lisi") is not None, "未勾选确认不该删掉"
    assert "请先勾选确认" in _all_text(at)


def test_deleting_the_other_admin_from_the_ui_is_allowed():
    """删除路径上的「最后一个管理员」守卫，在界面上**不可达**。

    原因：操作者本身必然是一个**活跃**的管理员（会话校验保证了会话里的对象
    与库一致），所以目标账号不可能是「最后一个可用管理员」。
    守卫仍然写在数据层——它防的是「会话里的对象与库不一致」那种情形
    （伪造或过期的 viewer），那条路只能在数据层直调时走到，
    用例在 `test_accounts.test_the_last_admin_cannot_be_deleted`。

    这条用例把这个结论钉下来：以后有人以为界面上能测到那个守卫，会先看到这里。
    """
    from src import database

    database.create_user(ADMIN_USERNAME, "fixture-pass-1", role="admin")
    other = User(username="root2", role=ROLE_ADMIN)

    at = _run(user=other)
    _go_to_page(at, "用户管理")
    at.checkbox(f"zg_admin_del_ok_{ADMIN_USERNAME}").set_value(True).run()
    _button(at, "删除账号").click().run()
    _assert_clean(at)

    assert database.get_user(ADMIN_USERNAME) is None
    assert database.count_active_admins() == 1


# --------------------------------------------------------------------------
# 记录删除与会话校验
# --------------------------------------------------------------------------


def test_deleting_a_history_record_from_the_ui(report):
    from src import database

    database.save_analysis(report, user_id=TEST_USERNAME)
    entry_id = database.list_analyses_of(TEST_USERNAME)[0].id

    at = _run()
    _go_to_page(at, "历史记录")
    _assert_clean(at)

    at.checkbox(f"del_ok_{entry_id}").set_value(True).run()
    _button(at, "删除").click().run()
    _assert_clean(at)

    assert database.list_analyses_of(TEST_USERNAME) == []
    assert "已删除" in _all_text(at)


def test_deleting_a_history_record_without_confirmation_is_refused(report):
    """未勾选确认时点删除：**只提示、不删**。

    没有把按钮置灰，因为灰按钮看起来像坏了；「点了没反应但告诉你为什么」
    至少把规则说清楚了。
    """
    from src import database

    database.save_analysis(report, user_id=TEST_USERNAME)

    at = _run()
    _go_to_page(at, "历史记录")
    _button(at, "删除").click().run()
    _assert_clean(at)

    assert len(database.list_analyses_of(TEST_USERNAME)) == 1, "不该删掉"
    assert "请先勾选" in _all_text(at)


def test_admin_deletes_a_record_from_the_overview(report):
    from src import database

    database.save_analysis(report, user_id="someone")
    entry_id = database.list_analyses_of("someone")[0].id

    at = _run(user=ADMIN_USER)
    _go_to_page(at, "全站概览")
    _assert_clean(at)

    at.checkbox(f"ov_del_ok_{entry_id}").set_value(True).run()
    at.button(f"ov_del_{entry_id}").click().run()
    _assert_clean(at)

    assert database.list_analyses_of("someone") == []


def test_a_disabled_account_loses_its_session():
    """spec：账号被停用后，其会话在**下一次交互**时失效。"""
    from src import database

    at = _run()
    assert _state(at, state.KEY_USER) is not None

    database.set_user_active(
        TEST_USERNAME, False, viewer=User(username="root", role=ROLE_ADMIN)
    )
    at.run()  # 下一次交互

    assert _state(at, state.KEY_USER) is None
    assert "已被停用或删除" in _all_text(at)
    assert "开始分析" not in _all_text(at), "不该还能进功能页"


def test_a_deleted_account_loses_its_session():
    from src import database

    at = _run()
    database.delete_user(
        TEST_USERNAME, viewer=User(username="root", role=ROLE_ADMIN)
    )
    at.run()

    assert _state(at, state.KEY_USER) is None
    assert "已被停用或删除" in _all_text(at)


def test_admin_can_change_a_role_and_reset_a_password():
    from src import accounts, database

    database.create_user("lisi", "good-pass-1")
    at = _run(user=ADMIN_USER)
    _go_to_page(at, "用户管理")

    _selectbox(at, "修改角色").set_value("admin").run()
    _button(at, "保存角色").click().run()
    _assert_clean(at)
    assert database.get_user("lisi").role == "admin"

    _text_input(at, "重置密码").set_value("brand-new-pass-1")
    _button(at, "重置密码").click().run()
    _assert_clean(at)
    assert accounts.authenticate("lisi", "brand-new-pass-1").username == "lisi"


def test_admin_can_disable_an_account():
    from src import database

    database.create_user("lisi", "good-pass-1")
    at = _run(user=ADMIN_USER)
    _go_to_page(at, "用户管理")

    _button(at, "停用账号").click().run()
    _assert_clean(at)

    assert database.get_user("lisi").is_active is False
    assert "已停用" in _all_text(at)


def test_the_last_admin_cannot_be_demoted_through_the_ui():
    """spec：不能把最后一个管理员降级——系统必须始终保有一个可用管理员。"""
    from src import database

    database.create_user(ADMIN_USER.username, "good-pass-1", role="admin")
    at = _run(user=ADMIN_USER)
    _go_to_page(at, "用户管理")

    _selectbox(at, "修改角色").set_value("user").run()
    _button(at, "保存角色").click().run()
    _assert_clean(at)

    # 断言的是**被拒绝那句话**，不是「至少保留一个管理员」——
    # 后者在页面的静态说明里就有，拿它做断言等于没测。
    assert "该操作已被拒绝" in _all_text(at)
    assert database.get_user(ADMIN_USER.username).role == "admin"


def test_the_last_admin_cannot_be_disabled_through_the_ui():
    from src import database

    database.create_user(ADMIN_USER.username, "good-pass-1", role="admin")
    at = _run(user=ADMIN_USER)
    _go_to_page(at, "用户管理")

    _button(at, "停用账号").click().run()
    _assert_clean(at)

    assert database.get_user(ADMIN_USER.username).is_active is True


def test_overview_lists_every_users_records_and_flags_legacy_ones(report):
    """spec：管理员的全站概览列出所有用户的分析记录及其归属用户。

    无归属的遗留记录要**单独标注**，不能混进某个账号那一栏。
    """
    from src import database

    database.save_analysis(report, user_id=TEST_USERNAME)
    database.save_analysis(report, user_id="someone-else")
    database.save_analysis(report)  # 单用户时期的遗留记录

    at = _run(user=ADMIN_USER)
    _go_to_page(at, "全站概览")
    _assert_clean(at)

    body = _all_text(at)
    assert TEST_USERNAME in body
    assert "someone-else" in body
    assert "无归属" in body, "遗留记录必须标注出来"
    assert "3 条" in body, "总数应包含无归属的记录"


def test_overview_is_refused_for_a_regular_user():
    at = _run()
    at.session_state[state.KEY_PAGE] = "全站概览"
    at.run()
    _assert_clean(at)

    assert "没有执行该操作的权限" in _all_text(at)


# --------------------------------------------------------------------------
# 管理员页面：商品维护（三个分块）
# --------------------------------------------------------------------------


def _widget(at: AppTest, kind: str, key: str):
    """按 **key** 取控件。

    商品维护页里同一个标签会出现二十多次（每件商品一个「名称」输入框），
    按标签找只能拿到第一个。`WidgetList` 支持按 key 取，用它。
    """
    return getattr(at, kind)(key)


def _open_catalog_page(at: AppTest) -> AppTest:
    _go_to_page(at, "商品维护")
    _assert_clean(at)
    return at


def test_catalog_page_offers_three_blocks():
    at = _open_catalog_page(_run(user=ADMIN_USER))
    body = _all_text(at)

    for label in ("分类", "品牌", "商品管理", "详情与参数"):
        assert label in [tab.label for tab in at.tabs], f"缺少「{label}」标签页"
    assert "新增商品" in body


def test_regular_user_cannot_open_the_catalog_page():
    at = _run()
    at.session_state[state.KEY_PAGE] = "商品维护"
    at.run()
    _assert_clean(at)

    assert "没有执行该操作的权限" in _all_text(at)


def test_admin_adds_a_product_through_the_ui():
    at = _open_catalog_page(_run(user=ADMIN_USER))

    _widget(at, "text_input", "zg_cat_new_id").set_value("UI-NEW-001")
    _widget(at, "text_input", "zg_cat_new_name").set_value("界面录入的笔记本")
    _widget(at, "text_input", "zg_cat_new_brand").set_value("测试品牌")
    _widget(at, "text_input", "zg_cat_new_model").set_value("T-1")
    _widget(at, "number_input", "zg_cat_new_price").set_value(5200.0)
    _widget(at, "text_input", "zg_cat_new_image").set_value("https://example.com/a.jpg")
    _widget(at, "text_area", "zg_cat_new_specs").set_value("cpu_tier: 3\nram_gb: 16")
    _widget(at, "text_area", "zg_cat_new_use_cases").set_value("办公")
    _widget(at, "text_area", "zg_cat_new_pros").set_value("轻便")
    _widget(at, "text_area", "zg_cat_new_cons").set_value("接口少")
    _button(at, "新增").click().run()
    _assert_clean(at)

    from src.data_loader import load_catalog

    created = load_catalog().get("UI-NEW-001")
    assert created is not None, "新增的商品应当立刻出现在数据集里"
    assert created.data_status == "unverified"
    assert created.entered_by == ADMIN_USERNAME
    assert "未核验" in _all_text(at)


def test_admin_adds_a_product_with_an_invalid_image_and_it_is_refused():
    at = _open_catalog_page(_run(user=ADMIN_USER))

    _widget(at, "text_input", "zg_cat_new_id").set_value("UI-BAD-001")
    _widget(at, "text_input", "zg_cat_new_name").set_value("图片地址非法的商品")
    _widget(at, "text_input", "zg_cat_new_brand").set_value("测试品牌")
    _widget(at, "number_input", "zg_cat_new_price").set_value(3000.0)
    _widget(at, "text_input", "zg_cat_new_image").set_value("javascript:alert(1)")
    _widget(at, "text_area", "zg_cat_new_specs").set_value("cpu_tier: 3")
    _widget(at, "text_area", "zg_cat_new_use_cases").set_value("办公")
    _widget(at, "text_area", "zg_cat_new_pros").set_value("轻便")
    _widget(at, "text_area", "zg_cat_new_cons").set_value("接口少")
    _button(at, "新增").click().run()
    _assert_clean(at)

    from src.data_loader import load_catalog

    assert load_catalog().get("UI-BAD-001") is None, "非法图片地址不该写进库"
    assert "http://" in _all_text(at), "应当给出中文说明"


def test_admin_adds_a_product_with_an_unknown_spec_and_it_is_refused():
    at = _open_catalog_page(_run(user=ADMIN_USER))

    _widget(at, "text_input", "zg_cat_new_id").set_value("UI-BAD-002")
    _widget(at, "text_input", "zg_cat_new_name").set_value("参数名写错的商品")
    _widget(at, "text_input", "zg_cat_new_brand").set_value("测试品牌")
    _widget(at, "number_input", "zg_cat_new_price").set_value(3000.0)
    _widget(at, "text_area", "zg_cat_new_specs").set_value("cpu_tierr: 3")
    _widget(at, "text_area", "zg_cat_new_use_cases").set_value("办公")
    _widget(at, "text_area", "zg_cat_new_pros").set_value("轻便")
    _widget(at, "text_area", "zg_cat_new_cons").set_value("接口少")
    _button(at, "新增").click().run()
    _assert_clean(at)

    from src.data_loader import load_catalog

    assert load_catalog().get("UI-BAD-002") is None
    assert "不属于该分类" in _all_text(at)


def test_admin_can_disable_a_product_from_the_ui():
    at = _open_catalog_page(_run(user=ADMIN_USER))
    product_id = "LP001"

    at.button(f"zg_cat_active_{product_id}").click().run()
    _assert_clean(at)

    from src.data_loader import load_catalog

    assert load_catalog().get(product_id).is_active is False
    assert "已停用" in _all_text(at)


def test_admin_renames_a_category_and_product_records_are_untouched():
    at = _open_catalog_page(_run(user=ADMIN_USER))

    from src import product_store

    before = [
        (record["id"], record["category"])
        for record in product_store.load_product_records()
    ]

    _widget(at, "text_input", "zg_cat_label_laptop").set_value("笔记本·精选")
    _button(at, "保存分类").click().run()
    _assert_clean(at)

    from src import catalog_meta

    entry = next(
        item for item in catalog_meta.category_entries() if item.key == "laptop"
    )
    assert entry.label == "笔记本·精选", "展示名没有落到库里"
    assert "笔记本·精选" in _all_text(at)

    after = [
        (record["id"], record["category"])
        for record in product_store.load_product_records()
    ]
    assert before == after, "改展示名不该动商品记录"


def test_catalog_page_offers_adding_categories_and_brands():
    """分类与品牌都可以在界面上新增。"""
    at = _open_catalog_page(_run(user=ADMIN_USER))
    body = _all_text(at)

    assert "新增分类" in body
    assert "新增品牌" in body
    assert "默认权重" in body
    assert "停用不等于删除" in body


def test_admin_adds_a_category_and_a_brand_through_the_ui():
    from src import catalog_meta, config

    # 新增分类会把键并入内存里的 CATEGORY_LABELS（进程级），
    # 用例结束必须还原，否则后续「分类集合」断言全部被污染。
    snapshot = dict(config.CATEGORY_LABELS)
    try:
        at = _open_catalog_page(_run(user=ADMIN_USER))

        # 新增分类
        at.text_input("zg_cat_newcat_key").set_value("tablet")
        at.text_input("zg_cat_newcat_label").set_value("平板电脑")
        _button(at, "新增分类").click().run()
        _assert_clean(at)
        assert "tablet" in [entry.key for entry in catalog_meta.category_entries()]

        # 新增品牌（没有商品也能登记）
        at.text_input("zg_cat_newbrand_name").set_value("测试品牌")
        at.text_input("zg_cat_newbrand_display").set_value("测试品牌")
        _button(at, "新增品牌").click().run()
        _assert_clean(at)
        assert "测试品牌" in [entry.brand_name for entry in catalog_meta.brand_entries()]
    finally:
        config.CATEGORY_LABELS.clear()
        config.CATEGORY_LABELS.update(snapshot)


def test_brand_block_explains_that_registering_a_brand_does_not_teach_the_parser():
    """界面上要写明：登记一个商品库里没有的品牌**不会**让解析器认识它。

    不写清楚的话，管理员登记完发现「分析里还是识别不出这个品牌」，
    会当成 bug 反复试。
    """
    at = _open_catalog_page(_run(user=ADMIN_USER))
    body = _all_text(at)

    assert "让需求解析认识它" in body
    assert "解析仍以商品数据为准" in body


# --------------------------------------------------------------------------
# 分析页的表单精简与品牌级联（simplify-analysis-form 的界面用例）
# --------------------------------------------------------------------------


def _brand_options(at: AppTest) -> list[str]:
    from src.ui.pages.analysis import _BRAND_KEY

    return list(at.selectbox(_BRAND_KEY).proto.options)


def test_brand_control_only_appears_after_a_category_is_chosen(catalog):
    """spec：品牌控件在选定商品类别后才出现。

    不级联的话，用户能选出「类别里不存在的品牌」，筛选结果必然是空集，
    而界面不会告诉他为什么。
    """
    from src import config
    from src.ui.pages.analysis import _BRAND_KEY, _CATEGORY_KEY, _NO_BRAND

    at = _run()
    _go_to_page(at, "智能分析")
    _assert_clean(at)

    assert _BRAND_KEY not in [widget.key for widget in at.selectbox], (
        "未选类别时不该渲染品牌控件"
    )

    at.selectbox(_CATEGORY_KEY).set_value(config.CATEGORY_LABELS["laptop"]).run()
    _assert_clean(at)

    options = _brand_options(at)
    assert options[0] == _NO_BRAND, "第一个选项应当是「不限品牌」"
    assert set(options[1:]) == {
        product.brand for product in catalog.by_category("laptop") if product.brand
    }


def test_brand_options_follow_the_category_and_reset_on_switch(catalog):
    """spec：切换类别后品牌选项变为该类别下的品牌，之前选的品牌被清空。"""
    from src import config
    from src.ui.pages.analysis import _BRAND_KEY, _CATEGORY_KEY, _NO_BRAND

    at = _run()
    _go_to_page(at, "智能分析")

    at.selectbox(_CATEGORY_KEY).set_value(config.CATEGORY_LABELS["laptop"]).run()
    chosen = _brand_options(at)[1]
    at.selectbox(_BRAND_KEY).set_value(chosen).run()
    assert at.selectbox(_BRAND_KEY).value == chosen

    at.selectbox(_CATEGORY_KEY).set_value(config.CATEGORY_LABELS["phone"]).run()
    _assert_clean(at)

    options = _brand_options(at)
    assert set(options[1:]) == {
        product.brand for product in catalog.by_category("phone") if product.brand
    }
    assert at.selectbox(_BRAND_KEY).value == _NO_BRAND, (
        "换了类别之后，上一个类别的品牌必须被清空——留着它会让筛选结果为空"
    )


def test_ai_qa_respects_the_global_switch_being_off():
    """spec：全局关闭时，问答页说明「AI 增强已在个人设置中关闭」。

    与「未配置密钥」是两回事：前者去设置打开即可，后者要先配密钥。
    两种情况的提示必须分得开，否则用户会去错地方。
    """
    from src import settings
    from src.settings import UserPreferences

    settings.save_preferences(DEFAULT_USER, UserPreferences(ai_enhanced=False))

    at = _ask_ai_qa(_run(), "笔记本多重适合带出门")
    _assert_clean(at)

    body = _all_text(at)
    assert "个人设置" in body and "关闭" in body
    assert "需要配置模型密钥" not in body, "开关关掉不是「没配密钥」，别混为一谈"
    assert "找到的资料" not in body


def test_the_analysis_form_has_no_usage_or_priority_controls():
    """spec：页面上不存在「主要用途」「比较看重」控件——它们在描述里写。"""
    at = _run()
    _go_to_page(at, "智能分析")
    _assert_clean(at)

    body = _all_text(at)
    assert "主要用途" not in body
    assert "比较看重" not in body
    assert "商品类别" in body, "类别与预算仍在"
    assert "预算（元）" in body


def test_mode_label_covers_all_three_states(monkeypatch):
    """spec：界面明确显示三种状态之一——本地演示模式 / 本地模式 / AI 增强模式。

    三种状态的区别对用户是实在的：「没配密钥」要去配，「开关关了」去设置里
    打开就行。混成一句「当前不在 AI 模式」，用户不知道该做什么。

    断言用的是三种状态**各自的说明文案**，不是模式名——「本地模式」是
    「本地演示模式」的子串，拿模式名断言会互相满足，等于没测。
    走界面而不是直接调 `current_mode()`：那个函数读的是**当前登录用户**的
    偏好，裸调时没有会话，取到的是默认值。
    """
    from src import config, settings
    from src.settings import UserPreferences

    monkeypatch.delenv(config.LLM_API_KEY_ENV, raising=False)
    assert "未配置模型密钥" in _all_text(_run())

    monkeypatch.setenv(config.LLM_API_KEY_ENV, "sk-test-not-real")
    settings.save_preferences(DEFAULT_USER, UserPreferences(ai_enhanced=False))
    assert "AI 增强已在个人设置中关闭" in _all_text(_run())

    settings.save_preferences(DEFAULT_USER, UserPreferences(ai_enhanced=True))
    assert "已接入模型" in _all_text(_run())
