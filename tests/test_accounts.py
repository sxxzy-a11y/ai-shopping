"""账号动作层的测试：注册、凭据校验、初始管理员引导。

对应任务 3.8 与 11.4。这一层不碰 Streamlit，所以「谁能登录」「第一个
注册者拿到什么角色」可以直接断言，不必先跑起一个应用。

跑测试时管理员环境变量已被隔离夹具清掉（见 conftest），
所以这里的用例结果不依赖开发机的 `.env`。
"""

from __future__ import annotations

import inspect
import re

import pytest

from src import accounts, config, database
from src.auth import ROLE_ADMIN, ROLE_USER, User
from src.errors import (
    InvalidCredentials,
    InvalidUsername,
    LastAdminProtected,
    PermissionDenied,
    UsernameTaken,
    WeakPassword,
)

PASSWORD = "good-pass-1"

#: 守卫只看 `viewer` 这个对象本身，所以这两个常量足够表达「谁在调用」。
REGULAR = User(username="lisi", role=ROLE_USER)
ADMIN = User(username="root", role=ROLE_ADMIN)


# --------------------------------------------------------------------------
# 注册
# --------------------------------------------------------------------------


def test_register_creates_a_regular_user():
    user = accounts.register("lisi", PASSWORD)

    assert user.username == "lisi"
    assert user.role == ROLE_USER, "自助注册只能是普通用户"
    assert user.is_active is True


def test_register_has_no_way_to_choose_a_role():
    """**注册函数压根没有 `role` 参数。**

    比「传进来会被忽略」更彻底：调用方连表达「我要注册成管理员」的机会
    都没有，所以也就不存在「哪条路径忘了过滤角色参数」这种漏法（任务 3.5）。
    """
    assert "role" not in inspect.signature(accounts.register).parameters


def test_register_rejects_a_taken_username():
    accounts.register("lisi", PASSWORD)

    with pytest.raises(UsernameTaken) as caught:
        accounts.register("lisi", "another-pass-1")

    assert "lisi" in caught.value.user_message


def test_register_rejects_a_short_password():
    with pytest.raises(WeakPassword):
        accounts.register("lisi", "short")


def test_register_rejects_a_username_with_spaces():
    with pytest.raises(InvalidUsername):
        accounts.register("li si", PASSWORD)


def test_registered_password_is_verifiable_but_not_stored_in_the_clear():
    accounts.register("lisi", PASSWORD)

    stored = database.get_user("lisi")
    assert stored is not None
    assert PASSWORD not in stored.password_hash


# --------------------------------------------------------------------------
# 登录校验
# --------------------------------------------------------------------------


def test_authenticate_accepts_the_right_password():
    accounts.register("lisi", PASSWORD)

    user = accounts.authenticate("lisi", PASSWORD)

    assert user.username == "lisi"


def test_username_is_trimmed_before_lookup():
    accounts.register("lisi", PASSWORD)
    assert accounts.authenticate("  lisi  ", PASSWORD).username == "lisi"


def test_unknown_user_and_wrong_password_share_one_message():
    """两种失败**必须一模一样**——否则等于给了一个枚举用户名的接口。"""
    accounts.register("lisi", PASSWORD)

    with pytest.raises(InvalidCredentials) as unknown:
        accounts.authenticate("nobody", PASSWORD)
    with pytest.raises(InvalidCredentials) as wrong:
        accounts.authenticate("lisi", "wrong-pass-1")

    assert unknown.value.user_message == wrong.value.user_message


def test_disabled_account_is_refused_without_revealing_it_exists():
    accounts.register("lisi", PASSWORD)
    database.set_user_active("lisi", False, viewer=ADMIN)

    with pytest.raises(InvalidCredentials) as disabled:
        accounts.authenticate("lisi", PASSWORD)
    with pytest.raises(InvalidCredentials) as wrong:
        accounts.authenticate("lisi", "wrong-pass-1")

    assert disabled.value.user_message == wrong.value.user_message, (
        "「账号已停用」同样不能透露这个账号存在"
    )


def test_empty_credentials_are_refused():
    with pytest.raises(InvalidCredentials):
        accounts.authenticate("", "")


# --------------------------------------------------------------------------
# 初始管理员引导
# --------------------------------------------------------------------------


