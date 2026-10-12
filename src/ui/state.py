"""会话状态与数据集缓存。

为什么要有这一层：Streamlit 的每次交互都会**从头重跑整个脚本**。
如果不把分析结果放进 `session_state`，用户每改一个控件都会重新算一遍，
既浪费又会让「重复提交产生重复记录」的问题失控。
所以：结果只由「点分析按钮」写入，渲染永远只读 `session_state`。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from src import config
from src.data_loader import Catalog, load_catalog

# --- session_state 键名 -----------------------------------------------------
# 集中定义，避免各页面随手写字符串导致拼错后静默失效。

KEY_DEMAND = "zg_demand"
KEY_RESULT = "zg_result"          # RecommendationResult
KEY_ERROR = "zg_error"            # 面向用户的中文错误文案
KEY_FOLLOWUPS = "zg_followups"    # 需要追问的问题列表
KEY_SIGNATURE = "zg_signature"    # 本次分析的条件指纹（用于识别重复提交）
KEY_SELECTED = "zg_selected"      # 比较页选中的商品 ID
KEY_COMPARE = "zg_compare"        # ComparisonTable

# --- 跨页请求 ---------------------------------------------------------------
# Streamlit 有一条硬规则：**控件实例化之后，不能再改它绑定的 session_state 键**。
# 侧栏的导航 radio 在页面正文之前创建，所以页面里不能直接写 zg_page；
# 输入控件同理，按钮回调发生时它们早就创建好了。
#
# 统一模式：发起方只**记一个请求**，由接收方在控件创建**之前**消费掉。
# 下面三个键就是这套机制的载体，任何跨页/重置操作都必须走它们。
KEY_NAV_REQUEST = "zg_nav_request"     # 请求切换到某个页面
KEY_PREFILL = "zg_prefill"             # 请求预填分析页的输入
KEY_RESET = "zg_reset_requested"       # 请求清空分析页的输入
KEY_COMPARE_PREFILL = "zg_compare_prefill"  # 请求填充比较页的商品选择


def get(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def put(key: str, value: Any) -> None:
    st.session_state[key] = value


def request_page(name: str) -> None:
    """请求切换到某个页面。

    不能直接写 `zg_page`——那是侧栏 radio 的键，此刻控件已经建好了。
    记为请求，由 app.py 在创建 radio 之前消费。
    """
    st.session_state[KEY_NAV_REQUEST] = name


def clear_analysis() -> None:
    """清掉上一次分析的一切痕迹。"""
    for key in (KEY_DEMAND, KEY_RESULT, KEY_ERROR, KEY_FOLLOWUPS, KEY_SIGNATURE):
        st.session_state.pop(key, None)


# --------------------------------------------------------------------------
# 数据集
# --------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _load_cached(path_str: str) -> Catalog:
    """按路径缓存数据集。

    用 `cache_resource` 而不是 `cache_data`：返回的是同一个对象，
    不做拷贝，页面之间共享。数据文件很小，缓存一次足够。
    """
    return load_catalog(Path(path_str))


def get_catalog() -> Catalog:
    """取商品数据集。

    这里**不吞异常**——文件缺失/非法时让 `DataFileMissing` 等抛出去，
    由 app.py 在边界处统一转成中文提示，保证整套异常处理只有一个出口。
    """
    return _load_cached(str(config.products_path()))


def current_mode() -> tuple[str, str]:
    """返回 (模式名, 说明)，供界面顶部展示当前运行模式。"""
    if config.is_ai_configured():
        return "AI 增强模式", f"已接入模型 {config.llm_model()}"
    return "本地演示模式", "未配置模型密钥，全部由本地规则完成，不联网"
