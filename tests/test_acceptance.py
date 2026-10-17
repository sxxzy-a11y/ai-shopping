"""端到端验收测试。

对应简报「八、测试与验收标准」列出的场景，以及任务组 9 的六项验收。
这里测的是**整条链路**在异常情况下的表现：不崩、有中文提示、不泄露堆栈。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config
from src.auth import ROLE_USER, User
from src.ui import state

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_FILE = str(PROJECT_ROOT / "app.py")

FALLBACK_TEXT = "操作未能完成，请稍后重试"

#: 端到端默认从一个**已登录**的会话起步：这里测的是整条决策链路，
#: 登录本身有自己的用例。未登录时的行为另有一条专门用例。
TEST_USERNAME = "acceptance-tester"
DEFAULT_USER = User(username=TEST_USERNAME, role=ROLE_USER)

#: 界面上**绝不允许**出现的东西
FORBIDDEN = ("Traceback", "File \"", "line ", "streamlit.errors", "sqlite3.", "httpx.")


#: 端到端用的需求句。**预算跟着真实价格上涨过**：需求简报里的原句是
#: 「预算 3000 元」，而真实数据里最便宜的笔记本要 3519 元——照抄那个数字，
#: 分析结果会一件都进不了预算内，「为你推荐」整块都渲染不出来，
#: 下面一串断言会集体失败，而失败信息看着像页面坏了。
EXAMPLE_TEXT = (
    "我是一名大学生，预算 6000 元，想买一台主要用于 Python 编程、"
    "日常学习和偶尔玩游戏的笔记本电脑。我比较看重性能和性价比，"
    "不希望电脑太重。"
)


def _ensure_account(user: User) -> None:
    """会话里那个账号必须在库里真的存在且启用。

    应用每轮会查库校验会话账号（被停用/被删除的账号要让其会话失效），
    所以夹具不能只往 `session_state` 里塞一个用户对象——那样会被当成
    「幽灵账号」踢回登录页。
    """
    from src import database
    from src.errors import ZhigouError

    try:
        if database.get_user(user.username) is None:
            database.create_user(user.username, "fixture-pass-1", role=user.role)
    except ZhigouError:
        # 库坏了（那几条「损坏的库不该让应用停摆」的用例会先把库弄坏）——
        # 跳过建号即可，应用侧对读库失败是 fail-open，不会因此踢掉会话。
        return


def _run(user: User | None = DEFAULT_USER) -> AppTest:
    at = AppTest.from_file(APP_FILE, default_timeout=60)
    if user is not None:
        _ensure_account(user)
        at.session_state[state.KEY_USER] = user
    at.run()
    return at


def _button(at: AppTest, label: str):
    for button in at.button:
        if button.label == label:
            return button
    raise AssertionError(f"找不到按钮「{label}」，现有：{[b.label for b in at.button]}")


def _go(at: AppTest, page: str) -> None:
    _button(at, page).click().run()


def _state(at: AppTest, key: str, default=None):
    """AppTest 的 session_state 不支持 `.get()`，这里补一个。"""
    try:
        return at.session_state[key]
    except (KeyError, AttributeError):
        return default


def _text(at: AppTest) -> str:
    """页面上所有可见文本（含控件标签）。"""
    chunks: list[str] = []
    for attr in ("markdown", "caption", "title", "header", "subheader", "text",
                 "info", "warning", "error", "success"):
        for element in getattr(at, attr, []):
            chunks.append(str(getattr(element, "value", "")))
    # `expander` 也要收：折叠面板的标题是页面上可见的文本，漏掉它会让
    # 「某某确实显示了」这类断言取不到东西（见 test_app._all_text 的说明）。
    for attr in ("selectbox", "multiselect", "text_input", "text_area", "toggle",
                 "radio", "checkbox", "button", "number_input", "expander"):
        for element in getattr(at, attr, []):
            label = getattr(element, "label", "")
            if label:
                chunks.append(str(label))
    import re

    return re.sub(r"<style>.*?</style>", "", "\n".join(chunks), flags=re.DOTALL)


def _assert_no_leak(at: AppTest, where: str) -> None:
    """没有未捕获异常，也没有任何内部细节漏到界面上。"""
    assert not at.exception, f"{where}：抛出未捕获异常 {[e.value for e in at.exception]}"

    body = _text(at)
    assert FALLBACK_TEXT not in body, f"{where}：出现兜底错误提示"
    for token in FORBIDDEN:
        assert token not in body, f"{where}：界面上出现了内部细节「{token}」"


# --------------------------------------------------------------------------
# 验收 1：用户没有输入需求
# --------------------------------------------------------------------------


def test_empty_input_is_rejected_with_a_chinese_hint():
    at = _run()
    _go(at, "智能分析")
    _button(at, "开始分析").click().run()

    _assert_no_leak(at, "空输入")
    assert "请先描述你的购买需求" in _text(at)
    assert _state(at, "zg_result") is None


# --------------------------------------------------------------------------
# 验收 2：预算为空 / 负数 / 格式错误
# --------------------------------------------------------------------------


def test_empty_budget_is_allowed_and_prompts_a_follow_up():
    at = _run()
    _go(at, "智能分析")
    at.text_area[0].set_value("想买台笔记本").run()
    _button(at, "开始分析").click().run()

    _assert_no_leak(at, "预算为空")
    assert "还需要一点信息" in _text(at)
    assert "预算" in _text(at)


def test_negative_budget_is_rejected():
    at = _run()
    _go(at, "智能分析")
    at.text_input[0].set_value("-100").run()
    _button(at, "开始分析").click().run()

    _assert_no_leak(at, "负数预算")
    assert "大于 0" in _text(at)


def test_malformed_budget_is_rejected_with_an_example():
    at = _run()
    _go(at, "智能分析")
    at.text_input[0].set_value("三千块").run()
    _button(at, "开始分析").click().run()

    _assert_no_leak(at, "格式错误预算")
    body = _text(at)
    assert "格式不正确" in body
    assert "3000" in body, "报错时应给出正确填写示例"


# --------------------------------------------------------------------------
# 验收 3：商品数据文件缺失或为空
# --------------------------------------------------------------------------


def test_missing_seed_shows_a_hint_and_keeps_the_app_alive(tmp_path, monkeypatch):
    """库为空且种子文件也不在——这时应用仍要能打开，并说清缺什么。

    商品数据入数据库后，这个场景的意思变成了「没有任何来源能初始化商品库」：
    conftest 给的是空库，种子又被指到了不存在的位置。
    """
    monkeypatch.setenv("ZHIGOU_PRODUCTS_PATH", str(tmp_path / "nope.json"))

    at = _run()
    _assert_no_leak(at, "商品数据缺失")

    body = _text(at)
    assert "商品" in body and ("找不到" in body or "为空" in body or "缺失" in body)
    assert "products.json" in body, "应告知期望的种子文件路径"


def test_corrupt_product_file_shows_a_hint(tmp_path, monkeypatch):
    bad = tmp_path / "products.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setenv("ZHIGOU_PRODUCTS_PATH", str(bad))

    at = _run()
    _assert_no_leak(at, "数据文件非法")

    assert "JSON" in _text(at)


def test_empty_product_catalog_shows_a_hint(tmp_path, monkeypatch):
    empty = tmp_path / "products.json"
    empty.write_text(json.dumps({"products": []}), encoding="utf-8")
    monkeypatch.setenv("ZHIGOU_PRODUCTS_PATH", str(empty))

    at = _run()
    _assert_no_leak(at, "商品数据为空")

    assert "没有可用" in _text(at) or "无可用于分析" in _text(at)


# --------------------------------------------------------------------------
# 验收 4：AI 密钥未配置
# --------------------------------------------------------------------------


def test_without_a_key_the_app_runs_fully_locally():
    """conftest 已经删掉密钥，所以这里跑的就是「无密钥」场景。"""
    at = _run()
    _go(at, "智能分析")
    _assert_no_leak(at, "无密钥")

    assert "本地演示模式" in _text(at)
    assert "启用 AI 增强" not in _text(at)

    _go(at, "首页")
    _go(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
    _button(at, "开始分析").click().run()
    _assert_no_leak(at, "无密钥分析")

    result = _state(at, "zg_result")
    assert result is not None and result.within_budget, "无密钥时应当仍能完成分析"


# --------------------------------------------------------------------------
# 验收 5：AI 服务调用失败
# --------------------------------------------------------------------------


def test_ai_failure_degrades_to_local_rules(monkeypatch):
    import httpx

    from src import ai_service
    from src.ai_service import AIService

    def broken():
        return AIService(
            api_key="sk-test-000000000000",
            base_url="https://example.invalid/v1",
            model="m",
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(503, text="down"))
            ),
        )

    monkeypatch.setattr(ai_service, "get_service", broken)

    at = _run()
    _go(at, "智能分析")
    at.text_area[0].set_value("预算 3000 买笔记本电脑，主要编程").run()
    _button(at, "开始分析").click().run()

    _assert_no_leak(at, "AI 调用失败")
    assert "本地规则" in _text(at)
    assert _state(at, "zg_result") is not None


# --------------------------------------------------------------------------
# 验收 6：没有满足条件的商品
# --------------------------------------------------------------------------


def test_no_matching_products_explains_and_suggests():
    at = _run()
    _go(at, "智能分析")
    at.text_area[0].set_value("预算 500 元买笔记本电脑").run()
    _button(at, "开始分析").click().run()

    _assert_no_leak(at, "无匹配")

    body = _text(at)
    assert "放宽条件的建议" in body

    from src import data_loader

    cheapest = min(
        p.price for p in data_loader.load_catalog().by_category("laptop") if p.price
    )
    assert f"{cheapest:.0f}" in body, "建议里应给出具体的最低参考价"

    result = _state(at, "zg_result")
    assert result.relaxations


# --------------------------------------------------------------------------
# 验收 7：历史记录读取失败
# --------------------------------------------------------------------------


def test_corrupt_history_database_does_not_block_analysis(tmp_path, monkeypatch):
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"definitely not sqlite" * 60)
    monkeypatch.setenv("ZHIGOU_DB_PATH", str(broken))

    at = _run()
    _go(at, "历史记录")
    _assert_no_leak(at, "数据库损坏")
    assert "暂不可用" in _text(at)

    # 关键：分析功能不受影响
    _go(at, "首页")
    _go(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
    _button(at, "开始分析").click().run()
    _assert_no_leak(at, "损坏库下的分析")

    assert _state(at, "zg_result") is not None
    assert "为你推荐" in _text(at)


def test_write_failure_keeps_the_result_on_screen(tmp_path, monkeypatch):
    """保存失败时结果仍要留在页面上——用户这次分析不能白做。"""
    monkeypatch.setenv("ZHIGOU_DB_PATH", str(tmp_path / "broken.db"))
    Path(tmp_path / "broken.db").write_bytes(b"not a database" * 60)

    at = _run()
    _go(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
    _button(at, "开始分析").click().run()
    _assert_no_leak(at, "写入失败")

    assert _state(at, "zg_result") is not None
    assert "为你推荐" in _text(at)
    assert "保存失败" in _text(at)


# --------------------------------------------------------------------------
# 验收 8：重复提交 / 快速修改条件
# --------------------------------------------------------------------------


def test_repeated_submission_creates_one_record():
    at = _run()
    _go(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()

    for _ in range(4):
        _button(at, "开始分析").click().run()
    _assert_no_leak(at, "重复提交")

    _go(at, "历史记录")
    assert "共 1 条记录" in _text(at)


def test_quick_condition_change_is_flagged_until_reanalysed():
    """改完条件还没重算时，界面要说明显示的是上一次的结果。"""
    at = _run()
    _go(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
    _button(at, "开始分析").click().run()

    at.text_input[0].set_value("6000").run()
    _assert_no_leak(at, "快速改条件")
    assert "你已经修改了输入条件" in _text(at)


# --------------------------------------------------------------------------
# 端到端：完整决策链路
# --------------------------------------------------------------------------


def test_full_decision_journey():
    """输入需求 → 筛选排序 → 比较 → 报告 → 存档 → 从历史打开。"""
    at = _run()

    # 1. 输入并分析
    _go(at, "首页")
    at.text_area[0].set_value(EXAMPLE_TEXT).run()
    _button(at, "开始分析").click().run()
    _assert_no_leak(at, "① 分析")
    result = _state(at, "zg_result")
    assert result is not None and result.within_budget

    # 2. 比较三件商品
    _go(at, "商品比较")
    _button(at, "用上次分析的推荐").click().run()
    _assert_no_leak(at, "② 比较")
    assert len(at.session_state["zg_compare_pick"]) >= 3
    assert "横向比较" in _text(at)

    # 3. 报告已生成并可导出
    _go(at, "智能分析")
    report = _state(at, "zg_report")
    assert report is not None
    from src import report_service

    markdown = report_service.to_markdown(report)
    for section in ("需求摘要", "推荐商品及排序", "最终决策建议", "数据说明"):
        assert section in markdown
    # 报告里必须带着数据边界说明。以前断言的是「含『演示』二字」，
    # 现在是「说明数据未经逐条核验」——真实品牌的数据更容易被误读成已核实。
    assert "未核验" in markdown, "导出报告必须写明数据未经核验"

    # 4. 历史里能重新打开，且结论与当初一致
    _go(at, "历史记录")
    _button(at, "查看详情").click().run()
    _assert_no_leak(at, "③ 历史报告")

    body = _text(at)
    for section in ("需求摘要", "预算与筛选条件", "推荐商品及排序",
                    "需要进一步核实的信息", "最终决策建议", "生成时间"):
        assert section in body, f"历史报告缺少「{section}」"

    from src import database

    stored = database.get_analysis(
        at.session_state["zg_history_selected"], viewer=DEFAULT_USER
    )
    assert stored is not None
    assert stored.created_at == report.created_at
    assert len(stored.recommendations) == len(report.recommendations)
    for original, loaded in zip(report.recommendations, stored.recommendations, strict=True):
        assert loaded.score_total == pytest.approx(original.score_total)
        assert loaded.product_id == original.product_id


# --------------------------------------------------------------------------
# 数据集规模
# --------------------------------------------------------------------------


def test_catalog_meets_the_acceptance_bar(catalog):
    """验收要求：商品覆盖全部已登记品类，且每条都如实标注来源与核验状态。

    断言从「必须含『演示』二字」改成了「不许自称已核验」——数据集换成
    真实品牌后，前者已经不成立，而后者才是真正要守的那条线。
    """
    assert len(catalog) >= 20
    assert set(catalog.present_categories()) == set(config.CATEGORY_LABELS)
    for product in catalog.products:
        assert product.data_source, f"{product.id} 没有来源说明"
        assert not product.is_verified, f"{product.id} 自称已核验，但没有核验记录"


# --------------------------------------------------------------------------
# 访问边界（端到端）
# --------------------------------------------------------------------------


def test_unauthenticated_visitor_is_stopped_at_the_login_page(monkeypatch):
    """spec：未登录的访问者被拦在登录页，且**不触发任何数据查询**。

    把取数据集的那一步换成「一调用就炸」：这样「查没查」是断言出来的，
    而不是靠读代码推断的。端到端这一条比 `test_app` 里那条更值钱——
    它跑的是真实的 `app.py` 入口。
    """
    from src.ui import state as state_module

    def explode(*_args, **_kwargs):
        raise AssertionError("未登录时不该去取数据集")

    monkeypatch.setattr(state_module, "get_catalog", explode)
    monkeypatch.setattr(state_module, "get_knowledge_index", explode)

    at = _run(user=None)
    _assert_no_leak(at, "未登录访问")

    body = _text(at)
    assert "登录" in body
    assert "开始分析" not in body, "未登录不该看到任何功能页"
    assert _state(at, state.KEY_USER) is None


def test_two_users_do_not_see_each_others_history():
    """spec：两个用户各自分析，互相看不到对方的历史。

    这是本变更的产品意义所在，所以用端到端的方式走一遍：两个不同的
    登录会话各做一次分析，各自的历史列表里只该有自己的那条。
    """
    from src import database
    from src.auth import ROLE_USER, User

    alice = User(username="alice", role=ROLE_USER)
    bob = User(username="bob", role=ROLE_USER)

    def analyze(user) -> None:
        at = _run(user=user)
        _go(at, "首页")
        _go(at, "首页")
        at.text_area[0].set_value(EXAMPLE_TEXT).run()
        _button(at, "开始分析").click().run()
        _assert_no_leak(at, "分析")

    analyze(alice)
    analyze(bob)

    assert database.count_analyses_of("alice") == 1
    assert database.count_analyses_of("bob") == 1

    at = _run(user=alice)
    _go(at, "历史记录")
    body = _text(at)
    assert "笔记本电脑" in body, "alice 应当看到自己那条"
    assert len(database.list_analyses_of("alice")) == 1
    assert len(database.list_analyses_of("bob")) == 1
