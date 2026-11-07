"""智购参谋 API。

启动（从项目根目录）：
    python backend/run.py
或：
    uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

`frontend/dist` 存在时自动托管构建产物，生产环境单端口即可访问。
Vue 端使用 hash 路由，因此静态托管不需要额外的 history fallback。
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from src import accounts, config, database, report_service
from src.errors import ZhigouError, to_user_message

from backend.app import schemas, services
from backend.app.admin_api import router as admin_router
from backend.app.core import (
    AdminUser,
    CurrentUser,
    create_session,
    destroy_session,
    session_cookie_kwargs,
)
from backend.app.services import BadRequest, ServiceUnavailable

app = FastAPI(title="智购参谋 API", version="2.0", docs_url="/api/docs")

_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)


@app.exception_handler(BadRequest)
async def _bad_request_handler(request: Request, exc: BadRequest) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ServiceUnavailable)
async def _unavailable_handler(
    request: Request, exc: ServiceUnavailable
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(ZhigouError)
async def _domain_error_handler(request: Request, exc: ZhigouError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": to_user_message(exc)})


# --------------------------------------------------------------------------
# 鉴权
# --------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    healthy, message = database.check_health()
    return {"status": "ok" if healthy else "degraded", "database": message}


@app.post("/api/auth/login")
def login(payload: schemas.LoginRequest, response: Response) -> dict:
    try:
        user = accounts.authenticate(payload.username, payload.password)
    except ZhigouError:
        # 用户名不存在 / 密码错误 / 账号停用共用同一句话。
        raise HTTPException(status_code=401, detail="用户名或密码错误") from None
    token = create_session(user)
    response.set_cookie(value=token, **session_cookie_kwargs())
    return {
        "username": user.username,
        "role": user.role,
        "role_label": user.role_label,
        "is_admin": user.is_admin,
    }


@app.post("/api/auth/register")
def register(payload: schemas.RegisterRequest) -> dict:
    if os.getenv("ZHIGOU_ALLOW_REGISTRATION", "true").lower() in {"0", "false", "no"}:
        raise HTTPException(status_code=403, detail="当前系统未开放自助注册")
    try:
        user = accounts.register(payload.username, payload.password)
    except ZhigouError as exc:
        raise HTTPException(status_code=400, detail=to_user_message(exc)) from exc
    return {"username": user.username, "role": user.role}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict:
    destroy_session(request.cookies.get("zg_session"))
    response.delete_cookie("zg_session", path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: CurrentUser) -> dict:
    return {
        "username": user.username,
        "role": user.role,
        "role_label": user.role_label,
        "is_admin": user.is_admin,
    }


# --------------------------------------------------------------------------
# 目录与元数据
# --------------------------------------------------------------------------


@app.get("/api/meta")
def meta(user: CurrentUser) -> dict:
    data = services.list_products()
    return {
        "categories": data["categories"],
        "brands": data["brands"],
        "total": data["total"],
        "dataset_name": data["dataset_name"],
        "disclaimer": data["disclaimer"],
        "score_display_name": config.SCORE_DISPLAY_NAME,
        "user": {
            "username": user.username,
            "role": user.role,
            "is_admin": user.is_admin,
        },
    }


@app.get("/api/about")
def about(user: CurrentUser) -> dict:
    return services.about_info()


@app.get("/api/products")
def products(user: CurrentUser, category: str = "") -> dict:
    return services.list_products(category)


# --------------------------------------------------------------------------
# 核心业务
# --------------------------------------------------------------------------


@app.post("/api/analysis")
def analysis(payload: schemas.AnalysisRequest, user: CurrentUser) -> dict:
    return services.run_analysis(payload, user)


@app.post("/api/compare")
def compare(payload: schemas.CompareRequest, user: CurrentUser) -> dict:
    return services.compare_products(payload.product_ids, payload.text)


@app.post("/api/qa")
def qa(payload: schemas.QARequest, user: CurrentUser) -> dict:
    return services.answer_question(payload.question, user)


# --------------------------------------------------------------------------
# 历史 / 收藏 / 偏好
# --------------------------------------------------------------------------


@app.get("/api/history")
def history(user: CurrentUser) -> dict:
    entries = database.list_analyses_of(user.username)
    return {"entries": [asdict(entry) for entry in entries]}


@app.get("/api/history/{entry_id}")
def history_detail(entry_id: int, user: CurrentUser) -> dict:
    report = database.get_analysis(entry_id, viewer=user)
    if report is None:
        raise HTTPException(status_code=404, detail="记录不存在或无权查看")
    return report.to_dict()


@app.get("/api/history/{entry_id}/export")
def history_export(entry_id: int, user: CurrentUser, format: str = "md") -> Response:
    report = database.get_analysis(entry_id, viewer=user)
    if report is None:
        raise HTTPException(status_code=404, detail="记录不存在或无权查看")
    if format == "csv":
        content = report_service.csv_bytes(report).decode("utf-8")
        media_type = "text/csv; charset=utf-8"
    else:
        content = report_service.markdown_bytes(report).decode("utf-8")
        media_type = "text/markdown; charset=utf-8"
    filename = report_service.suggested_filename(
        report, "csv" if format == "csv" else "md"
    )
    return PlainTextResponse(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/api/history/{entry_id}")
def history_delete(entry_id: int, user: CurrentUser) -> dict:
    deleted = database.delete_analysis(entry_id, viewer=user)
    if not deleted:
        raise HTTPException(status_code=404, detail="记录不存在或无权删除")
    return {"ok": True}


@app.get("/api/favorites")
def favorites(user: CurrentUser) -> dict:
    return {
        "items": [
            {"product_id": pid, "added_at": added}
            for pid, added in database.list_favorites(user.username)
        ]
    }


@app.post("/api/favorites")
def add_favorite(payload: schemas.FavoriteRequest, user: CurrentUser) -> dict:
    database.add_favorite(user.username, payload.product_id)
    return {"ok": True}


@app.delete("/api/favorites/{product_id}")
def remove_favorite(product_id: str, user: CurrentUser) -> dict:
    database.remove_favorite(user.username, product_id)
    return {"ok": True}


@app.get("/api/preferences")
def get_preferences(user: CurrentUser) -> dict:
    return services.get_preferences(user)


@app.put("/api/preferences")
def put_preferences(payload: schemas.PreferencesUpdate, user: CurrentUser) -> dict:
    return services.update_preferences(user, payload)


# --------------------------------------------------------------------------
# 管理员
# --------------------------------------------------------------------------


@app.get("/api/admin/overview")
def admin_overview(admin: AdminUser) -> dict:
    return services.admin_overview()


@app.get("/api/eval")
def eval_summary(admin: AdminUser) -> dict:
    return services.eval_summary()


# --------------------------------------------------------------------------
# 静态托管（生产：构建过前端才启用）
# --------------------------------------------------------------------------

_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")
