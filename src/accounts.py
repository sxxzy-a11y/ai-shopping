"""账号的动作层：注册、凭据校验、初始管理员引导。

分成三层，是因为依赖方向**只能有一个方向**：

    src/auth.py       纯逻辑：派生、校验规则、角色判定     ← 不依赖任何东西
    src/database.py   存储：users 表的增删改查            ← 依赖 auth
    src/accounts.py   动作：把上面两层拼成「注册」「登录」  ← 依赖上面两个

把注册与登录写进 `auth.py` 会让它反向依赖 `database`，与 `database` 对 `auth`
的依赖撞成循环导入。

（design 的 Impact 表把这几件事都记在 `src/auth.py` 名下。实现时拆开是因为
那条循环依赖是真的会炸——拆完之后 `auth.py` 依然能在完全不碰数据库的情况下
被单元测试。）
"""

from __future__ import annotations

import secrets

from src import config, database
from src.auth import (
    ROLE_ADMIN,
    ROLE_USER,
    User,
    hash_password,
    validate_password,
    validate_username,
    verify_password,
)
from src.errors import (
    AccountDisabled,
    InvalidCredentials,
    InvalidUsername,
    WeakPassword,
    ZhigouError,
)

#: 没有配置 `ZHIGOU_ADMIN_USERNAME` 时用的账号名。
DEFAULT_ADMIN_USERNAME = "admin"


def register(username: str, password: str) -> User:
    """自助注册。角色**固定为普通用户**。

    注意 `register()` 压根没有 `role` 参数——不是「传进来会被忽略」，
    而是调用方连表达「我要注册成管理员」的机会都没有（任务 3.5）。
    管理员权限只能由管理员授予。

    Raises:
        InvalidUsername: 用户名不合规。
        WeakPassword: 密码太短。
        UsernameTaken: 用户名已被占用。
        HistoryWriteError: 写入失败。
    """
    name = validate_username(username)
    validate_password(password)
    return database.create_user(name, password, role=ROLE_USER)


def authenticate(username: str, password: str) -> User:
    """校验凭据，返回账号。

    **三种失败共用同一句话**：用户名不存在、密码错误、账号被停用，
    对访问者都只是「登不进去」。分开说等于提供了一个枚举有效用户名的地方。

    Raises:
        InvalidCredentials: 登不进去（含账号停用，它继承同一个文案）。
    """
    name = (username or "").strip()
    user = database.get_user(name) if name else None

    if user is None or not user.password_hash:
        # 用户名不存在时**也跑一次派生**：不跑的话「查得到」明显慢于
        # 「查不到」，响应时间本身就把账号是否存在泄露出去了。
        hash_password(password)
        raise InvalidCredentials()

    if not verify_password(password, user.password_hash):
        raise InvalidCredentials()

    if not user.is_active:
        # 文案与上面完全一致（AccountDisabled 继承自 InvalidCredentials），
        # 真实原因进 detail，只写日志。
        raise AccountDisabled(detail=f"账号 {name} 已停用")

    return user


def still_valid(user: User | None) -> bool:
    """这个账号现在还能用吗——**存在且启用**。

    `app.py` 每轮渲染后调一次。为什么需要它：`require_admin(viewer)` 只看
    **会话里那个对象的角色**，`current_user()` 只读会话，两者都不查库。于是
    停用一个正在使用的账号之后，它的会话照样能进管理页，直到刷新才被拦；
    删除账号会把同一个口子放大——被删掉的管理员，会话里的对象还在。

    库读不出来时**按「仍然有效」处理**：那是「读不到」而不是「账号无效」，
    把使用者踢出去只会让一个只读故障升级成用不了应用。这与本项目对渲染期
    只读查询的一贯处理一致（`is_favorite` 读失败按「未收藏」处理）。
    """
    if user is None:
        return False

    try:
        stored = database.get_user(user.username)
    except ZhigouError:
        return True

    return stored is not None and stored.is_active


def ensure_initial_admin() -> tuple[User, str] | None:
    """账号表为空时创建初始管理员。

    **绝不允许「第一个注册的人自动成为管理员」**——那等于把管理员权限
    挂在谁手快上。所以这个函数只认环境变量与代码里的默认名。

    Returns:
        `(账号, 要打印一次的提示)`；表里已有账号、或密码来自配置（无需提示）
        时返回 `None`。提示里可能包含**刚生成的明文密码**，调用方负责打印
        一次并提示立即修改，之后不要再记它。
    """
    if database.count_users() > 0:
        return None

    lines: list[str] = []

    raw_username = config.admin_username() or DEFAULT_ADMIN_USERNAME
    try:
        username = validate_username(raw_username)
    except InvalidUsername as exc:
        # 配置里的名字不合规时**退回默认名并说明**，而不是让应用起不来：
        # 这是首次启动，起不来就没有任何界面可以把这件事告诉用户。
        username = DEFAULT_ADMIN_USERNAME
        lines.append(
            f"配置的管理员用户名不合规（{exc.user_message}），已改用「{username}」。"
        )

    password = config.admin_password()
    generated = False

    if not password:
        password = secrets.token_urlsafe(config.ADMIN_RANDOM_PASSWORD_BYTES)
        generated = True
    else:
        try:
            validate_password(password)
        except WeakPassword as exc:
            # 配置的密码太短：**不静默放行**。生一个合规的并明说。
            password = secrets.token_urlsafe(config.ADMIN_RANDOM_PASSWORD_BYTES)
            generated = True
            lines.append(f"配置的管理员密码不合规（{exc.user_message}），已改为随机生成。")

    user = database.create_user(username, password, role=ROLE_ADMIN)

    if generated:
        lines.append(f"初始管理员账号：{username}")
        lines.append(f"初始密码：{password}")
        lines.append("这段密码只在本次启动输出里出现一次，请登录后立即修改。")

    return user, "\n".join(lines)
