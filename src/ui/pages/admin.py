"""管理员页面：用户管理与全站分析概览。

两个页面共用这个模块，因为它们都只对管理员开放，且都要做同一件事：
**在页面入口再过一道权限守卫**。

为什么界面已经有守卫还要在这里再写一遍：`app.py` 靠侧边栏隐藏入口，
那只是不让普通用户看见；页面函数本身是可以在别处被调用的
（Streamlit 里页面之间互相调用、`session_state` 也能被脚本改写）。
所以这里的 `require_admin` 是**第二道**，数据层写入口里还有第三道
（design D3）。三道里任何一道单独存在都不够。
"""

from __future__ import annotations

import streamlit as st

from src import accounts, database
from src.auth import ROLE_ADMIN, ROLE_LABELS, ROLE_USER, require_admin
from src.errors import ZhigouError, to_user_message
from src.ui import components, state
from src.ui.theme import facts

_ROLE_OPTIONS = (ROLE_USER, ROLE_ADMIN)

#: 待显示的提示。见 `_flash()` 的说明——**不能就地渲染**。
_KEY_FLASH = "zg_admin_flash"


def _viewer():
    """当前访问者。本模块所有操作都以它为权限依据。"""
    return state.current_user()


def _flash(message: str, tone: str) -> None:
    """记下一条提示，留到**下一次运行**再显示。

    为什么不就地 `show_notice()`：管理操作做完会 `st.rerun()` 刷新列表，
    那次重跑会把这一轮的输出整体丢掉。结果是用户点了「停用账号」，
    页面刷新了，然后什么都没说——他只能自己去列表里猜有没有生效。
    """
    st.session_state[_KEY_FLASH] = (message, tone)


def _render_flash() -> None:
    """显示并清掉上一条提示。"""
    pending = st.session_state.pop(_KEY_FLASH, None)
    if pending:
        components.show_notice(pending[0], pending[1])


# --------------------------------------------------------------------------
# 用户管理（§6）
# --------------------------------------------------------------------------


def render_users(catalog=None) -> None:
    """用户管理页。`catalog` 用不上，签名与其它页面保持一致。"""
    viewer = _viewer()
    require_admin(viewer)

    components.page_header(
        "用户管理",
        "新建账号、改角色、重置密码、停用账号。**不提供删除**——"
        "删掉账号会让他的历史记录失去归属。",
    )

    _render_flash()
    _render_create_account(viewer)
    st.divider()
    _render_user_list(viewer)


def _render_create_account(viewer) -> None:
    components.section_title("新建账号")

    with st.form("zg_admin_new_user"):
        username = st.text_input("用户名", key="zg_admin_new_username")
        password = st.text_input("初始密码", type="password", key="zg_admin_new_password")
        role = st.selectbox(
            "角色",
            options=list(_ROLE_OPTIONS),
            format_func=lambda value: ROLE_LABELS.get(value, value),
            key="zg_admin_new_role",
        )
        submitted = st.form_submit_button("创建", type="primary")

    if not submitted:
        return

    try:
        accounts.create_account(viewer, username, password, role=role)
    except ZhigouError as exc:
        components.show_notice(f"创建失败：{to_user_message(exc)}", "stop")
        return

    components.show_notice(f"已创建账号「{username}」。", "ok")


def _render_user_list(viewer) -> None:
    components.section_title("全部账号")

    try:
        users = database.list_users()
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    if not users:
        components.empty_state("还没有任何账号。")
        return

    components.caption(
        f"共 {len(users)} 个账号，其中可用管理员 "
        f"{database.count_active_admins()} 个。"
        "系统必须至少保留一个可用的管理员——"
        "对最后一个管理员的降级与停用会被拒绝。"
    )

    for user in users:
        _render_user_row(viewer, user)


