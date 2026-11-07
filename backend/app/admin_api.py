"""管理员 API：把旧版 Streamlit 的写操作与诊断能力原样开放给 Vue 界面。

设计原则：
- **不重写业务规则**，全部调用 `src/` 里旧版同一批函数（含 require_admin 守卫）；
- 路由层再加一道 `AdminUser` 依赖，形成「界面隐藏 + 后端兜底 + 数据层守卫」三层；
- 领域异常由 `main.py` 的全局 handler 统一转成 400 中文提示；
- 密钥只在服务端读写，响应里一律掩码，绝不回传明文。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src import (
    ai_service,
    api_config,
    catalog_admin,
    catalog_meta,
    config,
    database,
)
from src.errors import ZhigouError, to_user_message
from src.knowledge import admin as knowledge_docs
from src.knowledge import corpus, embeddings

from backend.app.core import AdminUser
from backend.app.services import BadRequest, get_catalog, to_jsonable

router = APIRouter(prefix="/api/admin", tags=["admin"])

_SECRET_KEYS = frozenset({"llm_api_key", "embedding_api_key"})


def _config_view() -> dict:
    """当前生效配置。密钥只给掩码值，来源用 `api_config.source_of` 标注。"""
    getters: dict[str, Any] = {
        "llm_api_key": config.llm_api_key,
        "llm_base_url": config.llm_base_url,
        "llm_model": config.llm_model,
        "embedding_api_key": config.embedding_api_key,
        "embedding_base_url": config.embedding_base_url,
        "embedding_model": config.embedding_model,
        "embedding_dim": config.embedding_dim,
    }
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for key in api_config.ALLOWED_KEYS:
        raw = str(getters[key]())
        values[key] = api_config.mask(raw) if key in _SECRET_KEYS else raw
        sources[key] = api_config.source_of(key)
    return {
        "values": values,
        "sources": sources,
        "configured": {
            "llm": bool(config.llm_api_key()),
            "embedding": bool(config.embedding_api_key()),
        },
        "masked_keys": sorted(_SECRET_KEYS),
    }


class ApiConfigUpdate(BaseModel):
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_model: str | None = None
    embedding_api_key: str | None = None
    embedding_dim: int | None = Field(default=None, ge=64, le=8192)


# --------------------------------------------------------------------------
# API 配置与连接检测（旧版「个人设置 → API 配置」）
# --------------------------------------------------------------------------


@router.get("/api-config")
def get_api_config(admin: AdminUser) -> dict:
    return _config_view()


@router.put("/api-config")
def save_api_config(payload: ApiConfigUpdate, admin: AdminUser) -> dict:
    # 空值不覆盖：用户在界面只改模型名时，密钥框留空不能把已有密钥清掉。
    values = payload.model_dump(exclude_none=True)
    api_config.save(values)
    embeddings.reset_service()
    return _config_view()


@router.delete("/api-config")
def clear_api_config(admin: AdminUser) -> dict:
    api_config.clear()
    embeddings.reset_service()
    return _config_view()


@router.post("/api-config/probe/llm")
def probe_llm(admin: AdminUser) -> dict:
    """AI 连接检测：对话模型。沿用旧版 `ai_service.probe()`。"""
    ok, message = ai_service.probe()
    return {
        "ok": ok,
        "message": ("对话模型连接正常：" if ok else "对话模型连接失败：") + message,
    }


@router.post("/api-config/probe/embedding")
def probe_embedding(admin: AdminUser) -> dict:
    """AI 连接检测：向量化服务。沿用旧版 `_test_embedding()` 的三条判据。"""
    service = embeddings.get_service()
    if not service.configured:
        return {"ok": False, "message": "向量化连接失败：未配置向量化密钥，无法测试。"}
    try:
        vectors = service.embed(["连接测试"])
    except ZhigouError as exc:
        return {"ok": False, "message": "向量化连接失败：" + to_user_message(exc)}
    except Exception:  # noqa: BLE001 - 探测类接口不能把堆栈抛给界面
        return {"ok": False, "message": "向量化连接失败：出现未预期错误。"}
    if not vectors or len(vectors[0]) != config.embedding_dim():
        return {"ok": False, "message": "向量化连接失败：返回维度与配置不一致。"}
    return {
        "ok": True,
        "message": f"向量化连接正常：{service.model} · {len(vectors[0])} 维。",
    }


# --------------------------------------------------------------------------
# 商品维护（旧版「商品维护」页）
# --------------------------------------------------------------------------


class ProductPayload(BaseModel):
    id: str = Field(default="", max_length=128)
    name: str = Field(default="", max_length=200)
    model: str = ""
    brand: str = ""
    category: str = ""
    price: str | float | None = None
    specs: str = ""  # 每行「键=值」
    use_cases: str = ""  # 一行一条
    pros: str = ""
    cons: str = ""
    image_url: str = ""
    source_url: str = ""


class ActivePayload(BaseModel):
    is_active: bool


def _price(value: str | float | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise BadRequest("价格格式不正确，请填写数字。") from exc


def _record(payload: ProductPayload) -> dict[str, Any]:
    return {
        "id": payload.id.strip(),
        "name": payload.name.strip(),
        "brand": payload.brand.strip(),
        "category": payload.category,
        "model": payload.model.strip(),
        "price": _price(payload.price),
        "image_url": payload.image_url,
        "source_url": payload.source_url,
        "specs": catalog_admin.text_to_specs(payload.specs),
        "use_cases": catalog_admin.lines_to_list(payload.use_cases),
        "pros": catalog_admin.lines_to_list(payload.pros),
        "cons": catalog_admin.lines_to_list(payload.cons),
    }


@router.get("/products")
def admin_products(admin: AdminUser) -> dict:
    return {"items": catalog_admin.list_products()}


@router.post("/products")
def create_product(payload: ProductPayload, admin: AdminUser) -> dict:
    if not payload.id.strip():
        raise BadRequest("商品 ID 不能为空。")
    return {"item": catalog_admin.create_product(admin, _record(payload))}


@router.put("/products/{product_id}")
def update_product(product_id: str, payload: ProductPayload, admin: AdminUser) -> dict:
    # EDITABLE_FIELDS 之外的字段由 catalog_admin.update_product 自己过滤。
    return {"item": catalog_admin.update_product(admin, product_id, _record(payload))}


@router.put("/products/{product_id}/active")
def set_product_active(
    product_id: str, payload: ActivePayload, admin: AdminUser
) -> dict:
    return {"ok": catalog_admin.set_active(admin, product_id, payload.is_active)}


# --------------------------------------------------------------------------
# 品类 / 品牌元信息
# --------------------------------------------------------------------------


class CategoryMetaPayload(BaseModel):
    display_label: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class BrandMetaPayload(BaseModel):
    display_name: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


@router.get("/catalog-meta")
def get_catalog_meta(admin: AdminUser) -> dict:
    """按「品类大类」组织元数据。

    `CategoryEntry.label` 本来就是中文展示名（来自 config.CATEGORY_LABELS），
    上一版界面误把英文 `key` 当展示名、又绑了不存在的 `display_label`，
    所以出现「laptop / phone + 空输入框」。这里统一给出中文字段，
    并把每个品类下实际出现的品牌一并算出，供界面按大类分组展示。
    """
    catalog = get_catalog()
    products = catalog.products if catalog else []

    brand_categories: dict[str, list[str]] = {}
    for product in products:
        if not product.brand or not product.category:
            continue
        seen = brand_categories.setdefault(product.brand, [])
        if product.category not in seen:
            seen.append(product.category)

    categories: list[dict[str, Any]] = []
    for entry in catalog_meta.category_entries():
        in_category = catalog.by_category(entry.key) if catalog else []
        categories.append(
            {
                "key": entry.key,
                "label": entry.label,
                "display_label": entry.label,
                "sort_order": entry.sort_order,
                "is_active": entry.is_active,
                "custom_label": entry.custom_label,
                "product_count": len(in_category),
                "brands": sorted({p.brand for p in in_category if p.brand}),
            }
        )

    brands: list[dict[str, Any]] = []
    for entry in catalog_meta.brand_entries(products):
        row = to_jsonable(entry)
        row["categories"] = brand_categories.get(entry.brand_name, [])
        brands.append(row)
    return {"categories": categories, "brands": brands}


@router.put("/catalog-meta/category/{key}")
def set_category(key: str, payload: CategoryMetaPayload, admin: AdminUser) -> dict:
    catalog_meta.set_category_meta(
        admin,
        key,
        display_label=payload.display_label,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    return {"ok": True}


@router.put("/catalog-meta/brand/{brand_name}")
def set_brand(brand_name: str, payload: BrandMetaPayload, admin: AdminUser) -> dict:
    catalog_meta.set_brand_meta(
        admin,
        brand_name,
        display_name=payload.display_name,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    return {"ok": True}


# --------------------------------------------------------------------------
# 用户管理
# --------------------------------------------------------------------------


class UserCreatePayload(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=256)
    role: str = "user"


class RolePayload(BaseModel):
    role: str


class PasswordPayload(BaseModel):
    password: str = Field(min_length=8, max_length=256)


@router.get("/users")
def admin_users(admin: AdminUser) -> dict:
    return {
        "users": [
            u.model_dump(mode="json", exclude={"password_hash"})
            for u in database.list_users()
        ]
    }


@router.post("/users")
def create_user(payload: UserCreatePayload, admin: AdminUser) -> dict:
    user = database.create_user(payload.username, payload.password, payload.role)
    return {"user": user.model_dump(mode="json", exclude={"password_hash"})}


@router.put("/users/{username}/role")
def set_role(username: str, payload: RolePayload, admin: AdminUser) -> dict:
    database.set_user_role(username, payload.role, viewer=admin)
    return {"ok": True}


@router.put("/users/{username}/password")
def set_password(username: str, payload: PasswordPayload, admin: AdminUser) -> dict:
    database.set_user_password(username, payload.password, viewer=admin)
    return {"ok": True}


@router.put("/users/{username}/active")
def set_user_active(username: str, payload: ActivePayload, admin: AdminUser) -> dict:
    database.set_user_active(username, payload.is_active, viewer=admin)
    return {"ok": True}


@router.delete("/users/{username}")
def delete_user(username: str, admin: AdminUser) -> dict:
    histories, favorites = database.delete_user(username, viewer=admin)
    return {"ok": True, "deleted_histories": histories, "deleted_favorites": favorites}


# --------------------------------------------------------------------------
# 知识库管理
# --------------------------------------------------------------------------


class DocumentPayload(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    doc_type: str = "service"
    body: str = Field(min_length=1)
    source: str = "本项目整理（非厂商资料）"
    category: str = ""


class RetrievePayload(BaseModel):
    query: str = Field(min_length=1, max_length=500)


def _document_rows() -> list[dict]:
    docs = corpus.load_documents(config.knowledge_dir())
    return [
        {
            "doc_id": getattr(doc, "doc_id", ""),
            "title": getattr(doc, "title", ""),
            "doc_type": getattr(doc, "doc_type", ""),
            "category": getattr(doc, "category", ""),
            "source_path": str(getattr(doc, "source_path", "") or ""),
            "deletable": getattr(doc, "doc_type", "") != "product",
        }
        for doc in docs
    ]


@router.get("/knowledge/documents")
def knowledge_documents(admin: AdminUser) -> dict:
    return {"documents": _document_rows()}


@router.post("/knowledge/documents")
def create_document(payload: DocumentPayload, admin: AdminUser) -> dict:
    path = knowledge_docs.create_document(
        title=payload.title,
        doc_type=payload.doc_type,
        body=payload.body,
        source=payload.source,
        category=payload.category,
    )
    return {"ok": True, "path": str(path), "documents": _document_rows()}


@router.delete("/knowledge/documents/{doc_id}")
def delete_document(doc_id: str, admin: AdminUser) -> dict:
    path = knowledge_docs.delete_document(doc_id)
    return {"ok": True, "path": str(path), "documents": _document_rows()}


@router.post("/knowledge/retrieve")
def knowledge_retrieve(payload: RetrievePayload, admin: AdminUser) -> dict:
    """检索调试：沿用旧版的向量优先 / 关键词回退，并把模式与提示如实返回。"""
    from src.knowledge.retrieval import retrieve
    from src.ui.state import get_knowledge_index, get_vector_store

    result = retrieve(
        payload.query,
        index=get_knowledge_index(),
        store=get_vector_store(),
        service=embeddings.get_service(),
    )
    passages = [to_jsonable(p) for p in result.passages]
    return {
        "mode": result.mode,
        "note": result.note,
        "passages": passages,
        "count": len(passages),
    }


@router.post("/knowledge/reindex")
def knowledge_reindex(admin: AdminUser) -> dict:
    """重建索引：清除进程内缓存，让下次检索按文件时间戳自动重建（旧版同一机制）。"""
    from src.ui import state

    cleared = 0
    for name in ("_load_index_cached", "_index_cache"):
        cached = getattr(state, name, None)
        if hasattr(cached, "cache_clear"):
            cached.cache_clear()
            cleared += 1
    return {"ok": True, "cleared_caches": cleared, "documents": _document_rows()}


# --------------------------------------------------------------------------
# 全站历史记录
# --------------------------------------------------------------------------


@router.get("/analyses")
def all_analyses(admin: AdminUser) -> dict:
    return {"entries": [to_jsonable(e) for e in database.list_analyses(limit=100)]}


@router.delete("/analyses/{entry_id}")
def delete_any_analysis(entry_id: int, admin: AdminUser) -> dict:
    deleted = database.delete_analysis(entry_id, viewer=admin)
    if not deleted:
        return {"ok": False, "message": "记录不存在或已被删除"}
    return {"ok": True}
