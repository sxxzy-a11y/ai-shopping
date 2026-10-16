"""账号与凭据的纯逻辑测试。

对应变更 `add-login-and-user-roles` 的任务 1.6。这一层不碰数据库，
所以可以直接断言「密码怎么存」——不必起 Streamlit 会话或建表。

迭代次数在这些用例里刻意调低（`iterations=1000`）：
600_000 次派生一次要 90 毫秒，用例里反复跑会把测试时间堆到无谓的长度。
「参数从凭据串里读」这条正是靠低迭代串验证的——能校验成功，
就说明它读的不是模块常量。
"""

from __future__ import annotations

import pytest

from src.auth import (
    MIN_PASSWORD_LENGTH,
    ROLE_ADMIN,
    ROLE_USER,
    User,
    hash_password,
    is_admin,
    require_admin,
    validate_password,
    validate_username,
    verify_password,
)
from src.errors import InvalidUsername, PermissionDenied, WeakPassword

FAST = 1000
PASSWORD = "correct-horse-9"


# --- 1.6 密码不落明文、两次哈希不同、改迭代次数后仍可校验 --------------------


def test_credential_contains_no_trace_of_the_password():
    credential = hash_password(PASSWORD, iterations=FAST)
    assert PASSWORD not in credential
    assert credential.startswith("pbkdf2_sha256$")


def test_credential_is_self_describing():
    credential = hash_password(PASSWORD, iterations=FAST)
    algorithm, iterations, salt, digest = credential.split("$")
    assert algorithm == "pbkdf2_sha256"
    assert int(iterations) == FAST
    assert len(salt) == 32, "16 字节盐的十六进制表示"
    assert len(digest) == 64, "SHA-256 输出的十六进制表示"


def test_two_hashes_of_the_same_password_differ():
    """盐随机，所以同密码两次结果不同——否则能看出两个人密码一样。"""
    first = hash_password(PASSWORD, iterations=FAST)
    second = hash_password(PASSWORD, iterations=FAST)
    assert first != second
    assert verify_password(PASSWORD, first)
    assert verify_password(PASSWORD, second)


def test_credential_states_its_own_iterations():
    """校验要按**串里记录的**迭代次数派生，而不是模块当前常量。

    这条是设计 D1 的核心：把参数写进凭据串，日后调参不会让已有密码失效。
    """
    legacy = hash_password(PASSWORD, iterations=FAST)
    assert legacy.startswith(f"pbkdf2_sha256${FAST}$")
    assert verify_password(PASSWORD, legacy) is True


def test_wrong_password_is_rejected():
    credential = hash_password(PASSWORD, iterations=FAST)
    assert verify_password(PASSWORD + "-x", credential) is False


@pytest.mark.parametrize(
    "credential",
    ["", "not-a-credential", "pbkdf2_sha256$abc$00$ff", "md5$1$aa$bb", "pbkdf2_sha256$1$aa"],
)
def test_malformed_credential_is_rejected_not_raised(credential):
    """坏凭据只能判为「不通过」。抛异常会让登录页把内部错误透给用户。"""
    assert verify_password(PASSWORD, credential) is False


# --- 1.4 角色 -----------------------------------------------------------------


def test_admin_role_is_recognised():
    admin = User(username="root", role=ROLE_ADMIN)
    assert is_admin(admin) is True
    assert admin.role_label == "管理员"


def test_regular_user_is_not_admin():
    user = User(username="lisi", role=ROLE_USER)
    assert is_admin(user) is False
    assert user.role_label == "普通用户"


def test_not_logged_in_is_not_admin():
    assert is_admin(None) is False


def test_unknown_role_is_not_admin():
    """角色值不认识时按最小权限处理，而不是当成管理员。"""
    assert is_admin(User(username="odd", role="superuser")) is False


def test_require_admin_rejects_regular_user():
    with pytest.raises(PermissionDenied) as caught:
        require_admin(User(username="lisi", role=ROLE_USER))
    assert "权限" in caught.value.user_message


def test_require_admin_rejects_anonymous():
    with pytest.raises(PermissionDenied):
        require_admin(None)


def test_require_admin_accepts_admin():
    require_admin(User(username="root", role=ROLE_ADMIN))


# --- 1.5 用户名与密码校验 -----------------------------------------------------


@pytest.mark.parametrize("name", ["lisi", "li_si", "user-01", "张三丰", "a" * 32])
def test_valid_usernames_are_kept(name):
    assert validate_username(name) == name


def test_username_is_stripped_of_outer_spaces():
    assert validate_username("  lisi  ") == "lisi"


@pytest.mark.parametrize("name", ["", "   ", "ab", "a" * 33, "li si", "li\tsi", "li\nsi"])
def test_invalid_usernames_are_rejected(name):
    with pytest.raises(InvalidUsername) as caught:
        validate_username(name)
    assert caught.value.user_message, "错误必须带中文说明"


def test_password_shorter_than_minimum_is_rejected():
    too_short = "a" * (MIN_PASSWORD_LENGTH - 1)
    with pytest.raises(WeakPassword) as caught:
        validate_password(too_short)
    assert str(MIN_PASSWORD_LENGTH) in caught.value.user_message


def test_password_at_minimum_length_passes():
    validate_password("a" * MIN_PASSWORD_LENGTH)


def test_blank_password_is_rejected():
    with pytest.raises(WeakPassword):
        validate_password("   ")
