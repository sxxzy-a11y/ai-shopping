"""个人设置页：AI 增强开关、价格取向与数据说明。

偏好**按用户保存在数据库里**（`user_preferences` 表），由 `src/settings.py` 读写。
分析时会把这些偏好**作为默认值**并进需求——用户当次手动填的内容优先，
偏好不会反过来盖掉他的选择。
"""

from __future__ import annotations

import streamlit as st

from src import ai_service, api_config, config, settings
from src.auth import User, is_admin
from src.knowledge import embeddings
from src.data_loader import Catalog
from src.errors import ZhigouError, to_user_message
from src.ui import components, state
from src.ui.theme import bullet_list, facts

# 控件键。带上前缀避免与其它页面重名。
_KEY_AI = "zg_pref_ai"
_KEY_PRIORITY = "zg_pref_priority"
_KEY_SHOW_OVER = "zg_pref_show_over"
_KEY_AUTO = "zg_pref_auto"
_KEY_RESET = "zg_pref_reset"
_WIDGET_KEYS = (
    _KEY_AI,
    _KEY_PRIORITY,
    _KEY_SHOW_OVER,
    _KEY_AUTO,
)


def _seed_widget_state(
    prefs: settings.UserPreferences, user: User | None
) -> settings.UserPreferences:
    """在控件创建**之前**准备好它们的初始值。

    两件事：

    1. 上一轮点了「恢复默认」→ 把控件键清掉并落库默认值
    2. 用库里的偏好初始化控件，**只用 setdefault**——否则用户这一次的
       改动会在每次重跑时被库里的内容覆盖回去

    返回最终生效的偏好对象。
    """
    if st.session_state.pop(_KEY_RESET, False):
        prefs = settings.default_preferences()
        for key in _WIDGET_KEYS:
            st.session_state.pop(key, None)
        try:
            settings.save_preferences(user, prefs)
        except ZhigouError:
            pass  # 落库失败不影响本次界面回到默认值

    st.session_state.setdefault(_KEY_AI, prefs.ai_enhanced)
    st.session_state.setdefault(_KEY_PRIORITY, prefs.price_priority)
    st.session_state.setdefault(_KEY_SHOW_OVER, prefs.show_over_budget)
    st.session_state.setdefault(_KEY_AUTO, prefs.auto_apply)
    return prefs


def _collect() -> settings.UserPreferences:
    return settings.UserPreferences(
        ai_enhanced=bool(st.session_state.get(_KEY_AI, True)),
        price_priority=st.session_state.get(_KEY_PRIORITY, "value"),
        show_over_budget=bool(st.session_state.get(_KEY_SHOW_OVER, True)),
        auto_apply=bool(st.session_state.get(_KEY_AUTO, True)),
    )