def _password_from_notice(notice: str) -> str:
    match = re.search(r"初始密码：(\S+)", notice)
    assert match is not None, f"提示里没有可用的密码：{notice}"
    return match.group(1)


def test_initial_admin_comes_from_the_configured_credentials(monkeypatch):
    monkeypatch.setenv(config.ADMIN_USERNAME_ENV, "boss")
    monkeypatch.setenv(config.ADMIN_PASSWORD_ENV, "boss-pass-123")

    created = accounts.ensure_initial_admin()

    assert created is not None
    user, notice = created
    assert user.username == "boss"
    assert user.role == ROLE_ADMIN
    assert notice == "", "密码来自配置时没有任何东西需要打印"
    assert accounts.authenticate("boss", "boss-pass-123").is_admin


def test_unconfigured_credentials_are_generated_and_reported_once():
    created = accounts.ensure_initial_admin()

    assert created is not None
    user, notice = created
    assert user.username == accounts.DEFAULT_ADMIN_USERNAME
    assert user.role == ROLE_ADMIN

    generated = _password_from_notice(notice)
    assert "立即修改" in notice, "必须提示立即修改"
    # 提示里那个密码要真的能用——否则「打印了但登不进去」比不打印更糟
    assert accounts.authenticate(user.username, generated).is_admin


def test_a_configured_but_too_short_password_is_replaced_with_a_random_one(monkeypatch):
    """配置的密码太短时**不静默放行**，而是换一个合规的并明说。"""
    monkeypatch.setenv(config.ADMIN_USERNAME_ENV, "boss")
    monkeypatch.setenv(config.ADMIN_PASSWORD_ENV, "123")

    created = accounts.ensure_initial_admin()

    assert created is not None
    _user, notice = created
    assert "不合规" in notice
    assert accounts.authenticate("boss", _password_from_notice(notice)).is_admin


def test_an_invalid_configured_username_falls_back_to_the_default(monkeypatch):
    """用户名不合规时退回默认名——首次启动起不来就没有界面能说清原因。"""
    monkeypatch.setenv(config.ADMIN_USERNAME_ENV, "a b")
    monkeypatch.setenv(config.ADMIN_PASSWORD_ENV, "boss-pass-123")

    created = accounts.ensure_initial_admin()

    assert created is not None
    user, notice = created
    assert user.username == accounts.DEFAULT_ADMIN_USERNAME
    assert "不合规" in notice


def test_bootstrap_does_nothing_when_an_account_already_exists():
    accounts.register("lisi", PASSWORD)

    assert accounts.ensure_initial_admin() is None
    assert database.count_active_admins() == 0
    assert database.list_users().__len__() == 1


def test_startup_creates_the_initial_admin_on_a_fresh_database(monkeypatch):
    """验收 15.1：全新库首次启动自动建初始管理员。

    直接调 `app._bootstrap_once()`——它是启动路径上真正被调用的那个函数，
    不是它的某个副本。先 `clear()` 掉 `st.cache_resource` 的缓存来模拟
    「进程刚起来」：那个缓存是进程级的，不清的话只有第一个用例会真的跑到它。
    """
    import app

    monkeypatch.setenv(config.ADMIN_USERNAME_ENV, "boss")
    monkeypatch.setenv(config.ADMIN_PASSWORD_ENV, "boss-pass-123")

    app._bootstrap_once.clear()
    app._bootstrap_once()

    created = database.get_user("boss")
    assert created is not None
    assert created.role == ROLE_ADMIN
    assert created.is_active is True


def test_startup_is_idempotent_and_leaves_existing_accounts_alone(monkeypatch):
    """已经建过管理员之后再启动，不该再建一个、也不该改密码。"""
    import app

    database.create_user("keeper", "keeper-pass-1", role=ROLE_ADMIN)
    monkeypatch.setenv(config.ADMIN_USERNAME_ENV, "boss")
    monkeypatch.setenv(config.ADMIN_PASSWORD_ENV, "boss-pass-123")

    app._bootstrap_once.clear()
    app._bootstrap_once()

    assert database.get_user("boss") is None
    assert database.count_users() == 1


def test_the_first_registered_user_is_not_an_admin():
    """**绝不允许「第一个注册的人自动成为管理员」。**

    那等于把管理员权限挂在谁手快上——而且注册是开放的，
    任何能访问到地址的人都可能成为那个「手快的人」。
    """
    user = accounts.register("early-bird", PASSWORD)

    assert user.role == ROLE_USER
    assert database.count_active_admins() == 0


