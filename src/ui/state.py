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
from src.knowledge.corpus import build_corpus
from src.knowledge.index import BM25Index

# --- session_state 键名 -----------------------------------------------------
# 集中定义，避免各页面随手写字符串导致拼错后静默失效。

KEY_DEMAND = "zg_demand"
KEY_RESULT = "zg_result"          # RecommendationResult
KEY_ERROR = "zg_error"            # 面向用户的中文错误文案
KEY_FOLLOWUPS = "zg_followups"    # 需要追问的问题列表
KEY_SIGNATURE = "zg_signature"    # 本次分析的条件指纹（用于识别条件改动）
KEY_REPORT = "zg_report"          # DecisionReport：当前分析的完整报告
KEY_SAVED_SIGNATURE = "zg_saved_signature"  # 已落库那一次的条件指纹（会话级去重）
KEY_SELECTED = "zg_selected"      # 比较页选中的商品 ID
KEY_COMPARE = "zg_compare"        # ComparisonTable

# --- 跨页请求 ---------------------------------------------------------------
# Streamlit 有一条硬规则：**控件实例化之后，不能再改它绑定的 session_state 键**。
# 侧栏的导航 radio 在页面正文之前创建，所以页面里不能直接写 zg_page；
# 输入控件同理，按钮回调发生时它们早就创建好了。
#
# 统一模式：发起方只**记一个请求**，由接收方在控件创建**之前**消费掉。
# 下面三个键就是这套机制的载体，任何跨页/重置操作都必须走它们。
KEY_PAGE = "zg_current_page"           # 当前页面（普通状态，不绑定任何控件）
KEY_PREFILL = "zg_prefill"             # 请求预填分析页的输入
KEY_RESET = "zg_reset_requested"       # 请求清空分析页的输入
KEY_COMPARE_PREFILL = "zg_compare_prefill"  # 请求填充比较页的商品选择

#: 默认落地页
DEFAULT_PAGE = "首页"


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
    for key in (KEY_DEMAND, KEY_RESULT, KEY_ERROR, KEY_FOLLOWUPS, KEY_SIGNATURE, KEY_REPORT):
        st.session_state.pop(key, None)
    # KEY_SAVED_SIGNATURE 刻意不清：会话内重复提交不必再跑一次数据库查重，
    # 跨会话的重复由数据库层的条件指纹兜底（见 database.save_analysis）


# --------------------------------------------------------------------------
# 数据集
# --------------------------------------------------------------------------


@st.cache_resource(show_spinner=False, max_entries=4)
def _load_cached(path_str: str, mtime: float) -> Catalog:
    """按「数据库路径 + 数据库文件修改时间」缓存数据集。

    **缓存键从商品 JSON 换成了数据库**：商品数据现在存在 SQLite 里，
    盯着 JSON 的 mtime 没有意义——它只在首次导入种子时被读一次。

    把 mtime 放进缓存键是为了接入脚本：`ingest` 写库之后，运行中的应用
    下一次渲染就会自动加载新数据，不需要重启（数据库文件写入后 mtime 会变）。
    max_entries 取小值——旧版本的缓存没有复用价值，留 4 份足够覆盖
    「刚刷新过」的窗口。

    用 `cache_resource` 而不是 `cache_data`：返回的是同一个对象，
    不做拷贝，页面之间共享。
    """
    return load_catalog(Path(path_str))


def _file_stamp(path: Path) -> float:
    """取文件修改时间；文件不在或读不到时返回 0（缓存键仍可用）。"""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def get_catalog() -> Catalog:
    """取商品数据集。

    这里**不吞异常**——数据库损坏、库空且种子缺失等情况让领域异常抛出去，
    由 app.py 在边界处统一转成中文提示，保证整套异常处理只有一个出口。
    """
    path = config.products_db_path()
    return _load_cached(str(path), _file_stamp(path))


# --------------------------------------------------------------------------
# 知识检索索引
# --------------------------------------------------------------------------


def _knowledge_stamp(directory: Path) -> float:
    """语料目录的变更印戳。

    目录自身的 mtime **只在增删文件时变，改内容不会变**——只取目录会让
    「编辑了一份指南」这种最常见的改动无法触发重建。所以把目录下所有
    `.md` 的 mtime 一并取最大值。
    """
    stamps = [_file_stamp(directory)]
    try:
        stamps.extend(_file_stamp(path) for path in directory.rglob("*.md"))
    except OSError:  # 目录不存在或读不了——保持可用，走空语料的分支
        pass
    return max(stamps, default=0.0)


@st.cache_resource(show_spinner=False, max_entries=4)
def _load_index_cached(
    dir_str: str, knowledge_stamp: float, products_stamp: float
) -> BM25Index:
    """按「语料目录 + 语料 mtime + 商品数据 mtime」缓存检索索引。

    商品数据也要进缓存键：商品级知识条目是由商品字段**合成**的，
    改了 `products.json` 而语料没动时，索引同样需要重建。

    后两个参数不参与计算，只用于构造缓存键——与 `_load_cached` 同一手法。
    """
    documents = build_corpus(Path(dir_str), get_catalog().products)
    return BM25Index(documents)


def get_knowledge_index() -> BM25Index:
    """取知识检索索引。改语料或改商品数据后自动重建，不需要重启应用。"""
    directory = config.knowledge_dir()
    return _load_index_cached(
        str(directory),
        _knowledge_stamp(directory),
        _file_stamp(config.products_path()),
    )


def current_mode() -> tuple[str, str]:
    """返回 (模式名, 说明)，供界面顶部展示当前运行模式。"""
    if config.is_ai_configured():
        return "AI 增强模式", f"已接入模型 {config.llm_model()}"
    return "本地演示模式", "未配置模型密钥，全部由本地规则完成，不联网"


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
