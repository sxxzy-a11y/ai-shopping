"""智购参谋 —— 应用入口。

本文件只做五件事：页面配置、样式注入、数据加载、侧栏导航、异常兜底。
**不放任何业务逻辑**——筛选、评分、比较、偏好都在 `src/` 下的模块里。

启动：
    streamlit run app.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import streamlit as st

from src import accounts, config, settings
from src.auth import User, is_admin
from src.errors import ZhigouError, to_user_message
from src.ui import components, icons, state, theme
from src.ui.pages import (
    about,
    admin,
    analysis,
    catalog_admin,
    compare,
    history,
    home,
    knowledge,
    knowledge_admin,
    login,
    settings as settings_page,
)


@dataclass(frozen=True)
class NavItem:
    """一个导航项。

    `admin_only` 是**界面层的可见性**，不是权限本身——权限判定在数据层入口
    （design D3）。这里只是让普通用户看不到自己用不了的入口。
    """

    name: str
    icon: str
    renderer: callable
    admin_only: bool = False


#: 导航项。图标走 Streamlit 官方的 `icon=` 参数，这是最稳的接入方式。
NAV_ITEMS: list[NavItem] = [
    NavItem("首页", ":material/home:", home.render),
    NavItem("智能分析", ":material/insights:", analysis.render),
    NavItem("商品比较", ":material/view_column:", compare.render),
    NavItem("AI 问答", ":material/chat:", knowledge.render),
    NavItem("历史记录", ":material/history:", history.render),
    # 管理员专属。`admin_only` 控制的是**界面可见性**，不是权限本身——
    # 页面入口有一道 `require_admin`，数据层写入口还有一道（design D3）。
    NavItem("用户管理", ":material/group:", admin.render_users, admin_only=True),
    NavItem("全站概览", ":material/analytics:", admin.render_overview, admin_only=True),
    NavItem(
        "商品维护", ":material/inventory_2:", catalog_admin.render, admin_only=True
    ),
    NavItem(
        "知识库管理", ":material/library_books:", knowledge_admin.render, admin_only=True
    ),
    # 「个人设置」紧挨「项目说明」放在最末两位：它是低频操作，
    # 且对两种角色都稳定地出现在同一个位置（管理项只影响中间段）。
    NavItem("个人设置", ":material/tune:", settings_page.render),
    NavItem("关于", ":material/info:", about.render),
]

PAGES: dict[str, callable] = {item.name: item.renderer for item in NAV_ITEMS}

logger = logging.getLogger("zhigou")


def _visible_nav(user: User | None) -> list[NavItem]:
    """当前角色看得到的导航项。"""
    return [
        item for item in NAV_ITEMS if not item.admin_only or is_admin(user)
    ]


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


def _render_sidebar(user: User) -> str:
    """渲染侧栏并返回当前页面名。

    导航用 `st.button` 而不是 `st.radio`：按钮能拿到官方的 `type="primary"`
    选中态（颜色来自 config.toml 的 primaryColor），不用去覆盖 Streamlit
    的单选控件内部结构。
    """
    active = state.current_page()

    with st.sidebar:
        _render_brand()

        for item in _visible_nav(user):
            is_active = item.name == active
            if st.button(
                item.name,
                key=f"nav_{item.name}",
                icon=item.icon,
                type="primary" if is_active else "secondary",
                width="stretch",
            ):
                state.request_page(item.name)
                st.rerun()

        st.divider()

        st.markdown(
            f'<div style="padding:0 2px">'
            f'  <div style="font-size:11.5px;color:{theme.SIDEBAR_MUTED};'
            f'letter-spacing:.4px;margin-bottom:5px">当前账号</div>'
            f'  <div style="font-size:13.5px;font-weight:600;color:#fff;'
            f'margin-bottom:4px">{user.username}</div>'
            f'  <div style="font-size:11.5px;color:{theme.SIDEBAR_MUTED}">'
            f"{user.role_label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button("登出", icon=":material/logout:", width="stretch"):
            state.sign_out()
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
            f"</div>",
            unsafe_allow_html=True,
        )

        st.divider()

        st.markdown(
            f'<div style="font-size:11.5px;color:{theme.SIDEBAR_MUTED};'
            f'line-height:1.75;padding:0 2px">'
            f"商品数据来自公开资料整理：品牌与型号真实，"
            f"价格是采集时的参考价、<strong style=\"color:{theme.ON_NAVY}\">不是实时价格</strong>，"
            f"参数经简化且<strong style=\"color:{theme.ON_NAVY}\">未核验</strong>。<br><br>"
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


@st.cache_resource(show_spinner=False)
def _bootstrap_once() -> None:
    """进程启动时**只跑一次**的两件事，都是幂等的。

    用 `cache_resource` 而不是每次重跑：其中一件会写库，而 Streamlit
    每次交互都会重跑整个脚本。

    1. 把单用户时期的 `storage/settings.json` 收编成「新用户初始偏好模板」（任务 2.9）
    2. 账号表为空时创建初始管理员（任务 11.x）
    """
    try:
        settings.adopt_legacy_settings_file()
    except ZhigouError as exc:
        logger.warning("旧偏好文件收编失败: %s", exc.detail or exc)

    try:
        created = accounts.ensure_initial_admin()
    except ZhigouError as exc:
        # 建号失败不该让应用起不来：没有账号时用户仍能注册（第一个注册者
        # 拿到的是普通用户，不是管理员）。
        logger.warning("初始管理员创建失败: %s", exc.detail or exc)
        return

    if created is None:
        return

    _admin, notice = created
    if notice:
        # **打印一次**，而且只打在启动终端上：这段输出里可能有刚生成的
        # 明文密码，进日志文件就等于把它留在磁盘上了。
        try:
            print("\n" + "=" * 68)
            print(notice)
            print("=" * 68 + "\n")
        except UnicodeEncodeError:
            # 控制台编码容不下这些字符时（Windows 上不罕见），放宽容错再打一遍。
            # **不能让打印失败把首次启动整个掀掉**：密码只在这一刻有明文，
            # 崩溃就等于它从没露过面，而账号已经建好了——只剩重置一条路。
            # 容错模式下中文会变成「?」，但密码本身是纯 ASCII，抄得下来。
            import sys

            sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
            print("\n" + "=" * 68)
            print(notice)
            print("=" * 68 + "\n")


def main() -> None:
    st.set_page_config(
        page_title="智购参谋 · AI 消费决策助手",
        page_icon="◆",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _configure_logging()
    theme.inject_styles()
    _bootstrap_once()

    user = state.current_user()
    if user is None:
        # **入口短路**：未登录时只渲染登录页并立即返回。
        # 位置很要紧——下面的 `state.get_catalog()` 走不到了，
        # 「未登录不触发任何数据查询」由这个 return 保证（任务 4.1、4.5）。
        login.render()
        return

    # 账号可能已经在别处被停用或删除（管理员在另一个标签页操作）。
    # `require_admin` 与 `current_user` 都只看**会话里那个对象**，不查库——
    # 所以这里每轮查一次库：失效就登出，不让一个已经不存在的账号继续操作。
    # 开销是一次本地查询；库读不出来时 `still_valid` 按「仍然有效」处理，
    # 免得一个只读故障把所有人踢出去。
    if not accounts.still_valid(user):
        state.sign_out()
        components.show_notice(
            "你的账号已被停用或删除，请重新登录。", "warn"
        )
        login.render()
        return

    page = _render_sidebar(user)
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