def render(catalog: Catalog) -> None:
    user = state.current_user()
    if user is None:
        # 未登录时不该走到这里（入口短路已经拦了一层）。留这道判断是为了
        # 万一有别的路径渲染到这一页，也不至于把偏好写到「没有归属」上去。
        components.show_notice("请先登录后再设置偏好。", "info")
        return

    components.page_header(
        "个人设置",
        "设置一次，之后每次分析都会自动带上这些偏好。"
        "偏好只作为默认值——你在分析页手动填的内容永远优先。",
    )

    prefs = _seed_widget_state(settings.load_preferences(user), user)

    left, right = st.columns([3, 2], gap="large")

    with left:
        components.section_title("AI 增强")
        components.caption(
            "全局总开关：开启且已配置密钥时，「智能分析」与「AI 问答」都由 AI 增强。"
            "关闭后全部走本地规则，不发起任何网络请求。"
        )
        st.toggle(
            "AI 增强模式",
            key=_KEY_AI,
            help="开启后，分析页会把你的需求描述、筛选条件与候选商品的"
            "名称、价格、参数、优缺点发送给模型服务；AI 问答页会把问题与"
            "检索到的资料片段发送过去。不会发送收藏、历史或任何身份信息。",
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
            if st.button("保存设置", type="primary", width="stretch"):
                try:
                    settings.save_preferences(user, _collect())
                except ZhigouError as exc:
                    # 领域异常带的是给用户看的中文说明，直接用它；
                    # 不再自己拼一句，免得两处文案各说各的。
                    components.show_notice(f"保存失败：{to_user_message(exc)}", "stop")
                else:
                    components.show_notice(
                        f"偏好已保存到账号「{user.username}」，下次分析会自动带上。",
                        "ok",
                    )
        with col_reset:
            if st.button("恢复默认", width="stretch"):
                # 只记请求——控件此刻已经创建，不能就地改它们的键
                st.session_state[_KEY_RESET] = True
                st.rerun()

    with right:
        components.section_title("偏好会怎么影响分析")
        st.markdown(
            bullet_list(
                [
                    "AI 增强 → 开启且已配置密钥时，需求解析与问答由 AI 完成；"
                    "推荐排序仍由本地规则计算",
                    "价格取向 → 自动补进核心需求（性价比优先 → 加「性价比」；"
                    "性能优先 → 加「性能」）",
                    "你在分析页手填的内容不会被偏好覆盖，偏好只补空缺",
                ]
            ),
            unsafe_allow_html=True,
        )



    # --- API 配置（仅管理员） ----------------------------------------------
    if is_admin(state.current_user()):
        _render_api_config()

# --------------------------------------------------------------------------
# API 配置（仅管理员）
# --------------------------------------------------------------------------

_FLASH_KEY = "zg_api_config_flash"

_KEY_LLM_BASE = "zg_api_llm_base"
_KEY_LLM_MODEL = "zg_api_llm_model"
_KEY_LLM_SECRET = "zg_api_llm_secret"
_KEY_EMB_BASE = "zg_api_emb_base"
_KEY_EMB_MODEL = "zg_api_emb_model"
_KEY_EMB_DIM = "zg_api_emb_dim"
_KEY_EMB_SECRET = "zg_api_emb_secret"
_INPUT_KEYS = (
    _KEY_LLM_BASE,
    _KEY_LLM_MODEL,
    _KEY_LLM_SECRET,
    _KEY_EMB_BASE,
    _KEY_EMB_MODEL,
    _KEY_EMB_DIM,
    _KEY_EMB_SECRET,
)


def _flash(message: str, tone: str) -> None:
    st.session_state[_FLASH_KEY] = (message, tone)


def _render_flash() -> None:
    pending = st.session_state.pop(_FLASH_KEY, None)
    if pending:
        components.show_notice(pending[0], pending[1])


def _reset_inputs() -> None:
    for key in _INPUT_KEYS:
        st.session_state.pop(key, None)


def _seed_inputs() -> None:
    st.session_state.setdefault(_KEY_LLM_BASE, config.llm_base_url())
    st.session_state.setdefault(_KEY_LLM_MODEL, config.llm_model())
    st.session_state.setdefault(_KEY_EMB_BASE, config.embedding_base_url())
    st.session_state.setdefault(_KEY_EMB_MODEL, config.embedding_model())
    st.session_state.setdefault(_KEY_EMB_DIM, config.embedding_dim())
    st.session_state.setdefault(_KEY_LLM_SECRET, "")
    st.session_state.setdefault(_KEY_EMB_SECRET, "")


def _save(values: dict[str, object]) -> None:
    try:
        api_config.save(values)
    except ZhigouError as exc:
        _flash(f"保存失败：{to_user_message(exc)}", "stop")
        return
    embeddings.reset_service()
    _reset_inputs()
    _flash("已保存。新配置从下一次请求开始生效。", "ok")


def _clear() -> None:
    try:
        api_config.clear()
    except ZhigouError as exc:
        _flash(f"恢复失败：{to_user_message(exc)}", "stop")
        return
    embeddings.reset_service()
    _reset_inputs()
    _flash("已恢复为环境变量 / 默认配置。", "ok")


def _test_llm() -> None:
    ok, message = ai_service.probe()
    _flash(("对话模型连接正常：" if ok else "对话模型连接失败：") + message,
           "ok" if ok else "stop")


def _test_embedding() -> None:
    service = embeddings.get_service()
    if not service.configured:
        _flash("未配置向量化密钥，无法测试。", "warn")
        return
    try:
        vectors = service.embed(["连接测试"])
    except ZhigouError as exc:
        _flash(f"向量化连接失败：{to_user_message(exc)}", "stop")
        return
    except Exception:  # noqa: BLE001
        _flash("向量化连接失败：出现未预期错误。", "stop")
        return
    if not vectors or len(vectors[0]) != config.embedding_dim():
        _flash("向量化连接失败：返回维度与配置不一致。", "stop")
        return
    _flash(f"向量化连接正常：{service.model} · {len(vectors[0])} 维。", "ok")


def _render_api_config() -> None:
    """API 配置（仅管理员调用）：两组服务横向并排，各自独立成卡。"""
    _render_flash()
    _seed_inputs()
    components.section_title("API 配置")

    col_llm, col_emb = st.columns(2, gap="large")

    # --- 对话模型（DeepSeek） --------------------------------------------
    with col_llm:
        with st.container(border=True):
            st.markdown(
                '<div class="zg-card-title">对话模型</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="zg-caption" style="margin-bottom:8px">'
                f"服务商：DeepSeek（OpenAI 兼容）　·　当前密钥："
                f"{api_config.mask(config.llm_api_key())}</div>",
                unsafe_allow_html=True,
            )
            st.text_input("对话端点", key=_KEY_LLM_BASE)
            st.text_input("对话模型名", key=_KEY_LLM_MODEL)
            st.text_input(
                "对话密钥",
                key=_KEY_LLM_SECRET,
                type="password",
                placeholder="留空表示不修改",
            )
            if st.button("测试对话连接", width="stretch"):
                _test_llm()
                st.rerun()

    # --- 向量化（阿里云百炼） --------------------------------------------
    with col_emb:
        with st.container(border=True):
            st.markdown(
                '<div class="zg-card-title">向量化</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="zg-caption" style="margin-bottom:8px">'
                f"服务商：阿里云百炼（OpenAI 兼容）　·　当前密钥："
                f"{api_config.mask(config.embedding_api_key())}</div>",
                unsafe_allow_html=True,
            )
            st.text_input("向量端点", key=_KEY_EMB_BASE)
            st.text_input("向量模型名", key=_KEY_EMB_MODEL)
            st.number_input(
                "向量维度", key=_KEY_EMB_DIM, min_value=64, max_value=8192, step=1
            )
            st.text_input(
                "向量密钥",
                key=_KEY_EMB_SECRET,
                type="password",
                placeholder="留空表示不修改",
            )
            if st.button("测试向量连接", width="stretch"):
                _test_embedding()
                st.rerun()

    st.write("")
    save_col, reset_col = st.columns([1, 1])
    with save_col:
        if st.button("保存配置", type="primary", width="stretch"):
            _save(
                {
                    "llm_base_url": st.session_state.get(_KEY_LLM_BASE, ""),
                    "llm_model": st.session_state.get(_KEY_LLM_MODEL, ""),
                    "llm_api_key": st.session_state.get(_KEY_LLM_SECRET, ""),
                    "embedding_base_url": st.session_state.get(_KEY_EMB_BASE, ""),
                    "embedding_model": st.session_state.get(_KEY_EMB_MODEL, ""),
                    "embedding_dim": st.session_state.get(_KEY_EMB_DIM, 0),
                    "embedding_api_key": st.session_state.get(_KEY_EMB_SECRET, ""),
                }
            )
            st.rerun()
    with reset_col:
        if st.button("恢复为环境变量配置", width="stretch"):
            _clear()
            st.rerun()
