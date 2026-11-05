"""登录页与注册页。

未登录时应用**只渲染这一页**（见 `app.py` 的入口短路），而且不加载任何数据：
`render()` 刻意不接受 `catalog` 参数——没有数据可用，也就无从查询
（spec `user-auth`：未登录不触发任何数据查询）。

视觉方向：Editorial Luxury——宋体大标题、非对称双栏、发丝线、
单一琥珀强调色，动效只保留「三球载入 + 错峰浮现」一个高光时刻。
"""

from __future__ import annotations

import streamlit as st

from src import accounts, config
from src.errors import ZhigouError, to_user_message
from src.ui import components, state
from src.ui.loader import LOADER_CSS, loader_markup

#: 当前处于「登录」还是「注册」。
_KEY_MODE = "zg_auth_mode"
_MODE_LOGIN = "login"
_MODE_REGISTER = "register"

#: 登录成功后的一次性过场标记。由登录页写入，由首页渲染前消费。
_KEY_TRANSITION = "zg_login_transition"

#: 卡片里的两行标题（原组件 "Welcome, sign in to continue" 的位置）
_HEAD_LOGIN = '<div class="zg-form-head"><b>欢迎回来</b><span>登录以继续</span></div>'
_HEAD_REGISTER = '<div class="zg-form-head"><b>创建账号</b><span>注册后即可使用</span></div>'


def render() -> None:
    """渲染登录页。**不接受 catalog**——未登录时不该有任何数据可查。"""
    # 入场动效只在本次会话第一次渲染时播放；提交表单的重跑不再重复。
    #
    # 注意：幕布元素**每次都要发**，不是首帧才发。上一次渲染多一个元素、这次少一个，
    # Streamlit 按序号对不齐，会把整块内容错位复用——云上重连触发重跑时，
    # 页面上就会冒出第二份登录页，而且是从页脚开始、顺序还错了一位。
    fresh = not st.session_state.get("zg_login_entered")
    st.session_state["zg_login_entered"] = True

    st.markdown(_LOGIN_VEIL if fresh else _LOGIN_VEIL_OFF, unsafe_allow_html=True)
    st.markdown(_LOGIN_FX, unsafe_allow_html=True)
    st.markdown(
        '<div class="zg-login-fx zg-login-enter"></div>' if fresh
        else '<div class="zg-login-fx"></div>',
        unsafe_allow_html=True,
    )

    mode = st.session_state.get(_KEY_MODE, _MODE_LOGIN)
    if mode == _MODE_REGISTER and not config.allow_registration():
        mode = _MODE_LOGIN
        st.session_state[_KEY_MODE] = _MODE_LOGIN

    # 页面只剩一张居中的卡：品牌行、表单、注册入口
    st.markdown(
        '<div class="zg-brandline"><b>智购参谋</b><span>SMARTBUY</span></div>',
        unsafe_allow_html=True,
    )
    if mode == _MODE_REGISTER:
        _render_register_form()
    else:
        _render_login_form()
    _render_mode_switch(mode)
    if mode == _MODE_REGISTER:
        components.caption(
            "注册得到的账号一律是普通用户。管理员权限只能由现有管理员授予——"
            "不设「第一个注册的人自动成为管理员」这种规则。"
        )
    components.caption("账号凭据仅保存在当前会话；刷新页面需重新登录。")


