"""API 会话与权限依赖。

设计取舍：会话只放在进程内存里，用随机 token + HttpOnly Cookie 携带。
不引入 JWT 依赖、不把用户信息交给前端存储；服务重启后需要重新登录。
权限判定**在后端路由入口**执行（`require_admin`），前端隐藏入口不算权限 ——
沿用 `src/auth.py` 的同一条原则。
"""

from __future__ import annotations

import secrets
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from src.auth import User, is_admin

COOKIE_NAME = "zg_session"
_COOKIE_MAX_AGE = 60 * 60 * 12
#: 空闲多久没请求就失效。绝对过期仍由 `_COOKIE_MAX_AGE` 管，两者取先到者。
_SESSION_IDLE_TIMEOUT = 30 * 60

#: token -> (用户, 绝对过期时刻, 最近活动时刻)。单进程部署；重启即失效。
_sessions: dict[str, tuple[User, float, float]] = {}


def _purge_expired(now: float) -> None:
    """清掉绝对过期或空闲超时的 token。

    没有这一步，`_sessions` 只增不减：Cookie 有 12 小时有效期，但服务端
    字典里那些「登录后就没再回来」的 token 会一直留到进程重启。
    """
    expired = [
        token
        for token, (_, expires_at, last_seen) in _sessions.items()
        if expires_at <= now or now - last_seen >= _SESSION_IDLE_TIMEOUT
    ]
    for token in expired:
        _sessions.pop(token, None)


def create_session(user: User) -> str:
    now = time.monotonic()
    _purge_expired(now)
    token = secrets.token_urlsafe(32)
    _sessions[token] = (user, now + _COOKIE_MAX_AGE, now)
    return token


def destroy_session(token: str | None) -> None:
    if token:
        _sessions.pop(token, None)


def user_from_request(request: Request) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    entry = _sessions.get(token)
    if entry is None:
        return None
    user, expires_at, last_seen = entry
    now = time.monotonic()
    if expires_at <= now or now - last_seen >= _SESSION_IDLE_TIMEOUT:
        # 绝对过期或空闲超时都视为未登录，与 Cookie 到期后的表现一致。
        _sessions.pop(token, None)
        return None
    # 只滑动「最近活动」，绝对过期时刻不动——否则持续操作能无限续命。
    _sessions[token] = (user, expires_at, now)
    return user


def current_user(request: Request) -> User:
    """要求已登录。未登录统一 401，不区分「没带 token」和「token 失效」。"""
    user = user_from_request(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    """管理员端点的数据层守卫。"""
    if not is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限"
        )
    return user


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(require_admin)]


def session_cookie_kwargs() -> dict:
    return {
        "key": COOKIE_NAME,
        "httponly": True,
        "samesite": "lax",
        "max_age": _COOKIE_MAX_AGE,
        "path": "/",
        # 本地 http 演示必须为 False；部署到 HTTPS 时应由反向代理改写为 True。
        "secure": False,
    }
