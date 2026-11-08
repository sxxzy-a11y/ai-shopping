"""四个工具的声明与实现。

每个工具都是**已有业务函数的一层薄封装**——`search_products` 调 `recommender`，
`compare_products` 调 `comparison`，`search_knowledge` 调知识检索层。
不重复实现业务逻辑，也就不存在「Agent 算出来的和界面算出来的不一样」。

参数校验分两层（design.md D2）：

1. **形状层**：pydantic 模型管类型、必填与取值域
2. **语义层**：工具自己管「这个值在我们的数据里存在吗」——
   品类得是已知品类，商品 ID 得真在数据集里。pydantic 拦不住这两类错误，
   而模型编造它们太容易了。

**刻意不做模糊纠正**：模型把品类写成「笔记本」而不是 `laptop` 时直接拒绝，
不替它猜。猜测纠正等于替模型圆场，会掩盖它没按 schema 给值的事实——
而那恰恰是「参数校验在起作用」的可见证据。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src import config
from src.agent.registry import Tool, ToolContext, ToolResult, ToolRegistry
from src.demand_parser import Demand
from src.scoring import normalize_use_case, spec_bounds

# --------------------------------------------------------------------------
# 参数模型（形状层）
# --------------------------------------------------------------------------


class SearchProductsParams(BaseModel):
    """按条件筛选商品。"""

    category: str | None = Field(
        default=None,
        description=f"商品类别键，可选值：{'、'.join(sorted(config.CATEGORY_LABELS))}。不指定则跨类别检索。",
    )
    budget_max: float | None = Field(default=None, description="预算上限（元）")
    budget_min: float | None = Field(default=None, description="预算下限（元）")
    use_cases: list[str] = Field(default_factory=list, description="使用场景关键词")
    core_needs: list[str] = Field(default_factory=list, description="核心需求关键词")
    limit: int = Field(default=5, ge=1, le=10, description="最多返回几件商品")


class ProductDetailParams(BaseModel):
    """按商品 ID 取详情。"""

    product_id: str = Field(description="商品 ID，例如 LP001")


class CompareParams(BaseModel):
    """比较多件商品。"""

    product_ids: list[str] = Field(description="要比较的商品 ID 列表，2 到 5 件")
    focus: list[str] = Field(
        default_factory=list, description="重点关注的维度，例如「重量」「续航」"
    )


class SearchKnowledgeParams(BaseModel):
    """检索知识库。"""

    query: str = Field(description="用户的问题原文")
    limit: int = Field(default=3, ge=1, le=5, description="最多返回几条资料")


class FindSimilarProductsParams(BaseModel):
    """找相似商品。同品类内按规则算接近度，不依赖向量库。"""

    product_id: str = Field(description="作为参照的商品 ID")
    limit: int = Field(default=3, ge=1, le=6, description="最多返回几件相似商品")


class GetUserProfileParams(BaseModel):
    """读取当前登录用户的偏好画像。

    刻意不收 `user_id`：用户身份只能从 `ToolContext` 取，
    否则模型可以传别人的 ID 去读别人的收藏与历史。
    """


def _check_budget_range(params: SearchProductsParams) -> str | None:
    for name, value in (
        ("budget_min", params.budget_min),
        ("budget_max", params.budget_max),
    ):
        if value is not None and value <= 0:
            return f"{name} 必须是正数，收到 {value:g}"
    if (
        params.budget_min is not None
        and params.budget_max is not None
        and params.budget_min > params.budget_max
    ):
        return f"budget_min({params.budget_min:g}) 不能大于 budget_max({params.budget_max:g})"
    return None


def _check_category(category: str | None) -> str | None:
    if category and category not in config.CATEGORY_LABELS:
        available = "、".join(sorted(config.CATEGORY_LABELS))
        return f"没有「{category}」这个类别。可用类别：{available}"
    return None


# --------------------------------------------------------------------------
# 结果摘要
# --------------------------------------------------------------------------


def _product_brief(product) -> dict[str, Any]:
    """给模型看的商品摘要。只放数据里真有的字段。"""
    return {
        "product_id": product.id,
        "name": product.name,
        "brand": product.brand,
        "category": product.category,
        "price": product.price,
        "specs": product.specs,
        "use_cases": product.use_cases,
        "pros": product.pros,
        "cons": product.cons,
    }


def _reject_ids(ids: list[str], catalog) -> str | None:
    """返回不存在的商品 ID 说明，全部存在时返回 None。"""
    missing = [pid for pid in ids if catalog.get(pid) is None]
    if missing:
        return f"这些商品 ID 不存在：{'、'.join(missing)}"
    return None


# --------------------------------------------------------------------------
# 工具实现
# --------------------------------------------------------------------------


def _run_search_products(
    params: SearchProductsParams, context: ToolContext
) -> ToolResult:
    problem = _check_category(params.category) or _check_budget_range(params)
    if problem:
        return ToolResult.rejected(problem)

    demand = Demand(
        raw_text="（由 Agent 工具调用发起）",
        category=params.category or "",
        budget=params.budget_max,
        use_cases=list(params.use_cases),
        core_needs=list(params.core_needs),
        source="rule",
    )
    from src.recommender import recommend

    result = recommend(context.catalog, demand, limit=params.limit)
    items = result.within_budget
    # `recommend` 只认预算上界。模型给了下限时必须在这里再筛一遍，
    # 否则「3000–5000 元」会返回 2000 元的商品，而工具还回报成功——
    # 参数校验放行了，筛选却没用上，是最容易瞒过用户的一类偏差。
    if params.budget_min is not None:
        floor = params.budget_min
        items = [
            item
            for item in items
            if item.product.price is not None and item.product.price >= floor
        ]

    if not items:
        return ToolResult(
            ok=True,
            payload={
                "matched": 0,
                "message": "没有符合这些条件的商品。可以放宽预算或换个类别再试。",
                "relaxations": list(result.relaxations)[:3],
            },
            summary="没有符合条件的商品",
        )

    payload = {
        "matched": len(items),
        "candidate_count": result.candidate_count,
        "products": [
            {
                **_product_brief(item.product),
                "score": round(item.score.total, 1),
                "match_level": item.score.match_level,
                "budget_status": item.budget_label,
            }
            for item in items
        ],
        "over_budget": [
            {"product_id": item.product.id, "name": item.product.name}
            for item in result.over_budget[:3]
        ],
        "notes": list(result.notes)[:3],
    }
    return ToolResult(
        ok=True,
        payload=payload,
        summary=f"筛选出 {len(items)} 件候选（共 {result.candidate_count} 件参与评估）",
    )


def _run_get_product_detail(
    params: ProductDetailParams, context: ToolContext
) -> ToolResult:
    product = context.catalog.get(params.product_id)
    if product is None:
        return ToolResult.rejected(f"商品 ID「{params.product_id}」不存在")

    payload = {
        **_product_brief(product),
        "data_source": product.data_source,
        "updated_at": product.updated_at,
        "missing_fields": product.missing_fields,
        "data_issues": [issue.reason for issue in product.data_issues],
    }
    return ToolResult(
        ok=True,
        payload=payload,
        summary=f"读取商品详情：{product.name}（{product.price_label}）",
    )


def _run_compare_products(params: CompareParams, context: ToolContext) -> ToolResult:
    ids = params.product_ids
    if len(ids) < config.MIN_COMPARE_COUNT:
        return ToolResult.rejected(
            f"至少需要 {config.MIN_COMPARE_COUNT} 件商品才能比较"
        )
    if len(ids) > config.MAX_COMPARE_COUNT:
        return ToolResult.rejected(f"最多只能比较 {config.MAX_COMPARE_COUNT} 件商品")
    if len(set(ids)) != len(ids):
        return ToolResult.rejected("商品 ID 有重复")

    problem = _reject_ids(ids, context.catalog)
    if problem:
        return ToolResult.rejected(problem)

    products = [context.catalog.get(pid) for pid in ids]
    from src.comparison import compare

    try:
        table = compare([p for p in products if p is not None])
    except Exception as exc:  # noqa: BLE001 —— 混选类别等业务拒绝
        return ToolResult.rejected(f"无法比较：{exc}")

    rows = [
        {
            "dimension": row.label,
            "values": [str(value) for value in row.values],
            "varies": bool(row.varies),
        }
        for row in table.rows
        if row.varies
    ]
    payload = {
        "products": [{"product_id": p.id, "name": p.name} for p in products if p],
        "differing_dimensions": rows,
        "missing_cells": table.missing_cells,
    }
    return ToolResult(
        ok=True,
        payload=payload,
        summary=f"比较 {len(products)} 件商品，{len(rows)} 个维度存在差异",
    )


def _run_search_knowledge(
    params: SearchKnowledgeParams, context: ToolContext
) -> ToolResult:
    if context.knowledge_index is None and not config.is_embedding_configured():
        return ToolResult.rejected("知识库未加载，无法检索")
    if not params.query.strip():
        return ToolResult.rejected("query 不能为空")

    from src.knowledge import retrieval

    result = retrieval.retrieve(
        params.query, index=context.knowledge_index, limit=params.limit
    )
    passages = result.passages
    if not passages:
        # 检索不到**不是错误**，如实说明即可——模型据此可以换个问法或直接说找不到。
        return ToolResult(
            ok=True,
            payload={"found": 0, "message": "知识库里没有与这个问题相关的资料。"},
            summary="知识库中没有相关资料",
        )

    payload = {
        "found": len(passages),
        "retrieval": result.mode,
        "passages": [
            {
                "title": passage.title,
                "type": passage.type_label,
                "content": passage.excerpt,
                "updated_at": passage.updated_at,
            }
            for passage in passages
        ],
    }
    return ToolResult(
        ok=True,
        payload=payload,
        summary=f"检索到 {len(passages)} 条资料（{passages[0].title} 等）",
    )


def _numeric_distance(category: str, left: dict, right: dict) -> float | None:
    """用 `scoring.spec_bounds` 的维度边界把两侧数值归一后求平均距离。

    返回 `None` 表示没有可比的数值维度——调用方据此跳过这一项，
    而不是把「没数据」误当成「完全相似」。
    """
    distances: list[float] = []
    for key in set(left) & set(right):
        bounds = spec_bounds(category, key)
        if bounds is None:
            continue
        low, high = bounds
        if high <= low:
            continue
        try:
            a = float(left[key])
            b = float(right[key])
        except (TypeError, ValueError):
            continue
        distances.append(abs((a - low) / (high - low) - (b - low) / (high - low)))
    return sum(distances) / len(distances) if distances else None


def _run_find_similar_products(
    params: FindSimilarProductsParams, context: ToolContext
) -> ToolResult:
    """同品类内按规则算相似度，不需要向量库。"""
    target = context.catalog.get(params.product_id)
    if target is None:
        return ToolResult.rejected(f"商品 ID「{params.product_id}」不存在")

    ranked: list[tuple[Any, float]] = []
    for other in context.catalog.products:
        # 同品类是硬前提：跨品类比「参数接近」没有意义。
        if other.id == target.id or other.category != target.category:
            continue
        score = 0.0
        distance = _numeric_distance(target.category, target.specs, other.specs)
        if distance is not None:
            score += max(0.0, 1.0 - distance)
        if target.price and other.price:
            score += 1.0 - abs(target.price - other.price) / max(
                target.price, other.price
            )
        left_cases = {normalize_use_case(x) for x in target.use_cases}
        right_cases = {normalize_use_case(x) for x in other.use_cases}
        if left_cases or right_cases:
            score += len(left_cases & right_cases) / len(left_cases | right_cases)
        ranked.append((other, score))

    ranked.sort(key=lambda pair: pair[1], reverse=True)
    matches = [
        {"product": _product_brief(product), "similarity": round(score, 3)}
        for product, score in ranked[: params.limit]
    ]
    return ToolResult(
        ok=True,
        payload={
            "target": _product_brief(target),
            "similar": matches,
            "method": (
                "同品类规格归一距离 + 价格接近度 + 场景重叠；规则计算，不使用向量库"
            ),
        },
        summary=f"为「{target.name}」找到 {len(matches)} 件相似商品",
    )


def _run_get_user_profile(
    params: GetUserProfileParams, context: ToolContext
) -> ToolResult:
    """从本人收藏与历史记录提炼偏好画像。

    `params` 刻意为空：用户身份只能来自 `ToolContext`，模型不能传别人的 ID。
    """
    if not context.user_id:
        return ToolResult.rejected("当前调用没有绑定登录用户，无法读取个人画像")

    from src import database

    try:
        favorites = database.list_favorites(context.user_id)
        history = database.list_analyses_of(context.user_id, limit=10)
    except Exception as exc:  # noqa: BLE001 - 工具失败要如实回报，不拖垮编排
        return ToolResult.failed(f"读取用户画像失败：{exc}")

    brands: dict[str, int] = {}
    categories: dict[str, int] = {}
    for product_id, _added_at in favorites:
        product = context.catalog.get(product_id)
        if product is None:
            continue
        brands[product.brand] = brands.get(product.brand, 0) + 1
        categories[product.category] = categories.get(product.category, 0) + 1

    return ToolResult(
        ok=True,
        payload={
            "user_id": context.user_id,
            "favorite_count": len(favorites),
            "favorite_product_ids": [pid for pid, _ in favorites],
            "favorite_brands": sorted(brands, key=lambda k: brands[k], reverse=True)[
                :5
            ],
            "favorite_categories": sorted(
                categories, key=lambda k: categories[k], reverse=True
            )[:5],
            "recent_analysis_count": len(history),
            "recent_top_products": [
                entry.top_product for entry in history if entry.top_product
            ][:5],
            "note": "画像只由本人收藏与本人历史记录提炼，不含外部数据；未登录时不可用。",
        },
        summary=f"用户画像：{len(favorites)} 条收藏、{len(history)} 条历史",
    )


# --------------------------------------------------------------------------
# 注册表
# --------------------------------------------------------------------------

TOOLS: tuple[Tool, ...] = (
    Tool(
        name="search_products",
        description=(
            "按预算、类别、使用场景、核心需求筛选商品，返回按匹配度排序的候选列表。"
            "需要找商品时用这个。"
        ),
        params_model=SearchProductsParams,
        run=_run_search_products,
    ),
    Tool(
        name="get_product_detail",
        description="按商品 ID 获取一件商品的完整信息，包括参数、优缺点与数据来源。",
        params_model=ProductDetailParams,
        run=_run_get_product_detail,
    ),
    Tool(
        name="compare_products",
        description="横向比较多件商品，返回存在差异的维度。仅支持同类别商品。",
        params_model=CompareParams,
        run=_run_compare_products,
    ),
    Tool(
        name="search_knowledge",
        description=(
            "检索商品知识资料（选购指南、术语解释、常见问题）。"
            "用户问「怎么选」「有什么区别」这类知识性问题时用这个，"
            "而不是用商品数据回答。"
        ),
        params_model=SearchKnowledgeParams,
        run=_run_search_knowledge,
    ),
    Tool(
        name="find_similar_products",
        description=(
            "以某件商品为参照，在同品类里找参数、价格与使用场景最接近的几件。"
            "用户问「有没有类似的」「换个差不多的」时用这个。"
        ),
        params_model=FindSimilarProductsParams,
        run=_run_find_similar_products,
    ),
    Tool(
        name="get_user_profile",
        description=(
            "读取当前登录用户的偏好画像：收藏的品牌/品类、近期分析过的首选商品。"
            "只在用户问「按我的喜好」「我以前看过什么」这类问题时调用；未登录时不可用。"
        ),
        params_model=GetUserProfileParams,
        run=_run_get_user_profile,
    ),
)


def build_registry() -> ToolRegistry:
    """构造标准工具集。"""
    return ToolRegistry(TOOLS)