def render_login_transition() -> None:
    """登录成功后的暖色渐变过场。

    在 `app.py` 里、绘制侧栏和页面之前调用：新页面先铺满登录页同色系的
    深色渐变，再淡出到首页，避免从登录页直接切到白底工作台。
    只消费一次标记，后续页面切换不会重播。
    """
    if not st.session_state.pop(_KEY_TRANSITION, False):
        return
    st.markdown(_LOGIN_TRANSITION, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 登录
# --------------------------------------------------------------------------


def _sign_in(user) -> None:
    """登录成功后的落库动作：记当前用户、把页面送到首页、整页重跑。"""
    state.set_current_user(user)
    state.request_page(state.DEFAULT_PAGE)
    st.session_state[_KEY_TRANSITION] = True
    st.rerun()


def _render_login_form() -> None:
    with st.form("zg_login"):
        st.markdown(_HEAD_LOGIN, unsafe_allow_html=True)
        username = st.text_input("用户名", key="zg_login_username")
        password = st.text_input("密码", type="password", key="zg_login_password")
        submitted = st.form_submit_button("登录", type="primary", width="stretch")

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
    if not config.allow_registration():
        return

    with st.form("zg_register"):
        st.markdown(_HEAD_REGISTER, unsafe_allow_html=True)
        username = st.text_input("用户名", key="zg_reg_username")
        password = st.text_input(
            "密码", type="password", key="zg_reg_password", help="至少 8 位"
        )
        confirm = st.text_input("确认密码", type="password", key="zg_reg_confirm")
        submitted = st.form_submit_button("注册", type="primary", width="stretch")

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
        if st.button("已有账号，去登录", width="stretch"):
            st.session_state[_KEY_MODE] = _MODE_LOGIN
            st.rerun()
    elif config.allow_registration():
        if st.button("没有账号？注册一个", width="stretch"):
            st.session_state[_KEY_MODE] = _MODE_REGISTER
            st.rerun()


# --------------------------------------------------------------------------
# 视觉：Editorial Luxury
# --------------------------------------------------------------------------

_LOGIN_FX = """
<style>
  /* ---------- 关键帧 ---------- */
  @keyframes zgFadeUp {
    from { opacity: 0; transform: translateY(16px); filter: blur(4px); }
    to   { opacity: 1; transform: translateY(0); filter: none; }
  }
  @keyframes zgCardIn {
    from { opacity: 0; transform: translateY(22px); }
    to   { opacity: 1; transform: none; }
  }
  @keyframes zgVeilOut {
    from { opacity: 1; }
    to   { opacity: 0; visibility: hidden; }
  }
  /* ---------- 底色 ---------- */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) {
    background:
      radial-gradient(900px 480px at 84% -16%, rgba(211, 146, 60, .16), transparent 64%),
      #EDE9DF;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stHeader"] {
    background: transparent;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) .block-container {
    max-width: 420px; margin: 0 auto;
    /* Streamlit 默认左右各留 80px，卡片会被挤成一条 —— 这里只留一点安全边距 */
    padding: 12vh 10px 6vh 10px;
  }
  /* 登录页只剩一列：让这一列吃满容器，卡片才不是一条窄边 */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
    width: 100% !important;
  }
  /* Streamlit 会在 form 输入框里挂一句 "Press Enter to submit form"。
     深色输入框上它是黑字，还正好压在输入框中间，看起来像一层重影。 */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="InputInstructions"] {
    display: none;
  }

  /* ---------- 载入幕布：三球弹跳 + 品牌字 ---------- */
  .zg-login-veil {
    position: fixed; inset: 0; z-index: 9999;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 26px; background: #EDE9DF;
    pointer-events: none;
    animation: zgVeilOut .16s ease 1.02s forwards;
  }
  .zg-login-veil-word {
    font-family: "Songti SC", "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", "宋体", serif;
    font-size: 26px; font-weight: 600; line-height: 1;
    letter-spacing: .18em; padding-left: .18em;
    color: #161511; opacity: .92;
  }

  /* 卡上方的两行标题：宋体主句 + 一行小字说明 */
  .zg-form-head { margin: 0 0 14px 0; color: #161511; }
  .zg-form-head b {
    display: block;
    font-family: "Songti SC", "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", "宋体", serif;
    font-size: 26px; font-weight: 600; line-height: 1.3; letter-spacing: .04em;
  }
  .zg-form-head span {
    display: block; margin-top: 7px;
    font-size: 11px; letter-spacing: .18em; text-transform: uppercase;
    color: #6F6A5E;
  }
  /* 卡片上方的品牌行 */
  .zg-brandline {
    display: flex; align-items: baseline; justify-content: space-between;
    margin: 0 4px 12px 4px;
    color: #161511;
  }
  .zg-brandline b {
    font-family: "Songti SC", "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", "宋体", serif;
    font-size: 17px; font-weight: 600; letter-spacing: .12em;
  }
  .zg-brandline span {
    font-size: 9.5px; letter-spacing: .3em; text-transform: uppercase;
    color: #B8791F;
  }

  /* ---------- 右栏：表单 ----------
     卡片语言来自 Uiverse / D3OXY「short-panther-37」：2px 实描边 + 不带模糊的
     硬投影，hover 时实心填充从左侧扫过。原版是灰卡黑线白底，这里换成纸色卡 +
     墨线 + 品牌金，落在深色页面上是一张「贴上去」的卡。 */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stForm"] {
    position: relative;
    width: 100% !important;
    background: #E4DDCE;
    border: 2px solid #161511;
    border-radius: 6px;
    padding: 22px 20px 14px 20px;
    margin: 0 0 14px 0;
    box-shadow: 8px 8px 0 #161511;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stForm"] label p {
    color: #4A4338; font-size: 10.5px;
    letter-spacing: .18em; text-transform: uppercase;
  }

  /* 盒式输入框：描边 + 硬投影，聚焦时整体「按下去」2px */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"],
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stTextInputRootElement"] {
    background: #FFFDF8 !important;
    border: 2px solid #161511 !important;
    border-radius: 5px !important;
    box-shadow: 3px 3px 0 #161511 !important;
    transition: box-shadow .16s ease, transform .16s ease;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"]:focus-within,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stTextInputRootElement"]:focus-within {
    border-color: #161511 !important;
    box-shadow: 1px 1px 0 #161511 !important;
    transform: translate(2px, 2px);
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"] > div,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"] > div > div {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"] input,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stTextInputRootElement"] input {
    background: transparent !important;
    color: #161511 !important;
    caret-color: #B8791F;
    font-size: 15px; font-weight: 600;
    padding-left: 4px !important;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"] input::placeholder,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stTextInputRootElement"] input::placeholder {
    color: #A79F90 !important;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"] button,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stTextInputRootElement"] button {
    background: transparent !important; color: #6F6A5E !important;
  }
  /* 隐藏 Edge 自带的密码显示按钮，只保留 Streamlit 的那一个 */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) input[type="password"]::-ms-reveal,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) input[type="password"]::-ms-clear {
    display: none;
  }

  /* 按钮：2px 墨线 + 硬投影；hover 时实心填充从左扫过（原组件的招牌动效） */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primaryFormSubmit"],
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primary"] {
    position: relative; overflow: hidden; z-index: 1;
    background: #D3923C !important;
    border: 2px solid #161511 !important;
    border-radius: 5px !important;
    box-shadow: 4px 4px 0 #161511 !important;
    color: #161511 !important;
    font-weight: 700; letter-spacing: .12em;
    transition: color .2s ease, transform .12s ease, box-shadow .12s ease;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primaryFormSubmit"]::before,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primary"]::before {
    content: ""; position: absolute; left: 0; top: 0; height: 100%; width: 0;
    background: #161511; z-index: -1;
    transition: width .26s cubic-bezier(.22, .61, .36, 1);
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primaryFormSubmit"]::after,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primary"]::after {
    content: "→"; margin-left: 12px; opacity: .7;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primaryFormSubmit"]:hover,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primary"]:hover {
    color: #F2EEE4 !important;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primaryFormSubmit"]:hover::before,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primary"]:hover::before {
    width: 100%;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primaryFormSubmit"]:active,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primary"]:active {
    transform: translate(3px, 3px);
    box-shadow: 1px 1px 0 #161511 !important;
  }
  /* 次操作（登录 ⇄ 注册）是卡片外的一句链接，不要抢主按钮的注意力 */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-secondary"] {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    color: #6F6A5E !important;
    letter-spacing: .1em;
    transition: color .18s ease;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-secondary"] p {
    text-decoration: underline; text-underline-offset: 5px;
    text-decoration-thickness: 1px;
    text-decoration-color: rgba(22, 21, 17, .25);
    transition: text-decoration-color .18s ease;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-secondary"]:hover {
    color: #161511 !important;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-secondary"]:hover p {
    text-decoration-color: #D3923C;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) .zg-caption {
    color: #6F6A5E; font-size: 11px; letter-spacing: .03em;
    text-align: center;
  }

  /* ---------- 入场编排：左栏错峰，右栏随后 ---------- */
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-form-head {
    animation: zgFadeUp .5s .2s cubic-bezier(.22, .61, .36, 1) both;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) [data-testid="stForm"] {
    animation: zgCardIn .7s .3s cubic-bezier(.16, 1, .3, 1) both;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .stButton {
    animation: zgFadeUp .55s .42s cubic-bezier(.22, .61, .36, 1) both;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-caption {
    animation: zgFadeUp .55s .5s cubic-bezier(.22, .61, .36, 1) both;
  }

  /* ---------- 无障碍 ---------- */
  @media (prefers-reduced-motion: reduce) {
    .zg-login-veil,
    .zg-form-head,
    [data-testid="stAppViewContainer"]:has(.zg-login-enter) [data-testid="stForm"],
    [data-testid="stAppViewContainer"]:has(.zg-login-enter) .stButton,
    [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-caption {
      animation: none !important; transition: none !important;
    }
    .zg-login-veil { display: none; }
  }
</style>
"""

#: 首次进场幕布：三球弹跳 + 品牌字。球和页面内载入共用一份样式（src/ui/loader.py）。
_LOGIN_VEIL = (
    f"<style>{LOADER_CSS}</style>"
    '<div class="zg-login-veil" aria-hidden="true">'
    + loader_markup()
    + '<div class="zg-login-veil-word">智购参谋</div>'
    "</div>"
)

#: 重跑时用的空幕布：元素还在（保证每次渲染的元素个数一样），只是不显示。
_LOGIN_VEIL_OFF = (
    '<div class="zg-login-veil" style="display:none" aria-hidden="true"></div>'
)

#: 登录成功后的全屏过场：深色渐变先盖住工作台，中间是三颗交替弹跳的小球
#: （Uiverse / mobinkakei「grumpy-turtle-41」的节奏，配色改成品牌金），
#: 约 1.5s 后淡出。`pointer-events: none` 保证过场期间不会拦住操作。
_LOGIN_TRANSITION = (
    """
<style>
  @keyframes zgLoginEnterOut {
    0%   { opacity: 1; }
    68%  { opacity: 1; }
    100% { opacity: 0; visibility: hidden; }
  }
  @keyframes zgLoginEnterSheen {
    0%   { transform: translateX(-45%) rotate(7deg); opacity: 0; }
    35%  { opacity: .55; }
    100% { transform: translateX(45%) rotate(7deg); opacity: 0; }
  }
"""
    # 三球弹跳和页面内载入共用一份（src/ui/loader.py），改颜色或尺寸只改那里
    + LOADER_CSS
    + """
  .zg-login-transition {
    position: fixed; inset: 0;
    z-index: 2147483647;
    display: flex; align-items: center; justify-content: center;
    overflow: hidden; pointer-events: none;
    background:
      radial-gradient(65% 55% at 68% 36%, rgba(211, 146, 60, .20), transparent 66%),
      linear-gradient(135deg, #161511 0%, #1B1813 52%, #241C12 100%);
    animation: zgLoginEnterOut 1.5s cubic-bezier(.22, .61, .36, 1) .1s forwards;
  }
  .zg-login-transition::before {
    content: ""; position: absolute; inset: -25%;
    background: linear-gradient(
      112deg,
      transparent 34%,
      rgba(242, 238, 228, .055) 45%,
      rgba(211, 146, 60, .15) 51%,
      transparent 64%
    );
    transform: translateX(-45%) rotate(7deg);
    animation: zgLoginEnterSheen 1.05s ease-out .1s both;
  }
  .zg-login-transition-inner {
    position: relative; z-index: 1; text-align: center;
  }
  .zg-login-transition-sub {
    font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 10px; letter-spacing: .28em; text-transform: uppercase;
    color: #8C867A;
    margin-top: 10px;
  }

  /* 登录换页的瞬间，DOM 里会短暂残留登录页内容；过场期间先把它藏掉，
     免得渐变淡出时露出「侧栏 + 旧登录卡」的中间态。 */
  [data-testid="stAppViewContainer"]:has(.zg-login-transition) .zg-brandline,
  [data-testid="stAppViewContainer"]:has(.zg-login-transition) [data-testid="stForm"] {
    visibility: hidden;
  }

  @media (prefers-reduced-motion: reduce) {
    .zg-login-transition { display: none !important; }
  }
</style>
<div class="zg-login-transition" aria-hidden="true">
  <div class="zg-login-transition-inner">
"""
    + loader_markup()
    + """
    <div class="zg-login-transition-sub">正在进入智购参谋</div>
  </div>
</div>
"""
)
