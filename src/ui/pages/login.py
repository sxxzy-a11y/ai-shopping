"""登录页与注册页。

未登录时应用**只渲染这一页**（见 `app.py` 的入口短路），而且不加载任何数据：
`render()` 刻意不接受 `catalog` 参数——没有数据可用，也就无从查询
（spec `user-auth`：未登录不触发任何数据查询）。

视觉方向：Editorial Luxury——宋体大标题、非对称双栏、发丝线、
单一琥珀强调色，动效只保留「载入逐字点亮 + 错峰浮现」一个高光时刻。
"""

from __future__ import annotations

import streamlit as st

from src import accounts
from src.errors import ZhigouError, to_user_message
from src.ui import components, state

#: 当前处于「登录」还是「注册」。
_KEY_MODE = "zg_auth_mode"
_MODE_LOGIN = "login"
_MODE_REGISTER = "register"

#: 登录成功后的一次性过场标记。由登录页写入，由首页渲染前消费。
_KEY_TRANSITION = "zg_login_transition"


def render() -> None:
    """渲染登录页。**不接受 catalog**——未登录时不该有任何数据可查。"""
    # 入场动效只在本次会话第一次渲染时播放；提交表单的重跑不再重复
    fresh = not st.session_state.get("zg_login_entered")
    st.session_state["zg_login_entered"] = True

    if fresh:
        st.markdown(_LOGIN_VEIL, unsafe_allow_html=True)
    st.markdown(_LOGIN_FX, unsafe_allow_html=True)
    st.markdown(
        '<div class="zg-login-fx zg-login-enter"></div>' if fresh
        else '<div class="zg-login-fx"></div>',
        unsafe_allow_html=True,
    )
    st.markdown(_LOGIN_GLOW, unsafe_allow_html=True)

    # 非对称双栏：编辑式版面 56 / 44，宽度由 .block-container 收在 ~1120px
    left, right = st.columns([1.12, 0.88], gap="large")
    with left:
        st.markdown(_LOGIN_EDITORIAL, unsafe_allow_html=True)
    with right:
        mode = st.session_state.get(_KEY_MODE, _MODE_LOGIN)
        st.markdown(
            '<div class="zg-form-head">'
            + ("登录 / Sign in" if mode == _MODE_LOGIN else "注册 / Register")
            + "</div>",
            unsafe_allow_html=True,
        )
        if mode == _MODE_REGISTER:
            _render_register_form()
        else:
            _render_login_form()
        _render_mode_switch(mode)
        st.write("")
        components.caption("账号凭据仅保存在当前会话；刷新页面需重新登录。")

    # 横跨双栏的产品预览：借用 Neuralyn 的 dashboard mockup 结构，
    # 但换成本产品的「决策卡」，用演示数据，不查询真实 catalog。
    st.markdown(_LOGIN_DECISION, unsafe_allow_html=True)


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
    else:
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
  @keyframes zgReveal {
    from { clip-path: inset(0 0 100% 0); transform: translateY(12px); }
    to   { clip-path: inset(-10% -2% -50% -2%); transform: translateY(0); }
  }
  @keyframes zgCardIn {
    from { opacity: 0; transform: translateY(22px); }
    to   { opacity: 1; transform: none; }
  }
  @keyframes zgRule {
    from { transform: scaleX(0); }
    to   { transform: scaleX(1); }
  }
  @keyframes zgVeilOut {
    from { opacity: 1; }
    to   { opacity: 0; visibility: hidden; }
  }
  @keyframes zgBar {
    from { transform: scaleX(0); }
    to   { transform: scaleX(1); }
  }
  @keyframes zgBarFill {
    from { width: 0; }
  }
  @keyframes zgCharLit {
    0%   { color: #35312A; opacity: .32; text-shadow: none; }
    55%  { color: #FFD9A0; opacity: 1; text-shadow: 0 0 24px rgba(211, 146, 60, .55); }
    100% { color: #F2EEE4; opacity: 1; text-shadow: 0 0 10px rgba(211, 146, 60, .16); }
  }
  @keyframes zgDriftA {
    0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
    50%      { transform: translate3d(34px, -30px, 0) scale(1.08); }
  }
  @keyframes zgDriftB {
    0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
    50%      { transform: translate3d(-36px, 26px, 0) scale(1.06); }
  }

  /* ---------- 底色、颗粒、暗角 ---------- */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) {
    background:
      radial-gradient(1200px 560px at 82% -12%, rgba(211, 146, 60, .12), transparent 62%),
      radial-gradient(900px 480px at -8% 108%, rgba(242, 238, 228, .04), transparent 60%),
      #161511;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stHeader"] {
    background: transparent;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) .block-container {
    max-width: 1120px; padding-top: 4.2rem;
  }
  .zg-login-bg::before {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    opacity: .05; mix-blend-mode: overlay;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  }
  .zg-login-bg::after {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background: radial-gradient(120% 90% at 50% 45%, transparent 52%, rgba(0, 0, 0, .5) 100%);
  }

  /* ---------- 载入幕布：宋体大字 + 逐字点亮 ---------- */
  .zg-login-veil {
    position: fixed; inset: 0; z-index: 9999;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 18px; background: #161511;
    pointer-events: none;
    animation: zgVeilOut .45s ease 1.55s forwards;
  }
  .zg-login-veil-mark {
    display: flex; gap: 16px; padding-left: 16px;
    font-family: "Songti SC", "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", "宋体", serif;
    font-size: 46px; font-weight: 600; line-height: 1; color: #35312A;
    letter-spacing: 2px;
  }
  .zg-login-veil-mark span {
    display: inline-block; color: #35312A; opacity: .32;
    animation: zgCharLit .5s ease forwards;
  }
  .zg-login-veil-mark span:nth-child(1) { animation-delay: 0s; }
  .zg-login-veil-mark span:nth-child(2) { animation-delay: .29s; }
  .zg-login-veil-mark span:nth-child(3) { animation-delay: .58s; }
  .zg-login-veil-mark span:nth-child(4) { animation-delay: .87s; }
  .zg-login-veil-bar {
    width: 200px; height: 2px; border-radius: 2px;
    background: linear-gradient(90deg, #D3923C, #F0B35E);
    transform-origin: left;
    animation: zgBar 1.16s linear both;
  }

  /* ---------- 背景光斑 ---------- */
  .zg-login-bg { position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }
  .zg-login-bg span { position: absolute; display: block; border-radius: 999px; filter: blur(80px); opacity: .45; }
  .zg-login-bg span:nth-child(1) {
    width: 520px; height: 520px; right: 1%; top: 6%;
    background: radial-gradient(circle, rgba(211, 146, 60, .24), transparent 68%);
    animation: zgDriftA 24s ease-in-out infinite;
  }
  .zg-login-bg span:nth-child(2) {
    width: 440px; height: 440px; left: -6%; bottom: -4%;
    background: radial-gradient(circle, rgba(242, 238, 228, .05), transparent 70%);
    animation: zgDriftB 30s ease-in-out infinite;
  }

  /* ---------- 静态神经网络细线：借 Neuralyn 的意象，不用视频 ---------- */
  .zg-login-net {
    position: fixed; inset: 0; z-index: 0; pointer-events: none;
    opacity: .55; overflow: hidden;
  }
  .zg-login-net svg { width: 100%; height: 100%; display: block; }

  /* ---------- 左栏：编辑式版面 ---------- */
  .zg-editorial {
    position: relative; padding: 6px 44px 10px 2px;
    border-right: 1px solid rgba(242, 238, 228, .12);
    min-height: 520px;
    font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
  }
  .zg-ed-meta {
    display: flex; justify-content: space-between; align-items: baseline;
    padding-bottom: 12px; margin-bottom: 54px;
    border-bottom: 1px solid rgba(242, 238, 228, .14);
    font-size: 10px; letter-spacing: .26em; text-transform: uppercase;
    color: #7C766A;
  }
  .zg-ed-meta b { color: #D3923C; font-weight: 600; }
  .zg-ed-kicker {
    font-size: 10.5px; letter-spacing: .28em; text-transform: uppercase;
    color: #D3923C; margin-bottom: 20px;
  }
  .zg-editorial h1.zg-ed-title {
    margin: 0 0 26px 0; padding: 0; position: relative;
    font-family: "Songti SC", "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", "宋体", serif;
    font-size: 76px; font-weight: 600; line-height: .96;
    letter-spacing: -2px; color: #F4F0E6;
  }
  .zg-ed-title::after {
    content: ""; position: absolute; left: 2px; bottom: -22px;
    width: 92px; height: 2px;
    background: linear-gradient(90deg, #D3923C, rgba(240, 179, 94, .05));
    transform-origin: left;
  }
  .zg-ed-sub {
    margin: 44px 0 0 0; max-width: 410px;
    font-size: 15px; line-height: 1.95; color: #A79F90;
  }
  .zg-ed-sub em { color: #E9E3D6; font-style: normal; }
  .zg-ed-facts {
    display: flex; gap: 0; margin-top: 46px; max-width: 430px;
    border-top: 1px solid rgba(242, 238, 228, .10);
  }
  .zg-ed-facts div {
    flex: 1; padding: 14px 14px 0 0; margin-right: 14px;
    border-right: 1px solid rgba(242, 238, 228, .08);
  }
  .zg-ed-facts div:last-child { border-right: none; margin-right: 0; }
  .zg-ed-facts b {
    display: block; font-size: 11px; letter-spacing: .18em;
    text-transform: uppercase; color: #E9E3D6; font-weight: 600; margin-bottom: 6px;
  }
  .zg-ed-facts small { font-size: 11px; color: #7C766A; letter-spacing: .04em; }
  .zg-ed-foot {
    margin-top: 46px; font-size: 10px; letter-spacing: .22em;
    text-transform: uppercase; color: #6A655A;
  }

  /* ---------- 底部产品预览：决策卡 ---------- */
  .zg-decision {
    position: relative; overflow: hidden;
    margin: 30px 0 0 0; padding: 15px 20px 17px 20px;
    border: 1px solid rgba(242, 238, 228, .13);
    border-radius: 2px;
    background:
      radial-gradient(120% 200% at 0% 0%, rgba(211, 146, 60, .09), transparent 42%),
      linear-gradient(180deg, rgba(255, 255, 255, .045), rgba(255, 255, 255, .012));
    backdrop-filter: blur(18px) saturate(115%);
    -webkit-backdrop-filter: blur(18px) saturate(115%);
    box-shadow:
      0 26px 70px rgba(0, 0, 0, .34),
      inset 0 1px 0 rgba(255, 255, 255, .05);
    font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
  }
  .zg-decision::before {
    content: ""; position: absolute; left: 0; top: 0;
    width: 170px; height: 1px;
    background: linear-gradient(90deg, #D3923C, rgba(211, 146, 60, 0));
  }
  .zg-decision-top {
    display: flex; justify-content: space-between; align-items: baseline;
    padding-bottom: 10px; margin-bottom: 14px;
    border-bottom: 1px solid rgba(242, 238, 228, .09);
    font-size: 9.5px; letter-spacing: .24em; text-transform: uppercase;
    color: #7C766A;
  }
  .zg-decision-top em { font-style: normal; color: #D3923C; }
  .zg-decision-top .zg-decision-tag { letter-spacing: .12em; color: #6A655A; }
  .zg-decision-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.35fr) minmax(0, .55fr) minmax(0, 1.35fr) minmax(0, 1.05fr);
    gap: 22px; align-items: center;
  }
  .zg-decision-name {
    font-family: "Songti SC", "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", "宋体", serif;
    font-size: 17px; font-weight: 600; line-height: 1.25;
    color: #F4F0E6; letter-spacing: .01em;
  }
  .zg-decision-price {
    margin-top: 7px; font-size: 11.5px; letter-spacing: .04em; color: #A79F90;
  }
  .zg-decision-price b { color: #E9E3D6; font-weight: 600; font-size: 13px; }
  .zg-decision-score b {
    font-family: "Songti SC", "Noto Serif SC", "STSong", "SimSun", serif;
    font-size: 40px; font-weight: 600; line-height: .9; color: #D3923C;
  }
  .zg-decision-score span { font-size: 10px; color: #7C766A; margin-left: 4px; }
  .zg-decision-score small {
    display: block; margin-top: 6px; font-size: 9.5px;
    letter-spacing: .2em; text-transform: uppercase; color: #7C766A;
  }
  .zg-decision-bars { display: grid; gap: 7px; }
  .zg-dbar {
    display: grid; grid-template-columns: 52px minmax(0, 1fr) 24px;
    gap: 9px; align-items: center;
    font-size: 10px; letter-spacing: .06em; color: #9A9385;
  }
  .zg-dbar i {
    display: block; height: 3px; background: rgba(242, 238, 228, .10);
    border-radius: 2px; overflow: hidden;
  }
  .zg-dbar i em {
    display: block; height: 100%; width: 0;
    background: linear-gradient(90deg, #B57A2C, #E8AE5B);
    border-radius: 2px;
  }
  .zg-dbar b { font-weight: 500; color: #DCD4C5; text-align: right; font-variant-numeric: tabular-nums; }
  .zg-decision-verdict {
    padding-left: 17px; border-left: 1px solid rgba(242, 238, 228, .12);
  }
  .zg-decision-verdict small {
    display: block; font-size: 9.5px; letter-spacing: .22em;
    text-transform: uppercase; color: #7C766A; margin-bottom: 6px;
  }
  .zg-decision-verdict p { margin: 0; font-size: 12px; line-height: 1.7; color: #A79F90; }
  .zg-decision-verdict em { font-style: normal; color: #E9E3D6; white-space: nowrap; }

  /* ---------- 右栏：表单 ---------- */
  .zg-form-head {
    margin: 8px 0 22px 0;
    font-size: 10.5px; letter-spacing: .26em; text-transform: uppercase;
    color: #8C867A;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stForm"] {
    position: relative;
    background:
      radial-gradient(130% 120% at 50% -10%, rgba(211, 146, 60, .10), transparent 58%),
      linear-gradient(180deg, rgba(255, 255, 255, .055), rgba(255, 255, 255, .012));
    border: 1px solid rgba(242, 238, 228, .16);
    border-radius: 3px;
    padding: 24px 22px 10px 22px;
    backdrop-filter: blur(18px) saturate(118%);
    -webkit-backdrop-filter: blur(18px) saturate(118%);
    box-shadow:
      0 28px 70px rgba(0, 0, 0, .38),
      inset 0 1px 0 rgba(255, 255, 255, .07);
    overflow: hidden;
    transition: border-color .25s ease, background .25s ease, box-shadow .25s ease;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stForm"]::before {
    content: ""; position: absolute; left: 0; top: 0;
    width: 62%; height: 1px; pointer-events: none;
    background: linear-gradient(90deg, rgba(255, 255, 255, .30), rgba(255, 255, 255, 0));
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stForm"]:hover {
    border-color: rgba(211, 146, 60, .38);
    background:
      radial-gradient(130% 120% at 50% -10%, rgba(211, 146, 60, .13), transparent 58%),
      linear-gradient(180deg, rgba(255, 255, 255, .07), rgba(255, 255, 255, .018));
    box-shadow:
      0 30px 80px rgba(0, 0, 0, .42),
      inset 0 1px 0 rgba(255, 255, 255, .09);
  }
  @supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
    [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stForm"],
    .zg-decision {
      background: rgba(30, 28, 23, .94);
    }
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stForm"] label p {
    color: #8C867A; font-size: 10.5px;
    letter-spacing: .18em; text-transform: uppercase;
  }

  /* 下划线式输入框 */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"],
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"] > div,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"] > div > div {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"] {
    border-bottom: 1px solid rgba(242, 238, 228, .18) !important;
    box-shadow: none !important;
    transition: border-color .2s ease;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"]:focus-within {
    border-bottom: 1px solid #D3923C !important;
    box-shadow: none !important;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"] input {
    background: transparent !important;
    color: #F4F0E6 !important;
    caret-color: #D3923C;
    font-size: 15px; padding-left: 0 !important;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"] input::placeholder {
    color: #5E594F !important;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-baseweb="input"] button {
    background: transparent !important; color: #8C867A !important;
  }
  /* 隐藏 Edge 自带的密码显示按钮，只保留 Streamlit 的那一个 */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) input[type="password"]::-ms-reveal,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) input[type="password"]::-ms-clear {
    display: none;
  }

  /* 按钮 */
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primaryFormSubmit"],
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primary"] {
    background: #D3923C !important;
    border: 1px solid #D3923C !important;
    color: #1D1407 !important;
    font-weight: 600; letter-spacing: .14em;
    border-radius: 1px;
    transition: background .18s ease, transform .18s ease, box-shadow .18s ease;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primaryFormSubmit"]::after,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primary"]::after {
    content: "→"; margin-left: 12px; opacity: .7;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primaryFormSubmit"]:hover,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primary"]:hover {
    background: #E2A44C !important;
    transform: translateY(-1px);
    box-shadow: 0 12px 34px rgba(211, 146, 60, .22);
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primaryFormSubmit"]:active,
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-primary"]:active {
    transform: translateY(0); box-shadow: none;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-secondary"] {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    color: #A79F90 !important;
    letter-spacing: .1em;
    transition: color .18s ease;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-secondary"] p {
    text-decoration: underline; text-underline-offset: 5px;
    text-decoration-thickness: 1px;
    text-decoration-color: rgba(242, 238, 228, .22);
    transition: text-decoration-color .18s ease;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-secondary"]:hover {
    color: #F4F0E6 !important;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stBaseButton-secondary"]:hover p {
    text-decoration-color: #D3923C;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-fx) .zg-caption {
    color: #7A7466; font-size: 11px; letter-spacing: .03em;
  }

  /* ---------- 入场编排：左栏错峰，右栏随后 ---------- */
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-ed-meta {
    animation: zgFadeUp .55s cubic-bezier(.22, .61, .36, 1) both;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-ed-kicker {
    animation: zgFadeUp .55s .06s cubic-bezier(.22, .61, .36, 1) both;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-ed-title {
    animation: zgReveal .85s .10s cubic-bezier(.16, 1, .3, 1) both;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-ed-title::after {
    animation: zgRule .6s .55s cubic-bezier(.16, 1, .3, 1) both;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-ed-sub {
    animation: zgFadeUp .65s .3s cubic-bezier(.22, .61, .36, 1) both;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-ed-facts {
    animation: zgFadeUp .65s .4s cubic-bezier(.22, .61, .36, 1) both;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-ed-foot {
    animation: zgFadeUp .55s .48s cubic-bezier(.22, .61, .36, 1) both;
  }
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
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-decision {
    animation: zgCardIn .8s .56s cubic-bezier(.16, 1, .3, 1) both;
  }
  [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-dbar i em {
    animation: zgBarFill 1.1s .95s cubic-bezier(.16, 1, .3, 1) both;
  }

  /* ---------- 窄屏：单栏，去掉竖线 ---------- */
  @media (max-width: 900px) {
    .zg-editorial { border-right: none; padding-right: 2px; min-height: 0; }
    .zg-editorial h1.zg-ed-title { font-size: 52px; }
    .zg-decision { margin-top: 26px; }
    .zg-decision-grid {
      grid-template-columns: minmax(0, 1.2fr) minmax(0, .5fr) minmax(0, 1.2fr);
    }
    .zg-decision-verdict {
      grid-column: 1 / -1; padding: 12px 0 0 0;
      border-left: none; border-top: 1px solid rgba(242, 238, 228, .10);
    }
  }

  @media (max-width: 760px) {
    [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stHorizontalBlock"]:has(.zg-editorial) {
      flex-wrap: wrap;
    }
    [data-testid="stAppViewContainer"]:has(.zg-login-fx) [data-testid="stHorizontalBlock"]:has(.zg-editorial) > [data-testid="stColumn"] {
      flex: 1 1 100% !important;
      width: 100% !important;
      min-width: 100% !important;
    }
    .zg-editorial h1.zg-ed-title { font-size: 46px; }
    .zg-ed-meta { margin-bottom: 34px; }
    .zg-decision { padding: 14px 16px 16px 16px; }
    .zg-decision-grid {
      grid-template-columns: minmax(0, 1fr) auto;
      row-gap: 14px;
    }
    .zg-decision-bars, .zg-decision-verdict { grid-column: 1 / -1; }
  }

  /* ---------- 无障碍 ---------- */
  @media (prefers-reduced-motion: reduce) {
    .zg-login-veil, .zg-login-veil-mark span, .zg-login-veil-bar, .zg-login-bg span,
    .zg-ed-meta, .zg-ed-kicker, .zg-ed-title, .zg-ed-sub, .zg-ed-facts, .zg-ed-foot,
    .zg-form-head, .zg-decision,
    [data-testid="stAppViewContainer"]:has(.zg-login-enter) [data-testid="stForm"],
    [data-testid="stAppViewContainer"]:has(.zg-login-enter) .stButton,
    [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-dbar i em,
    [data-testid="stAppViewContainer"]:has(.zg-login-enter) .zg-caption {
      animation: none !important; transition: none !important;
    }
    .zg-login-veil { display: none; }
    .zg-login-veil-mark span { color: #F4F0E6; opacity: 1; text-shadow: none; }
  }
</style>
"""

_LOGIN_VEIL = """
<div class="zg-login-veil" aria-hidden="true">
  <div class="zg-login-veil-mark" aria-label="智购参谋">
    <span>智</span><span>购</span><span>参</span><span>谋</span>
  </div>
  <span class="zg-login-veil-bar"></span>
</div>
"""

_LOGIN_GLOW = """
<div class="zg-login-bg" aria-hidden="true"><span></span><span></span></div>
<div class="zg-login-net" aria-hidden="true">
  <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
    <g fill="none" stroke="#F2EEE4" stroke-opacity=".10" stroke-width="1">
      <path d="M1030 100 L1140 150 L1210 230 L1300 390"/>
      <path d="M1140 150 L1070 245 L1180 330 L1240 470"/>
      <path d="M1210 230 L1180 330 L1300 390"/>
      <path d="M1070 245 L980 205"/>
      <path d="M60 720 L160 660 L220 760 L330 700 L390 800"/>
      <path d="M160 660 L330 700"/>
      <path d="M220 760 L390 800"/>
    </g>
    <g fill="#D3923C" fill-opacity=".55">
      <circle cx="1030" cy="100" r="2.4"/><circle cx="1140" cy="150" r="2.4"/>
      <circle cx="1210" cy="230" r="2.4"/><circle cx="1300" cy="390" r="2.4"/>
      <circle cx="1070" cy="245" r="2.4"/><circle cx="1180" cy="330" r="2.4"/>
      <circle cx="1240" cy="470" r="2.4"/><circle cx="980" cy="205" r="2.4"/>
      <circle cx="60" cy="720" r="2.4"/><circle cx="160" cy="660" r="2.4"/>
      <circle cx="220" cy="760" r="2.4"/><circle cx="330" cy="700" r="2.4"/>
      <circle cx="390" cy="800" r="2.4"/>
    </g>
  </svg>
</div>
"""

_LOGIN_EDITORIAL = """
<div class="zg-editorial">
  <div class="zg-ed-meta">
    <span><b>SmartBuy</b> — 01</span>
    <span>AI Consumer Intelligence</span>
  </div>
  <div class="zg-ed-kicker">基于 AI 的消费决策助手</div>
  <h1 class="zg-ed-title">智购参谋</h1>
  <p class="zg-ed-sub">
    登录后使用。没有账号可以直接注册一个，注册得到的都是普通用户。
    我们把<em>预算与真实需求</em>放在第一位，每个结论都能追溯到具体数据。
  </p>
  <div class="zg-ed-facts">
    <div><b>可解释</b><small>评分逐项摊开</small></div>
    <div><b>可追溯</b><small>来源与更新时间</small></div>
    <div><b>本地运行</b><small>数据不出本机</small></div>
  </div>
  <div class="zg-ed-foot">SmartBuy · 消费决策，不卖货</div>
</div>
"""

_LOGIN_DECISION = """
<section class="zg-decision" aria-label="决策预览">
  <div class="zg-decision-top">
    <span>决策预览 <em>/ Decision 01</em></span>
    <span class="zg-decision-tag">演示数据 · 可追溯</span>
  </div>
  <div class="zg-decision-grid">
    <div class="zg-decision-product">
      <div class="zg-decision-name">联想 小新Pro14 2024 锐龙版</div>
      <div class="zg-decision-price"><b>¥5,199</b> · 14 英寸 · 1.46 kg</div>
    </div>
    <div class="zg-decision-score">
      <b>86</b><span>/ 100</span>
      <small>综合分</small>
    </div>
    <div class="zg-decision-bars">
      <div class="zg-dbar"><span>预算匹配</span><i><em style="width:92%"></em></i><b>92</b></div>
      <div class="zg-dbar"><span>性能匹配</span><i><em style="width:88%"></em></i><b>88</b></div>
      <div class="zg-dbar"><span>便携程度</span><i><em style="width:74%"></em></i><b>74</b></div>
    </div>
    <div class="zg-decision-verdict">
      <small>结论</small>
      <p>在 5,000 元档里，<em>性能与便携最均衡</em>；重度游戏需要再上一档。</p>
    </div>
  </div>
</section>
"""

#: 登录成功后的全屏过场。深色渐变先把白底工作台盖住，再淡出；
#: `pointer-events: none` 保证过场期间不会拦住任何操作。
_LOGIN_TRANSITION = """
<style>
  @keyframes zgLoginEnterOut {
    0%   { opacity: 1; }
    68%  { opacity: 1; }
    100% { opacity: 0; visibility: hidden; }
  }
  @keyframes zgLoginEnterLine {
    from { transform: scaleX(0); }
    to   { transform: scaleX(1); }
  }
  @keyframes zgLoginEnterSheen {
    0%   { transform: translateX(-45%) rotate(7deg); opacity: 0; }
    35%  { opacity: .55; }
    100% { transform: translateX(45%) rotate(7deg); opacity: 0; }
  }

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
  .zg-login-transition-mark {
    font-family: "Songti SC", "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", "宋体", serif;
    font-size: 40px; font-weight: 600; letter-spacing: .14em;
    color: #F4F0E6; text-shadow: 0 0 30px rgba(211, 146, 60, .16);
  }
  .zg-login-transition-line {
    display: block; width: 64px; height: 2px; margin: 19px auto 15px;
    background: linear-gradient(90deg, rgba(211, 146, 60, 0), #D3923C, rgba(211, 146, 60, 0));
    transform-origin: center;
    animation: zgLoginEnterLine .55s cubic-bezier(.16, 1, .3, 1) .2s both;
  }
  .zg-login-transition-sub {
    font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 10px; letter-spacing: .28em; text-transform: uppercase;
    color: #8C867A;
  }

  /* 登录换页的瞬间，DOM 里会短暂残留登录页内容；过场期间先把它藏掉，
     免得渐变淡出时露出「侧栏 + 旧登录页」的中间态。 */
  [data-testid="stAppViewContainer"]:has(.zg-login-transition) [data-testid="stHorizontalBlock"]:has(.zg-editorial),
  [data-testid="stAppViewContainer"]:has(.zg-login-transition) .zg-decision,
  [data-testid="stAppViewContainer"]:has(.zg-login-transition) .zg-login-bg,
  [data-testid="stAppViewContainer"]:has(.zg-login-transition) .zg-login-net {
    display: none !important;
  }

  @media (prefers-reduced-motion: reduce) {
    .zg-login-transition { display: none !important; }
  }
</style>
<div class="zg-login-transition" aria-hidden="true">
  <div class="zg-login-transition-inner">
    <div class="zg-login-transition-mark">登录成功</div>
    <span class="zg-login-transition-line"></span>
    <div class="zg-login-transition-sub">正在进入智购参谋</div>
  </div>
</div>
"""
