"""智购参谋 —— 应用入口。

本文件只做五件事：页面配置、样式注入、数据加载、侧栏导航、异常兜底。
**不放任何业务逻辑**——筛选、评分、比较、偏好都在 `src/` 下的模块里。

启动：
    streamlit run app.py
"""

from __future__ import annotations

import logging

import streamlit as st

from src import config
from src.errors import ZhigouError, to_user_message
from src.ui import components, icons, state, theme
from src.ui.pages import about, analysis, compare, history, home, knowledge, settings

#: 导航项：(页面名, Material 图标名, 渲染函数)。
#: 图标走 Streamlit 官方的 `icon=` 参数，这是最稳的接入方式。
NAV_ITEMS: list[tuple[str, str, callable]] = [
    ("首页", ":material/home:", home.render),
    ("智能分析", ":material/insights:", analysis.render),
    ("商品比较", ":material/view_column:", compare.render),
    ("知识问答", ":material/menu_book:", knowledge.render),
    ("历史记录", ":material/history:", history.render),
    ("个人设置", ":material/tune:", settings.render),
    ("项目说明", ":material/info:", about.render),
]

PAGES: dict[str, callable] = {
    name: renderer for name, _icon, renderer in NAV_ITEMS
}

logger = logging.getLogger("zhigou")


def _configure_logging() -> None:
    """详细日志写到文件，界面只给用户看中文提示。

    这样既满足「不向用户暴露堆栈」，又保留排查问题所需的信息。
    日志里只记异常类型与消息，**绝不记录密钥或用户输入全文**。
    """
    if logger.handlers:
        return
    handler = logging.FileHandler(config.PROJECT_ROOT / "zhigou.log", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _render_brand() -> None:
    """侧栏顶部的品牌块。"""
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:11px;padding:6px 2px 16px 2px">'
        f'  <div style="width:38px;height:38px;border-radius:10px;flex-shrink:0;'
        f'background:{theme.BRAND};display:flex;align-items:center;'
        f'justify-content:center;color:#fff">'
        f"{icons.icon('sparkles', size=21, color='#ffffff')}</div>"
        f'  <div style="min-width:0">'
        f'    <div style="font-size:17px;font-weight:700;color:#fff;'
        f'letter-spacing:.2px;line-height:1.25">智购参谋</div>'
        f'    <div style="font-size:11.5px;color:{theme.SIDEBAR_MUTED};'
        f'margin-top:1px">AI 消费决策助手</div>'
        f"  </div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_sidebar() -> str:
    """渲染侧栏并返回当前页面名。

    导航用 `st.button` 而不是 `st.radio`：按钮能拿到官方的 `type="primary"`
    选中态（颜色来自 config.toml 的 primaryColor），不用去覆盖 Streamlit
    的单选控件内部结构。
    """
    active = state.current_page()

    with st.sidebar:
        _render_brand()

        for name, icon_name, _renderer in NAV_ITEMS:
            is_active = name == active
            if st.button(
                name,
                key=f"nav_{name}",
                icon=icon_name,
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                state.request_page(name)
                st.rerun()

        st.divider()

        mode, detail = state.current_mode()
        mode_color = "#7FD1A6" if mode == "AI 增强模式" else theme.SIDEBAR_MUTED
        st.markdown(
            f'<div style="padding:0 2px">'
            f'  <div style="font-size:11.5px;color:{theme.SIDEBAR_MUTED};'
            f'letter-spacing:.4px;margin-bottom:5px">当前模式</div>'
            f'  <div style="font-size:13.5px;font-weight:600;color:{mode_color};'
            f'margin-bottom:4px">{mode}</div>'
            f'  <div style="font-size:11.5px;color:{theme.SIDEBAR_MUTED};'
            f'line-height:1.7">{detail}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

        st.divider()

        st.markdown(
            f'<div style="font-size:11.5px;color:{theme.SIDEBAR_MUTED};'
            f'line-height:1.75;padding:0 2px">'
            f"全部商品均为<strong style=\"color:{theme.ON_NAVY}\">演示数据</strong>，"
            f"不是真实在售商品，价格不是实时价格。<br><br>"
            f"「系统匹配评分」衡量的是与你需求的匹配程度，"
            f"不是用户评价或市场口碑。</div>",
            unsafe_allow_html=True,
        )

    return active


def _render_data_help() -> None:
    """数据加载失败时告诉用户该检查什么。"""
    components.section_title("怎么排查")
    components.caption(
        f"应用期望在下面的路径找到商品数据文件：{config.products_path()}\n\n"
        "该文件应为一个 JSON 数组，或一个包含 products 数组的对象，"
        "每条商品记录至少要有 id、name、category、price 等字段。"
    )


def main() -> None:
    st.set_page_config(
        page_title="智购参谋 · AI 消费决策助手",
        page_icon="◆",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _configure_logging()
    theme.inject_styles()

    page = _render_sidebar()
    if page not in PAGES:
        page = state.DEFAULT_PAGE

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


if __name__ == "__main__":
    main()
