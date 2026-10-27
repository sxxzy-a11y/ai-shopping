"""历史记录页：回顾过去的分析，重新打开当时的报告，管理收藏。"""

from __future__ import annotations

import streamlit as st

from src import config, database, report_service
from src.data_loader import Catalog
from src.errors import ZhigouError, to_user_message
from src.ui import components, icons, state
from src.ui.theme import bullet_list, chip, esc, facts, notice

_SELECTED_KEY = "zg_history_selected"

#: 待显示的提示。删除之后要 `st.rerun()` 刷新列表，而 `show_notice` 是
#: **即时渲染**的——就地渲染的提示会被那次重跑丢掉，用户点完删除只看到列表变短，
#: 没有任何反馈。（同一个坑在管理页踩过，那边的 `_flash` 是同一套做法。）
_FLASH_KEY = "zg_history_flash"


def _flash(message: str, tone: str) -> None:
    st.session_state[_FLASH_KEY] = (message, tone)


def _render_flash() -> None:
    pending = st.session_state.pop(_FLASH_KEY, None)
    if pending:
        components.show_notice(pending[0], pending[1])


def _delete_entry(entry_id: int, confirmed: bool) -> None:
    """删除一条历史记录（硬删，不可恢复）。

    **未勾选确认时只提示、不删**，而不是把按钮置灰：灰按钮看起来像坏了，
    而「点了没反应、但告诉你为什么」至少把规则说清楚了。

    归属校验在数据层（`delete_analysis` 只放行本人与管理员），这里不做判断——
    界面上的判断都只是提示，不是权限。
    """
    if not confirmed:
        _flash("请先勾选「确认」再删除。", "warn")
        st.rerun()

    try:
        deleted = database.delete_analysis(entry_id, viewer=state.current_user())
    except ZhigouError as exc:
        _flash(to_user_message(exc), "stop")
        st.rerun()

    _flash(
        "已删除这条历史记录。" if deleted else "这条记录不存在，可能已被删除。",
        "ok" if deleted else "warn",
    )
    # 删掉的若正是右侧打开着的那条，把它关掉——否则右边会停在一份已不存在的报告上
    if st.session_state.get(_SELECTED_KEY) == entry_id:
        st.session_state.pop(_SELECTED_KEY, None)
    st.rerun()


def _render_entry_row(entry: database.HistoryEntry) -> None:
    """历史列表里的一行：摘要 + 时间 + 得分 + 查看详情。"""
    tone = (
        "ok"
        if entry.top_score is not None and entry.top_score >= 70
        else ("brand" if entry.top_score is not None else "neutral")
    )

    # 按钮列要给足宽度：中文四个字在窄列里会被竖着折成四行。
    # 得分标签并进标题那一行——单独占一列时它既贴不到标题、又和按钮对不齐。
    # 操作区用横向容器排成一行（确认 / 查看 / 删除）：拆成并排的列时，
    # 「确认删除」会被顶到行首，和按钮错开大半行。
    col_main, col_actions = st.columns([7, 3], vertical_alignment="center")

    with col_main:
        st.markdown(
            f'<div class="zg-row" style="align-items:center">'
            f'  <div class="zg-thumb">{icons.icon("file", size=22)}</div>'
            f'  <div class="zg-row-main">'
            f'    <div class="zg-row-name" style="font-size:14.5px">'
            f"      {esc(entry.demand_summary)}"
            f'      <span style="display:inline-block;margin-left:8px;vertical-align:1px">'
            f"{chip(entry.score_label, tone)}</span>"
            f"    </div>"
            f'    <div class="zg-row-spec" style="margin-bottom:0">'
            f"      {esc(entry.created_at_label)}　·　"
            f"      {entry.result_count} 件推荐"
            + (f"　·　首选 {esc(entry.top_product)}" if entry.top_product else "")
            + "</div>"
            f"  </div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_actions:
        with st.container(
            horizontal=True,
            horizontal_alignment="right",
            vertical_alignment="center",
            gap="small",
        ):
            confirmed = st.checkbox(
                "确认删除", key=f"del_ok_{entry.id}", help="勾选后才能删除这条记录"
            )
            if st.button("查看详情", key=f"open_{entry.id}"):
                st.session_state[_SELECTED_KEY] = entry.id
                st.rerun()
            if st.button("删除", key=f"del_{entry.id}"):
                _delete_entry(entry.id, confirmed)


def _render_report_detail(entry_id: int) -> None:
    """右侧：打开某条历史记录的完整报告。"""
    try:
        report = database.get_analysis(entry_id, viewer=state.current_user())
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    if report is None:
        components.show_notice("这条记录不存在，可能已被删除。", "warn")
        st.session_state.pop(_SELECTED_KEY, None)
        return

    st.write("")
    components.render_stored_report(report)

    st.write("")
    col_md, col_csv, col_back = st.columns([1, 1, 3])
    with col_md:
        st.download_button(
            "导出 Markdown",
            data=report_service.markdown_bytes(report),
            file_name=report_service.suggested_filename(report, "md"),
            mime="text/markdown",
            key=f"hist_md_{entry_id}",
            width="stretch",
        )
    with col_csv:
        st.download_button(
            "导出 CSV",
            data=report_service.csv_bytes(report),
            file_name=report_service.suggested_filename(report, "csv"),
            mime="text/csv",
            key=f"hist_csv_{entry_id}",
            width="stretch",
        )
    with col_back:
        st.write("")
        if st.button("关闭报告", width="content"):
            st.session_state.pop(_SELECTED_KEY, None)
            st.rerun()


def _render_history_tab(catalog: Catalog) -> None:
    user = state.current_user()
    if user is None:
        return

    try:
        # **只列本人的记录**：`list_analyses()` 是全站视角，给管理员概览用的。
        entries = database.list_analyses_of(user.username)
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        components.caption(
            "历史记录读取失败不会影响其它功能——你仍然可以在「智能分析」页做新的分析。"
        )
        return

    if not entries:
        components.empty_state(
            "还没有分析记录。到「智能分析」页做一次分析后，这里会保存下来。",
            icon_name="history",
        )
        return

    components.caption(
        f"共 {len(entries)} 条记录，按时间由新到旧排列。"
        "报告保存的是当时的结论，之后商品数据更新不会改变它。"
    )
    st.write("")

    selected = st.session_state.get(_SELECTED_KEY)

    if selected is not None:
        left, right = st.columns([2, 3], gap="large")
    else:
        left, right = st.container(), None  # type: ignore[assignment]

    with left:
        for entry in entries:
            _render_entry_row(entry)
            st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)

    if right is not None:
        with right:
            _render_report_detail(selected)


