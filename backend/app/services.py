"""业务桥接层：把 HTTP 请求翻译成对 `src/` 已有函数的调用。

**这一层不实现业务规则。** 筛选、评分、比较、报告、落库全部沿用 Streamlit 版
同一批函数，因此 Vue 版与旧版结论一致，1114 条测试继续覆盖这些逻辑。
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src import ai_enhance, ai_service, comparison, config, database, settings
from src.auth import User
from src.data_loader import Catalog, load_catalog
from src.demand_parser import (
    Demand,
    detect_unsupported_category,
    follow_up_questions,
    merge_demand,
    parse_budget_value,
    parse_demand,
    unsupported_category_message,
)
from src.recommender import recommend
from src.report_service import build_report

from backend.app.schemas import AnalysisRequest, PreferencesUpdate


class BadRequest(Exception):
    """输入不合规。路由层转成 400，文案可直接展示。"""


class ServiceUnavailable(Exception):
    """依赖不可用。路由层转成 503。"""


def to_jsonable(value: Any) -> Any:
    """把 dataclass / pydantic 模型递归转成可 JSON 序列化的结构。"""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    return value


def get_catalog() -> Catalog:
    return load_catalog()


def _build_demand(payload: AnalysisRequest, catalog: Catalog) -> Demand:
    raw_text = payload.text.strip()
    if not raw_text and not payload.category and not payload.budget:
        raise BadRequest("请描述需求，或至少选择品类 / 填写预算。")

    term = detect_unsupported_category(raw_text)
    if term:
        raise BadRequest(unsupported_category_message(term))

    try:
        parsed = (
            parse_demand(raw_text, known_brands=catalog.brands())
            if raw_text
            else Demand()
        )
        structured = Demand(
            category=payload.category,
            budget=parse_budget_value(payload.budget),
            brand_preferences=[payload.brand] if payload.brand else [],
        )
        return merge_demand(structured, parsed) if raw_text else structured
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def run_analysis(payload: AnalysisRequest, user: User) -> dict:
    """一次完整分析：解析 → 追问 / 偏好 → 推荐 → 报告 → 落库。"""
    catalog = get_catalog()
    demand = _build_demand(payload, catalog)

    questions = follow_up_questions(demand)
    if questions:
        return {"status": "need_info", "questions": questions}

    prefs = settings.load_preferences(user)
    applied = settings.apply_preferences(prefs, demand)
    result = recommend(catalog, applied)
    if not prefs.show_over_budget:
        result.over_budget = []
    report = build_report(catalog, applied, result)
    database.save_analysis(report, user_id=user.username)

    return {
        "status": "ok",
        "report": report.to_dict(),
        "ai_enhanced": False,
        "preferences_applied": prefs.auto_apply,
    }


def list_products(category: str = "") -> dict:
    catalog = get_catalog()
    products = catalog.by_category(category) if category else catalog.products
    return {
        "products": [p.model_dump(mode="json") for p in products],
        "categories": [
            {"key": key, "label": config.category_label(key)}
            for key in catalog.present_categories()
        ],
        "brands": catalog.brands(),
        "total": len(catalog.products),
        "dataset_name": catalog.dataset_name,
        "disclaimer": catalog.disclaimer,
        "issues": catalog.issues,
    }


def compare_products(product_ids: list[str], text: str) -> dict:
    catalog = get_catalog()
    products = [p for pid in product_ids if (p := catalog.get(pid)) is not None]
    if len(products) < 2:
        raise BadRequest("至少选择 2 件商品才能横向比较。")
    demand = (
        parse_demand(text.strip(), known_brands=catalog.brands())
        if text.strip()
        else None
    )
    table = comparison.compare(products, demand)
    return to_jsonable(table)


def _qa_product_detail(item: Any) -> dict:
    """把一条推荐结果整理成界面可直接展示的中文商品详情。

    标签统一取 `config.SPEC_LABELS` / `DIMENSION_LABELS`，参数值走
    `comparison.format_param`——与商品比较页同一套口径，避免两处显示不一致。
    """
    product = item.product
    score = item.score
    specs = []
    for key, value in product.specs.items():
        # 数据源里有 "True"/"False" 字符串，先归一成布尔再格式化，
        # 否则 format_param 会把字符串 "False" 当成真值。
        normalized = value
        if isinstance(value, str) and value in {"True", "False"}:
            normalized = value == "True"
        specs.append(
            {
                "key": key,
                "label": config.SPEC_LABELS.get(key, key),
                "value": comparison.format_param(key, normalized),
            }
        )
    return {
        "id": product.id,
        "name": product.name,
        "brand": product.brand,
        "model": product.model,
        "category_label": config.category_label(product.category),
        "price": product.price,
        "score_total": round(float(score.total), 1),
        "budget_label": item.budget_label,
        "within_budget": item.within_budget,
        "use_cases": list(product.use_cases),
        "pros": list(product.pros),
        "cons": list(product.cons),
        "specs": specs,
        "dimensions": [
            {
                "key": dim.key,
                "label": config.DIMENSION_LABELS.get(dim.key, dim.key),
                "score": round(float(dim.score), 1),
                "weight": dim.weight,
                "reason": dim.reason,
            }
            for dim in score.dimensions
        ],
        "data_source": product.data_source,
        "data_status": product.data_status,
        "updated_at": product.updated_at,
        "price_source": product.price_source,
        "price_collected_at": product.price_collected_at,
        "source_url": product.source_url,
        "image_url": product.image_url,
    }


def answer_question(question: str, user: User) -> dict:
    """AI 问答：与旧版同构的「检索 → 商品意图 → 选回答策略 → 失败回退」链路。

    响应始终带 `source` / `retrieval_mode` / `citations`，如实告诉界面这句话
    是来自知识库、商品库、模型通用知识，还是本地规则；不编造价格与参数。
    """
    catalog = get_catalog()

    # 1) 知识检索：向量优先，失败自动回退关键词（旧版 retrieval.retrieve 的职责）
    passages: list = []
    retrieval_mode = "unavailable"
    retrieval_note = "知识检索暂不可用，已回退到本地规则。"
    try:
        from src.knowledge import embeddings
        from src.knowledge.retrieval import retrieve
        from src.ui.state import get_knowledge_index, get_vector_store

        found = retrieve(
            question,
            index=get_knowledge_index(),
            store=get_vector_store(),
            service=embeddings.get_service(),
        )
        passages = list(found.passages)
        retrieval_mode = found.mode
        retrieval_note = found.note
    except Exception:  # noqa: BLE001 - 检索链路失败不能拖垮问答
        pass

    # 2) 商品意图：从本地商品库筛真实候选
    demand = parse_demand(question, known_brands=catalog.brands())
    has_product_intent = bool(
        demand.category or demand.budget or demand.brand_preferences
    )
    raw_items = (
        recommend(catalog, demand, limit=5).all_items()[:5]
        if has_product_intent
        else []
    )
    products = [_qa_product_detail(item) for item in raw_items]

    citations = [
        {
            "title": str(getattr(p, "title", "") or ""),
            "excerpt": str(getattr(p, "excerpt", "") or "")[:240],
        }
        for p in passages
    ]

    # 3) 已配置模型时，按旧版的策略选一种组织方式
    service = None
    try:
        candidate = ai_service.get_service()
        if config.llm_api_key():
            service = candidate
    except Exception:  # noqa: BLE001
        service = None

    if service is not None:
        try:
            if passages and raw_items:
                answer = ai_enhance.answer_with_products(
                    question, passages, raw_items, service=service
                )
                source = "knowledge+products"
            elif passages:
                answer = ai_enhance.answer_from_knowledge(
                    question, passages, service=service
                )
                source = "knowledge"
            else:
                answer = ai_enhance.answer_from_general_knowledge(
                    question, service=service
                )
                source = "general-knowledge"
            return {
                "answer": answer,
                "source": source,
                "products": products,
                "citations": citations,
                "retrieval_mode": retrieval_mode,
                "retrieval_note": retrieval_note,
            }
        except Exception:  # noqa: BLE001 - 模型失败必须回退规则链路
            pass

    # 4) 规则回退：只用本地商品库里真实存在的条目
    if products:
        names = "、".join(
            str(item.get("name", "")) for item in products if item.get("name")
        )
        text = (
            f"根据本地商品库，和「{question}」最相关的是：{names}。"
            "以下是规则筛选的结果，价格为数据集参考价，请以下单页为准。"
        )
        source = "catalog"
    else:
        text = (
            "本地商品库里没有找到能回答这个问题的商品。可以换个说法，"
            "或在「个人设置 → API 配置」里配置模型后使用 AI 通用知识回答。"
        )
        source = "empty"
    return {
        "answer": text,
        "source": source,
        "products": products,
        "citations": citations,
        "retrieval_mode": retrieval_mode,
        "retrieval_note": retrieval_note,
    }


def get_preferences(user: User) -> dict:
    return settings.load_preferences(user).model_dump(mode="json")


def update_preferences(user: User, payload: PreferencesUpdate) -> dict:
    prefs = settings.UserPreferences(**payload.model_dump())
    settings.save_preferences(user, prefs)
    return prefs.model_dump(mode="json")


def admin_overview() -> dict:
    healthy, message = database.check_health()
    if not healthy:
        raise ServiceUnavailable(message)
    catalog = get_catalog()
    users = database.list_users()
    return {
        "healthy": healthy,
        "message": message,
        "user_count": len(users),
        "admin_count": database.count_active_admins(),
        "users": [u.model_dump(mode="json", exclude={"password_hash"}) for u in users],
        "product_count": len(catalog.products),
        "incomplete_products": catalog.incomplete_count,
        "categories": [
            {"key": key, "label": config.category_label(key)}
            for key in catalog.present_categories()
        ],
        "dataset_name": catalog.dataset_name,
        "dataset_updated_at": catalog.dataset_updated_at,
    }


def eval_summary() -> dict:
    """评测快照。文件不存在时如实返回空，不编造指标。"""
    candidates = sorted(Path("data/evaluation").glob("report.json"))
    if not candidates:
        return {"available": False, "reason": "尚未生成评测报告快照"}
    try:
        payload = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": f"报告读取失败：{exc}"}
    return {"available": True, "file": str(candidates[0]), "payload": payload}


def about_info() -> dict:
    catalog = get_catalog()
    healthy, message = database.check_health()
    return {
        "name": "智购参谋",
        "score_display_name": config.SCORE_DISPLAY_NAME,
        "categories": [
            {"key": key, "label": config.category_label(key)}
            for key in catalog.present_categories()
        ],
        "product_count": len(catalog.products),
        "dataset_name": catalog.dataset_name,
        "disclaimer": catalog.disclaimer,
        "database_healthy": healthy,
        "database_message": message,
        "frontend": "Vue 3 + Vite + TypeScript",
        "backend": "FastAPI + Python",
    }