# --------------------------------------------------------------------------
# 权限守卫（任务 4.6 / 6.7 / 6.8）
# --------------------------------------------------------------------------


def test_regular_user_cannot_perform_admin_writes():
    """spec：普通用户直接调用管理员操作被拒绝，且**不产生任何写入**。

    「直接调用」是关键——这些调用都绕过了界面，正是「只隐藏入口」挡不住的
    那条路。所以守卫写在数据层写入口里（design D3）。
    """
    accounts.register("lisi", PASSWORD)
    before = database.list_users()

    with pytest.raises(PermissionDenied):
        database.set_user_role("lisi", ROLE_ADMIN, viewer=REGULAR)
    with pytest.raises(PermissionDenied):
        database.set_user_password("lisi", "another-pass-1", viewer=REGULAR)
    with pytest.raises(PermissionDenied):
        database.set_user_active("lisi", False, viewer=REGULAR)
    with pytest.raises(PermissionDenied):
        accounts.create_account(REGULAR, "sneaky", PASSWORD, role=ROLE_ADMIN)
    with pytest.raises(PermissionDenied):
        database.set_user_role("lisi", ROLE_ADMIN, viewer=None)

    assert database.list_users() == before, "被拒绝的调用不该留下任何写入"
    assert database.get_user("sneaky") is None
    assert database.get_user("lisi").role == ROLE_USER


def test_admin_can_perform_the_same_writes():
    """反过来也要成立——守卫不能把管理员自己也挡在外面。

    库里先放一个真管理员：否则「停用 lisi」会撞上「最后一个可用管理员」
    另一条守卫，把这条用例的意图（权限放行）和那条守卫的意图搅在一起。
    """
    database.create_user("root", PASSWORD, role=ROLE_ADMIN)
    accounts.register("lisi", PASSWORD)

    database.set_user_role("lisi", ROLE_ADMIN, viewer=ADMIN)
    assert database.get_user("lisi").role == ROLE_ADMIN

    database.set_user_password("lisi", "brand-new-pass-1", viewer=ADMIN)
    assert accounts.authenticate("lisi", "brand-new-pass-1").is_admin

    database.set_user_active("lisi", False, viewer=ADMIN)
    assert database.get_user("lisi").is_active is False


def test_last_admin_cannot_be_demoted():
    admin = database.create_user("root", PASSWORD, role=ROLE_ADMIN)

    with pytest.raises(LastAdminProtected):
        database.set_user_role("root", ROLE_USER, viewer=admin)

    assert database.get_user("root").role == ROLE_ADMIN
    assert database.count_active_admins() == 1


def test_last_admin_cannot_be_disabled():
    admin = database.create_user("root", PASSWORD, role=ROLE_ADMIN)

    with pytest.raises(LastAdminProtected):
        database.set_user_active("root", False, viewer=admin)

    assert database.get_user("root").is_active is True


def test_demoting_one_of_two_admins_is_allowed():
    """有第二个管理员之后就该放行——守卫拦的是「一个都不剩」，不是「改管理员」。"""
    database.create_user("root", PASSWORD, role=ROLE_ADMIN)
    second = database.create_user("root2", PASSWORD, role=ROLE_ADMIN)

    database.set_user_role("root", ROLE_USER, viewer=second)

    assert database.get_user("root").role == ROLE_USER
    assert database.count_active_admins() == 1


def test_disabling_one_of_two_admins_is_allowed():
    database.create_user("root", PASSWORD, role=ROLE_ADMIN)
    second = database.create_user("root2", PASSWORD, role=ROLE_ADMIN)

    database.set_user_active("root", False, viewer=second)

    assert database.count_active_admins() == 1


def test_a_disabled_admin_does_not_count_as_available():
    """停用的管理员不算「可用」——否则停用第一个之后，第二个就永远降不了级。"""
    root = database.create_user("root", PASSWORD, role=ROLE_ADMIN)
    database.create_user("root2", PASSWORD, role=ROLE_ADMIN)

    database.set_user_active("root2", False, viewer=root)

    with pytest.raises(LastAdminProtected):
        database.set_user_active("root", False, viewer=root)