def _render_user_row(viewer, user) -> None:
    status = "启用" if user.is_active else "**已停用**"
    with st.expander(f"{user.username} · {user.role_label} · {status}"):
        components.caption(f"创建时间：{user.created_at or '未知'}")

        col_role, col_role_action = st.columns([3, 1])
        with col_role:
            new_role = st.selectbox(
                # 标签与新建表单里的那个区分开：两处都叫「角色」时，
                # 界面测试没法按标签取到想要的那一个。
                "修改角色",
                options=list(_ROLE_OPTIONS),
                index=_ROLE_OPTIONS.index(user.role) if user.role in _ROLE_OPTIONS else 0,
                format_func=lambda value: ROLE_LABELS.get(value, value),
                key=f"zg_admin_role_{user.username}",
            )
        with col_role_action:
            st.write("")
            if st.button("保存角色", key=f"zg_admin_role_save_{user.username}"):
                _apply(
                    lambda: database.set_user_role(
                        user.username, new_role, viewer=viewer
                    ),
                    f"已把「{user.username}」的角色改为 "
                    f"{ROLE_LABELS.get(new_role, new_role)}。",
                )

        col_pw, col_pw_action = st.columns([3, 1])
        with col_pw:
            new_password = st.text_input(
                "重置密码",
                type="password",
                key=f"zg_admin_pw_{user.username}",
                help="至少 8 位。留空不会改动。",
            )
        with col_pw_action:
            st.write("")
            if st.button("重置密码", key=f"zg_admin_pw_save_{user.username}"):
                if not new_password:
                    components.show_notice("请先填写新密码。", "warn")
                else:
                    _apply(
                        lambda: database.set_user_password(
                            user.username, new_password, viewer=viewer
                        ),
                        f"已重置「{user.username}」的密码。",
                    )

        label = "停用账号" if user.is_active else "启用账号"
        if st.button(label, key=f"zg_admin_active_{user.username}"):
            _apply(
                lambda: database.set_user_active(
                    user.username, not user.is_active, viewer=viewer
                ),
                f"已{'停用' if user.is_active else '启用'}「{user.username}」。",
            )

        # 刻意的缺席：这里**没有**删除账号的按钮。删掉账号之后，他的历史记录
        # 要么被级联删掉（丢用户数据），要么指向一个不存在的账号（更乱）。
        components.caption("账号只能停用，不能删除——删除会让历史记录失去归属。")


def _apply(action, success_message: str) -> None:
    """执行一次管理操作，记下结果提示，然后重跑刷新列表。

    领域异常（越权、最后一个管理员、用户名重复……）带的文案直接可用，
    所以成功与失败走同一条提示通道，只在语气上分开。

    **未预期的异常不在这里吞掉**——交给 `app.py` 的兜底，免得这里
    又养出一个「什么异常都当业务失败」的出口。
    """
    try:
        action()
    except ZhigouError as exc:
        _flash(to_user_message(exc), "stop")
    else:
        _flash(success_message, "ok")

    # 无论成败都要重跑：失败的信息也还等着在下一次运行里显示。
    st.rerun()


# --------------------------------------------------------------------------
# 全站分析概览（§7）
# --------------------------------------------------------------------------


def render_overview(catalog=None) -> None:
    viewer = _viewer()
    require_admin(viewer)

    components.page_header(
        "全站概览",
        "所有账号的分析记录。**无归属的记录单独列出**——"
        "那是引入账号体系之前的遗留数据，不知道是谁做的。",
    )

    _render_flash()

    try:
        entries = database.list_analyses(limit=500)
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    if not entries:
        components.empty_state("全站还没有任何分析记录。")
        return

    total = len(entries)
    unowned = database.count_unowned_analyses()
    by_owner: dict[str, int] = {}
    for entry in entries:
        by_owner[entry.owner_label] = by_owner.get(entry.owner_label, 0) + 1

    _render_counts(total, by_owner, unowned)
    st.divider()
    _render_entry_table(entries)


def _render_counts(total: int, by_owner: dict[str, int], unowned: int) -> None:
    components.section_title("数量")

    rows = [("记录总数", f"{total} 条")]
    for owner, count in sorted(by_owner.items(), key=lambda kv: (-kv[1], kv[0])):
        rows.append((f"　{owner}", f"{count} 条"))

    st.markdown(facts(rows), unsafe_allow_html=True)

    if unowned:
        st.write("")
        components.show_notice(
            f"其中 {unowned} 条**无归属**，是单用户时期留下的记录，"
            "只有管理员能看到。系统没有把它们划给任何账号——"
            "那样等于编造归属。",
            "info",
        )


def _cell(value: object) -> str:
    """Markdown 表格里的一个单元格。

    需求摘要是用户输入来的，里面可能有 `|`——不转义就会把表格撑坏，
    多出来的那一段会被当成新的一列。
    """
    return str(value).replace("|", "\\|").replace("\n", " ")


def _render_entry_table(entries) -> None:
    components.section_title("记录明细")

    lines = [
        "| 归属用户 | 时间 | 需求摘要 | 推荐条数 |",
        "|---|---|---|---:|",
    ]
    for entry in entries:
        lines.append(
            f"| {_cell(entry.owner_label)} | {_cell(entry.created_at_label)} "
            f"| {_cell(entry.demand_summary)} | {entry.result_count} |"
        )

    st.markdown("\n".join(lines))
