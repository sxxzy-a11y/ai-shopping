"""账号与登录的纯逻辑：用户模型、密码派生与校验、角色判定。

**这一层不碰数据库。** 用户记录的读写（建表、增删改查）在 `src/database.py`，
登录页在 `src/ui/pages/login.py`。分开的理由：「密码怎么存」与「谁能做什么」
这两件事必须能被单元测试直接盯住，而不必先起一个 Streamlit 会话。

设计要点（design.md D1、D3、D8）
--------------------------------
- 密码用标准库 `hashlib.pbkdf2_hmac`，**不引入任何新依赖**。
  实测 600_000 次派生在本机约 93 毫秒：慢是刻意的，但没慢到影响演示，
  所以按设计保持 600_000，不做降级。
- **算法与迭代次数写进凭据串**（`pbkdf2_sha256$<迭代>$<盐>$<哈希>`）。
  校验时从串里读参数，而不是读模块常量——日后调参不会让已有密码失效。
- 角色只有两种，且权限判定只有一个入口 `require_admin()`。
  侧边栏隐藏入口只是锦上添花，**不算权限**（D3）。
- 用户名不存在与密码错误**共用同一句话**，见 `errors.InvalidCredentials`。
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Final

from pydantic import BaseModel, ConfigDict

from src.errors import InvalidUsername, PermissionDenied, WeakPassword

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

#: 角色取值。**只有两种**，不做细粒度授权（design 的 Non-Goals）。
ROLE_ADMIN: Final[str] = "admin"
ROLE_USER: Final[str] = "user"

ROLE_LABELS: Final[dict[str, str]] = {
    ROLE_ADMIN: "管理员",
    ROLE_USER: "普通用户",
}

#: 凭据串里的算法标识。将来换算法时它也要变，老串仍按老算法校验。
ALGORITHM: Final[str] = "pbkdf2_sha256"

#: 迭代次数。写进凭据串，所以调整它不需要迁移任何已有密码。
PASSWORD_ITERATIONS: Final[int] = 600_000

SALT_BYTES: Final[int] = 16

MIN_PASSWORD_LENGTH: Final[int] = 8
MIN_USERNAME_LENGTH: Final[int] = 3
MAX_USERNAME_LENGTH: Final[int] = 32


# --------------------------------------------------------------------------
# 用户模型
# --------------------------------------------------------------------------


class User(BaseModel):
    """一个账号。

    字段就是 `users` 表的列，**没有多余的个人信息**——
    不要手机号、邮箱、姓名：本应用不需要，收了也只是白拿（见 spec 的
    「数据最小化与隐私」与 design D8）。
    """

    model_config = ConfigDict(extra="ignore")

    username: str
    role: str = ROLE_USER
    is_active: bool = True
    #: 派生结果串，**绝不是明文密码**。
    password_hash: str = ""
    created_at: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)


def is_admin(user: User | None) -> bool:
    """角色判定。未登录（`None`）或角色值不认识，**一律按非管理员处理**。

    用「等于管理员」而不是「不等于普通用户」来判断：前者遇到没见过的角色值
    会拒绝，后者会放行。权限判定要错在拒的那一侧。
    """
    return user is not None and user.role == ROLE_ADMIN


def require_admin(user: User | None) -> None:
    """管理员守卫。**放在真正读写数据的那个函数入口调用**（design D3）。

    只隐藏界面入口不构成权限：页面函数之间会互相调用，`st.session_state`
    也能被脚本改写。守卫放在数据层入口，「能不能做这件事」就只有一处判断。

    Raises:
        PermissionDenied: 当前会话不是管理员。
    """
    if not is_admin(user):
        who = user.username if user is not None else "未登录会话"
        raise PermissionDenied(detail=f"{who} 尝试执行管理员操作")


# --------------------------------------------------------------------------
# 输入校验
# --------------------------------------------------------------------------


def validate_username(username: str) -> str:
    """校验并归一化用户名，返回去掉首尾空白后的结果。

    规则刻意宽松：只要求「不含空白字符」与长度区间，不限制字符集。
    收紧字符集等于替用户决定他该叫什么，而这里并没有那个必要。

    Raises:
        InvalidUsername: 不合规，文案里带上具体区间。
    """
    name = (username or "").strip()
    rule = f"请使用 {MIN_USERNAME_LENGTH}–{MAX_USERNAME_LENGTH} 个字符，且不含空格。"

    if not name:
        raise InvalidUsername(f"用户名不能为空，{rule}")
    if any(char.isspace() for char in name):
        raise InvalidUsername(f"用户名不能包含空格，{rule}")
    if not MIN_USERNAME_LENGTH <= len(name) <= MAX_USERNAME_LENGTH:
        raise InvalidUsername(f"用户名长度不符，{rule}")
    return name


def validate_password(password: str) -> None:
    """密码最低要求：长度不少于 `MIN_PASSWORD_LENGTH`。

    比长度更严的规则（大小写混合、特殊字符）这里刻意不做：
    它们通常只会把人推向「Password1!」这类可预测的组合。

    Raises:
        WeakPassword: 长度不足。文案里的数字取自常量，不写死。
    """
    if not password or not password.strip():
        raise WeakPassword("密码不能为空或全为空格。")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(f"密码太短，请至少使用 {MIN_PASSWORD_LENGTH} 个字符。")


# --------------------------------------------------------------------------
# 密码派生与校验
# --------------------------------------------------------------------------


def hash_password(password: str, *, iterations: int = PASSWORD_ITERATIONS) -> str:
    """派生密码，返回自描述凭据串 `pbkdf2_sha256$<迭代>$<盐hex>$<哈希hex>`。

    盐每次都随机——所以同一个密码的两次结果不同，光看库里的凭据串
    判断不出两个人是否用了同一个密码。
    """
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, credential: str) -> bool:
    """校验密码。**参数从凭据串里读**，不读模块常量（design D1）。

    坏凭据一律返回 `False` 而不抛异常：登录页拿到的应该是「不通过」，
    而不是一个内部错误——抛出去就得在那里再包一层，还容易漏掉某条路径
    把异常内容透给用户。
    """
    try:
        algorithm, iterations_text, salt_hex, digest_hex = (credential or "").split("$")
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False

    if algorithm != ALGORITHM or iterations <= 0 or not salt or not expected:
        return False

    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    # 定长比较，不因为「第几个字节不同」而提前返回。
    return hmac.compare_digest(candidate, expected)
