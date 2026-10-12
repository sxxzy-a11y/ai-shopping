"""个人设置页：品牌偏好、价格取向、关注项与数据说明。

偏好保存在 `storage/settings.json`，由 `src/settings.py` 读写。
分析时会把这些偏好**作为默认值**并进需求——用户当次手动填的内容优先，
偏好不会反过来盖掉他的选择。
"""

from __future__ import annotations

import streamlit as st

from src import config, settings
from src.data_loader import Catalog
from src.errors import ZhigouError, to_user_message
from src.ui import components, state
from src.ui.theme import bullet_list, facts

# 控件键。带上前缀避免与其它页面重名。
_KEY_BRANDS = "zg_pref_brands"
_KEY_PRIORITY = "zg_pref_priority"
_KEY_FOCUS = "zg_pref_focus"
_KEY_SHOW_OVER = "zg_pref_show_over"
_KEY_AUTO = "zg_pref_auto"
_KEY_RESET = "zg_pref_reset"
_WIDGET_KEYS = (
    _KEY_BRANDS,
    _KEY_PRIORITY,
    _KEY_FOCUS,
    _KEY_SHOW_OVER,
    _KEY_AUTO,
)


def _seed_widget_state(prefs: settings.UserPreferences) -> settings.UserPreferences:
    """在控件创建**之前**准备好它们的初始值。

    两件事：

    1. 上一轮点了「恢复默认」→ 把控件键清掉并落盘默认值
    2. 用文件里的偏好初始化控件，**只用 setdefault**——否则用户这一次的
       改动会在每次重跑时被文件内容覆盖回去

    返回最终生效的偏好对象。
    """
    if st.session_state.pop(_KEY_RESET, False):
        prefs = settings.default_preferences()
        for key in _WIDGET_KEYS:
            st.session_state.pop(key, None)
        try:
            settings.save_preferences(prefs)
        except OSError:
            pass  # 落盘失败不影响本次界面回到默认值

    st.session_state.setdefault(_KEY_BRANDS, list(prefs.brand_preferences))
    st.session_state.setdefault(_KEY_PRIORITY, prefs.price_priority)
    st.session_state.setdefault(_KEY_FOCUS, list(prefs.focus_areas))
    st.session_state.setdefault(_KEY_SHOW_OVER, prefs.show_over_budget)
    st.session_state.setdefault(_KEY_AUTO, prefs.auto_apply)
    return prefs


def _collect() -> settings.UserPreferences:
    return settings.UserPreferences(
        brand_preferences=list(st.session_state.get(_KEY_BRANDS, [])),
        price_priority=st.session_state.get(_KEY_PRIORITY, "value"),
        focus_areas=list(st.session_state.get(_KEY_FOCUS, [])),
        show_over_budget=bool(st.session_state.get(_KEY_SHOW_OVER, True)),
        auto_apply=bool(st.session_state.get(_KEY_AUTO, True)),
    )


def render(catalog: Catalog) -> None:
    components.page_header(
        "个人设置",
        "设置一次，之后每次分析都会自动带上这些偏好。"
        "偏好只作为默认值——你在分析页手动填的内容永远优先。",
    )

    prefs = _seed_widget_state(settings.load_preferences())

    left, right = st.columns([3, 2], gap="large")

    with left:
        components.section_title("品牌偏好")
        components.caption("选中后，分析时会优先在这些品牌里筛选。留空表示不限品牌。")
        st.pills(
            "常用品牌",
            options=catalog.brands(),
            selection_mode="multi",
            key=_KEY_BRANDS,
            label_visibility="collapsed",
        )

        components.section_title("价格取向")
        components.caption(
            "决定分析时自动补进「核心需求」的词。品牌优先只影响筛选范围，"
            "不改变评分维度——因为品牌本身不是一个评分项。"
        )
        # 这里用 radio 而不是 st.pills：pills 的**单选模式**在 AppTest 下
        # 会抛 `content: "v" is not in list`——AppTest 序列化控件状态时把
        # 字符串值当成数组逐字符遍历了。浏览器里 pills 是正常的，但界面测试
        # 覆盖不到这一页，代价不值得。多选的 pills 没有这个问题，下面照用。
        st.radio(
            "价格取向",
            options=list(settings.PRICE_PRIORITY_LABELS),
            format_func=lambda value: settings.PRICE_PRIORITY_LABELS[value],
            horizontal=True,
            key=_KEY_PRIORITY,
            label_visibility="collapsed",
        )

        components.section_title("长期关注项")
        components.caption("这些会并入每次分析的核心需求，参与匹配度评分。")
        st.pills(
            "关注项",
            options=list(settings.FOCUS_OPTIONS),
            selection_mode="multi",
            key=_KEY_FOCUS,
            label_visibility="collapsed",
        )

        components.section_title("显示与行为")
        st.toggle(
            "在分析结果里展示超预算商品",
            key=_KEY_SHOW_OVER,
            help="关掉后只保留预算内的商品。默认开着，因为「加多少钱能买到什么」"
            "本身也是决策信息。",
        )
        st.toggle(
            "分析时自动应用上面的偏好",
            key=_KEY_AUTO,
            help="关掉后每次分析都需要手动填写，偏好仅在此页保存。",
        )

        st.write("")
        col_save, col_reset = st.columns([1, 1])
        with col_save:
            if st.button("保存设置", type="primary", use_container_width=True):
                try:
                    path = settings.save_preferences(_collect())
                except (OSError, ValueError) as exc:
                    components.show_notice(
                        f"保存失败：{to_user_message(ZhigouError())}（{type(exc).__name__}）",
                        "stop",
                    )
                else:
                    components.show_notice(
                        f"已保存到 {config.display_path(path)}，"
                        f"下次分析会自动带上这些偏好。",
                        "ok",
                    )
        with col_reset:
            if st.button("恢复默认", use_container_width=True):
                # 只记请求——控件此刻已经创建，不能就地改它们的键
                st.session_state[_KEY_RESET] = True
                st.rerun()

    with right:
        components.section_title("偏好会怎么影响分析")
        st.markdown(
            bullet_list(
                [
                    "品牌偏好 → 只在选中的品牌内筛选；没有命中时会提示放宽",
                    "价格取向 → 自动补进核心需求（性价比优先 → 加「性价比」；"
                    "性能优先 → 加「性能」）",
                    "长期关注项 → 全部并入核心需求，参与匹配度评分",
                    "你在分析页手填的内容不会被偏好覆盖，偏好只补空缺",
                ]
            ),
            unsafe_allow_html=True,
        )

        components.section_title("存储位置")
        st.markdown(
            facts(
                [
                    ("设置文件", config.display_path(settings.settings_path())),
                    ("商品数据", config.display_path(config.products_path())),
                    ("数据库", "阶段四接入，用于保存分析历史与收藏"),
                ]
            ),
            unsafe_allow_html=True,
        )
        st.write("")
        components.show_notice(
            "设置文件保存在本机，不会上传到任何地方。"
            "它只记录你的偏好，不包含任何个人信息。",
            "info",
        )

        components.section_title("AI 设置")
        mode, detail = state.current_mode()
        st.markdown(facts([("当前模式", mode), ("说明", detail)]), unsafe_allow_html=True)
        st.write("")
        components.caption(
            "大模型接入在阶段五实现。届时可以通过环境变量配置密钥与模型，"
            "未配置时应用照常以本地规则模式运行，不发起任何网络请求。"
        )
