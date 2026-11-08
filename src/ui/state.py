"""会话状态与数据集缓存。

为什么要有这一层：Streamlit 的每次交互都会**从头重跑整个脚本**。
如果不把分析结果放进 `session_state`，用户每改一个控件都会重新算一遍，
既浪费又会让「重复提交产生重复记录」的问题失控。
所以：结果只由「点分析按钮」写入，渲染永远只读 `session_state`。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from src import config
from src.auth import User

# `get_catalog` / `get_vector_store` 在这里是**对外转出**：页面一直写
# `state.get_catalog()`，保留同名导出可以让界面层不用改。显式的
# `as` 写法是 ruff 认可的重导出标记，否则会被当成未使用的导入删掉。
from src.runtime_cache import (
    get_catalog as get_catalog,
    get_knowledge_index,
    get_vector_store as get_vector_store,
)

# --- session_state 键名 -----------------------------------------------------
# 集中定义，避免各页面随手写字符串导致拼错后静默失效。

KEY_DEMAND = "zg_demand"
KEY_RESULT = "zg_result"  # RecommendationResult
KEY_ERROR = "zg_error"  # 面向用户的中文错误文案
KEY_FOLLOWUPS = "zg_followups"  # 需要追问的问题列表
KEY_SIGNATURE = "zg_signature"  # 本次分析的条件指纹（用于识别条件改动）
KEY_REPORT = "zg_report"  # DecisionReport：当前分析的完整报告
KEY_SAVED_SIGNATURE = "zg_saved_signature"  # 已落库那一次的条件指纹（会话级去重）
KEY_SELECTED = "zg_selected"  # 比较页选中的商品 ID
KEY_COMPARE = "zg_compare"  # ComparisonTable

# --- 跨页请求 ---------------------------------------------------------------
# Streamlit 有一条硬规则：**控件实例化之后，不能再改它绑定的 session_state 键**。
# 侧栏的导航 radio 在页面正文之前创建，所以页面里不能直接写 zg_page；
# 输入控件同理，按钮回调发生时它们早就创建好了。
#
# 统一模式：发起方只**记一个请求**，由接收方在控件创建**之前**消费掉。
# 下面三个键就是这套机制的载体，任何跨页/重置操作都必须走它们。
KEY_PAGE = "zg_current_page"  # 当前页面（普通状态，不绑定任何控件）
KEY_PREFILL = "zg_prefill"  # 请求预填分析页的输入
KEY_RESET = "zg_reset_requested"  # 请求清空分析页的输入
KEY_COMPARE_PREFILL = "zg_compare_prefill"  # 请求填充比较页的商品选择

#: 默认落地页
DEFAULT_PAGE = "首页"

#: 登录页的页面名。未登录时应用只渲染它（见 app.py 的入口短路）。
LOGIN_PAGE = "登录"

# --- 当前登录用户 -----------------------------------------------------------

KEY_USER = "zg_current_user"  # User | None


def current_user() -> User | None:
    """当前登录用户，未登录返回 `None`。

    **唯一的出处就是 session_state，不留模块级缓存。** Streamlit 每次交互
    都重跑整个脚本，但模块只加载一次——把当前用户放进模块变量，
    它会跨会话串味，那是比「刷新要重新登录」严重得多的取舍。
    """
    return st.session_state.get(KEY_USER)


def set_current_user(user: User | None) -> None:
    st.session_state[KEY_USER] = user


def sign_out() -> None:
    """登出：**清空整个会话**，然后回到登录页。

    不是只清 `KEY_USER`：上一个用户的推荐结果、完整报告、比较选择都还在
    会话里，换个账号登录就会看到上一个人的东西。整体清空比逐个列举可靠——
    这里漏一个就是一次数据泄漏，而逐个列举必然会在以后新增会话键时漏掉。
    """
    st.session_state.clear()
    request_page(LOGIN_PAGE)


def get(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def put(key: str, value: Any) -> None:
    st.session_state[key] = value


def current_page() -> str:
    return st.session_state.get(KEY_PAGE, DEFAULT_PAGE)


def request_page(name: str) -> None:
    """切换页面。

    导航改用 `st.button` 之后，当前页存在一个**普通**会话键里，不绑定任何
    控件，所以可以直接写——之前那套「记请求、下一轮消费」的绕路不再需要。
    （当初绕路是因为键绑在侧栏 radio 上，控件创建后就不能改了。）
    """
    st.session_state[KEY_PAGE] = name


def clear_analysis() -> None:
    """清掉上一次分析的一切痕迹。"""
    for key in (
        KEY_DEMAND,
        KEY_RESULT,
        KEY_ERROR,
        KEY_FOLLOWUPS,
        KEY_SIGNATURE,
        KEY_REPORT,
    ):
        st.session_state.pop(key, None)
    # KEY_SAVED_SIGNATURE 刻意不清：会话内重复提交不必再跑一次数据库查重，
    # 跨会话的重复由数据库层的条件指纹兜底（见 database.save_analysis）


# --------------------------------------------------------------------------
# 数据集
# --------------------------------------------------------------------------


# 数据集缓存已抽到 `src.runtime_cache`：那里用 `functools.lru_cache` 实现，
# 语义（按「路径 + 文件 mtime」作缓存键、改库自动重建）与原 `st.cache_resource`
# 一致，但后端进程不再需要 import streamlit。`get_catalog` 见文件顶部导入。


# --------------------------------------------------------------------------
# 知识检索索引
# --------------------------------------------------------------------------


# 检索索引及其 mtime 缓存同样在 `src.runtime_cache` 里，
# `get_knowledge_index` 见文件顶部导入。


def retrieve_knowledge(query: str, *, limit: int | None = None):
    """统一检索入口：语义优先，失败回退关键词。

    返回 `RetrievalResult`（含 passages 与 mode）。页面与 Agent 工具都用它，
    避免两处各自判断「该走向量还是关键词」。
    """
    from src.knowledge import retrieval

    return retrieval.retrieve(query, index=get_knowledge_index(), limit=limit)


def ai_enhanced_active() -> bool:
    """AI 增强现在是否真的在起作用。

    两个条件缺一不可：个人设置里的全局开关（默认开）+ 密钥已配置。
    分析页、AI 问答页、模式标识都从这里取答案——「AI 什么时候在起作用」
    只允许有一个出处，否则三处口径迟早漂移。
    """
    from src import ai_service, settings

    if not settings.load_preferences(current_user()).ai_enhanced:
        return False
    return ai_service.get_service().configured


def current_mode() -> tuple[str, str]:
    """返回 (模式名, 说明)，供界面顶部展示当前运行模式。"""
    if not config.is_ai_configured():
        return "本地演示模式", "未配置模型密钥，全部由本地规则完成，不联网"
    from src import settings

    if not settings.load_preferences(current_user()).ai_enhanced:
        return "本地模式", "AI 增强已在个人设置中关闭，全部由本地规则完成"
    return "AI 增强模式", f"已接入模型 {config.llm_model()}"


# --------------------------------------------------------------------------
# 控件状态镜像
# --------------------------------------------------------------------------
#
# 为什么需要这个东西：侧栏导航按钮的处理器里调了 `st.rerun()`，那次运行在
# 渲染完侧栏之后就中断了，页面正文的控件根本没被「看到」，Streamlit 于是把它们
# 的 session 状态清掉。表现出来就是：用户在分析页写了一段需求，去历史页看一眼
# 再回来，输入全没了——这在真实浏览器里复现过。
#
# 对策是把这些值另存一份到**普通**会话键（不绑控件，不会被清理），
# 下次渲染时如果发现控件键不见了就从镜像里恢复。

_MIRROR_PREFIX = "zg_mirror_"


def snapshot_widgets(namespace: str, keys: dict[str, Any]) -> None:
    """把一组控件的当前值记进镜像。keys 形如 {控件键: 默认值}。"""
    from copy import copy

    recorded: dict[str, Any] = {}
    for key, default in keys.items():
        value = st.session_state.get(key, default)
        # 列表要拷一份，否则镜像和控件共用同一个对象，控件被清时会一起没
        recorded[key] = copy(value) if isinstance(value, list) else value
    st.session_state[_MIRROR_PREFIX + namespace] = recorded


def restore_widgets(namespace: str, keys: dict[str, Any]) -> None:
    """控件键被清掉时从镜像恢复。

    只在键**不存在**时写入。键还在就说明是用户当前这一次的输入，不能被镜像盖掉。
    """
    mirror = st.session_state.get(_MIRROR_PREFIX + namespace)
    if not mirror:
        return
    for key, default in keys.items():
        if key not in st.session_state and key in mirror:
            value = mirror[key]
            st.session_state[key] = list(value) if isinstance(value, list) else value


def clear_mirror(namespace: str) -> None:
    st.session_state.pop(_MIRROR_PREFIX + namespace, None)