def _render_favorites_tab(catalog: Catalog) -> None:
    user = state.current_user()
    if user is None:
        return

    try:
        favorites = database.list_favorites(user.username)
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    if not favorites:
        components.empty_state(
            "还没有收藏任何商品。在推荐列表里点收藏，之后就能在这里快速找到。",
            icon_name="bookmark",
        )
        return

    components.caption(f"共收藏 {len(favorites)} 件商品，按收藏时间由新到旧排列。")

    gone: list[str] = []
    for product_id, added_at in favorites:
        product = catalog.get(product_id)
        if product is None:
            gone.append(product_id)
            continue

        col_card, col_action = st.columns([5, 1])
        with col_card:
            st.markdown(
                components.product_mini(product) + f'<div class="zg-muted" style="margin-top:4px">收藏于 {esc(added_at[:16].replace("T", " "))}</div>',
                unsafe_allow_html=True,
            )
        with col_action:
            st.write("")
            if st.button("取消收藏", key=f"unfav_{product_id}", width="stretch"):
                try:
                    database.remove_favorite(user.username, product_id)
                except ZhigouError as exc:
                    components.show_notice(to_user_message(exc), "stop")
                else:
                    st.rerun()

    if gone:
        st.write("")
        components.show_notice(
            f"有 {len(gone)} 条收藏对应的商品已不在当前数据集中：{'、'.join(gone)}。"
            "收藏记录仍然保留，如果商品数据补回来就会重新显示。",
            "warn",
        )


def render(catalog: Catalog) -> None:
    components.page_header(
        "历史记录",
        "回顾过去的分析，重新打开当时的结论，管理收藏的商品。",
    )
    _render_flash()

    healthy, message = database.check_health()
    if not healthy:
        components.show_notice(message, "stop")
        st.markdown(
            f'<div class="zg-card is-flat">{bullet_list([
                "历史记录与收藏功能暂不可用，其余功能不受影响",
                "你仍然可以在「智能分析」页完成新的分析",
                "如需恢复，可以联系管理员处理",
            ])}</div>',
            unsafe_allow_html=True,
        )
        return

    tab_history, tab_favorites = st.tabs(["分析历史", "我的收藏"])
    with tab_history:
        _render_history_tab(catalog)
    with tab_favorites:
        _render_favorites_tab(catalog)
