"""智购参谋 —— 应用入口。

本文件只做四件事：页面配置、样式注入、数据加载、导航路由。
**不放任何业务逻辑**——筛选、评分、比较、报告都在 `src/` 下的模块里。

启动：
    streamlit run app.py
"""

from __future__ import annotations

import logging

import streamlit as st

from src import config
from src.errors import ZhigouError, to_user_message
from src.ui import components, state, theme
from src.ui.pages import about, analysis, compare, history, home

#: 导航项。键是侧栏显示名，值是渲染函数。
PAGES = {
    "首页": home.render,
    "智能分析": analysis.render,
    "商品比较": compare.render,
    "历史记录": history.render,
    "项目说明": about.render,
}

logger = logging.getLogger("zhigou")


def _configure_logging() -> None:
    """把详细日志写到文件，界面只给用户看中文提示。

    这样既满足「不向用户暴露堆栈」，又保留排查问题需要的信息。
    日志里绝不记录密钥——这里只记异常类型与消息。
    """
    if logger.handlers:
        return
    handler = logging.FileHandler(config.PROJECT_ROOT / "zhigou.log", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _render_sidebar() -> str:
    # 必须最先执行：消费上一轮页面留下的跳转请求。
    # 一旦下面的 radio 被创建，再改它的 session_state 键就会抛
    # StreamlitAPIException，所以这一步不能挪到后面去。
    requested = st.session_state.pop(state.KEY_NAV_REQUEST, None)
    if requested in PAGES:
        st.session_state["zg_page"] = requested

    with st.sidebar:
        st.markdown(
            '<div style="padding:2px 0 14px 0">'
            '<div style="font-size:19px;font-weight:700;color:#1B3A6B">智购参谋</div>'
            '<div style="font-size:12px;color:#5A6472;margin-top:3px">'
            "智能消费决策助手</div></div>",
            unsafe_allow_html=True,
        )

        page = st.radio(
            "导航",
            options=list(PAGES),
            key="zg_page",
            label_visibility="collapsed",
        )

        st.divider()

        mode, detail = state.current_mode()
        st.markdown(
            f'<div style="font-size:12px;color:#5A6472;line-height:1.7">'
            f"<strong>当前模式</strong><br>{mode}<br>{detail}</div>",
            unsafe_allow_html=True,
        )

        st.divider()
        st.markdown(
            '<div style="font-size:12px;color:#5A6472;line-height:1.7">'
            "全部商品均为<strong>演示数据</strong>，"
            "不是真实在售商品，价格不是实时价格。<br>"
            "「系统匹配评分」衡量的是与你需求的匹配程度，"
            "不是用户评价或市场口碑。</div>",
            unsafe_allow_html=True,
        )

    return page


def main() -> None:
    st.set_page_config(
        page_title="智购参谋 · 智能消费决策助手",
        page_icon="◆",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _configure_logging()
    theme.inject_styles()

    page = _render_sidebar()

    # 数据加载是所有页面的前提。失败时给出中文提示并停在这里，
    # 而不是让每个页面各自崩一次。
    try:
        catalog = state.get_catalog()
    except ZhigouError as exc:
        logger.warning("商品数据加载失败: %s", exc.detail or exc)
        components.page_header("智购参谋", "商品数据加载失败")
        components.show_notice(to_user_message(exc), "stop")
        _render_data_help()
        return
    except Exception as exc:  # noqa: BLE001 - 兜底，绝不让堆栈冒到界面上
        logger.exception("商品数据加载时发生未预期错误")
        components.page_header("智购参谋", "商品数据加载失败")
        components.show_notice(to_user_message(exc), "stop")
        _render_data_help()
        return

    # 兜底：任何页面内部的意外异常都转成中文提示，不向用户暴露堆栈
    try:
        PAGES[page](catalog)
    except ZhigouError as exc:
        logger.warning("页面 %s 抛出领域异常: %s", page, exc.detail or exc)
        components.show_notice(to_user_message(exc), "stop")
    except Exception as exc:  # noqa: BLE001
        logger.exception("页面 %s 发生未预期错误", page)
        components.show_notice(to_user_message(exc), "stop")


def _render_data_help() -> None:
    """数据加载失败时告诉用户该检查什么。"""
    components.section_title("怎么排查")
    components.caption(
        f"应用期望在下面的路径找到商品数据文件：\n"
        f"{config.products_path()}\n\n"
        "该文件应为一个 JSON 数组，或一个包含 products 数组的对象，"
        "每条商品记录至少要有 id、name、category、price 等字段。"
    )


if __name__ == "__main__":
    main()
