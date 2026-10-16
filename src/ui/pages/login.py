"""登录页与注册页。

未登录时应用**只渲染这一页**（见 `app.py` 的入口短路），而且不加载任何数据：
`render()` 刻意不接受 `catalog` 参数——没有数据可用，也就无从查询
（spec `user-auth`：未登录不触发任何数据查询）。

几个刻意的选择：

- 用 `st.form` 包住表单：不包的话每敲一个字符都会重跑一次脚本，
  而每次重跑都会去查一次库（校验要等提交，不该在打字时就跑）。
- **登录失败不区分原因**：用户名不存在、密码错误、账号停用共用一句话，
  由 `src/accounts.py` 的 `authenticate()` 保证。这里只负责把领域异常
  翻译成中文提示，不自己判断属于哪一种。
- 注册成功不自动登录：让用户自己用新账号登一次，顺带验证密码记得住。
"""

from __future__ import annotations

import streamlit as st

from src import accounts
from src.errors import ZhigouError, to_user_message
from src.ui import components, disclosure, state

#: 当前处于「登录」还是「注册」。
_KEY_MODE = "zg_auth_mode"
_MODE_LOGIN = "login"
_MODE_REGISTER = "register"


def render() -> None:
    """渲染登录页。**不接受 catalog**——未登录时不该有任何数据可查。"""
    components.page_header(
        "智购参谋",
        "登录后使用。没有账号可以直接注册一个，注册得到的都是普通用户。",
    )

    left, right = st.columns([3, 2], gap="large")

    with left:
        mode = st.session_state.get(_KEY_MODE, _MODE_LOGIN)
        if mode == _MODE_REGISTER:
            _render_register_form()
        else:
            _render_login_form()
        _render_mode_switch(mode)

    with right:
        _render_boundary_notice()


# --------------------------------------------------------------------------
# 登录
# --------------------------------------------------------------------------


def _sign_in(user) -> None:
    """登录成功后的落库动作：记当前用户、把页面送到首页、整页重跑。"""
    state.set_current_user(user)
    state.request_page(state.DEFAULT_PAGE)
    st.rerun()


def _render_login_form() -> None:
    components.section_title("登录")

    with st.form("zg_login"):
        username = st.text_input("用户名", key="zg_login_username")
        password = st.text_input("密码", type="password", key="zg_login_password")
        submitted = st.form_submit_button("登录", type="primary", use_container_width=True)

    if not submitted:
        return

    try:
        user = accounts.authenticate(username, password)
    except ZhigouError as exc:
        # 领域异常带的已经是「用户名或密码不正确」这一句，不区分原因。
        # 这里不再加工措辞——加工就有可能把内部原因带出来。
        components.show_notice(to_user_message(exc), "stop")
        return

    _sign_in(user)


# --------------------------------------------------------------------------
# 注册
# --------------------------------------------------------------------------


def _render_register_form() -> None:
    components.section_title("注册")
    components.caption(
        "注册得到的账号一律是**普通用户**。管理员权限只能由现有管理员授予——"
        "不设「第一个注册的人自动成为管理员」这种规则。"
    )

    with st.form("zg_register"):
        username = st.text_input("用户名", key="zg_reg_username")
        password = st.text_input(
            "密码", type="password", key="zg_reg_password", help="至少 8 位"
        )
        confirm = st.text_input("确认密码", type="password", key="zg_reg_confirm")
        submitted = st.form_submit_button("注册", type="primary", use_container_width=True)

    if not submitted:
        return

    if password != confirm:
        components.show_notice("两次输入的密码不一致，请重新输入。", "stop")
        return

    try:
        accounts.register(username, password)
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    st.session_state[_KEY_MODE] = _MODE_LOGIN
    components.show_notice("注册成功。请用刚才的账号登录。", "ok")


def _render_mode_switch(mode: str) -> None:
    """登录 ⇄ 注册。"""
    st.write("")
    if mode == _MODE_REGISTER:
        if st.button("已有账号，去登录", use_container_width=False):
            st.session_state[_KEY_MODE] = _MODE_LOGIN
            st.rerun()
    else:
        if st.button("没有账号？注册一个", use_container_width=False):
            st.session_state[_KEY_MODE] = _MODE_REGISTER
            st.rerun()


# --------------------------------------------------------------------------
# 右侧边界说明
# --------------------------------------------------------------------------


def _render_boundary_notice() -> None:
    """把「演示级鉴权」的边界摆在登录口上。

    放在这里而不是藏在「项目说明」深处：使用者一进来就先知道它**不是**
    什么，比事后从文档里补一句更实在。
    """
    components.section_title("关于账号体系")
    for line in disclosure.boundary_lines():
        st.markdown(f"- {line}")
    st.write("")
    components.show_notice(
        "演示环境请只绑定本机地址，不要把这个服务暴露到公网——"
        "注册是开放的，任何能访问到地址的人都能建号进入。",
        "warn",
    )
