"""API 请求体模型。

只约束外部输入的边界；业务领域模型继续用 `src/demand_parser.Demand` 等。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src import config


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


# 注册只需要用户名 + 密码，与登录完全一致。保留别名而不是空子类：
# 空子类不增加任何约束，却会让 OpenAPI 里出现一个内容重复的模型。
RegisterRequest = LoginRequest


class AnalysisRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    category: str = Field(default="", max_length=64)
    budget: str | float | None = None
    brand: str = Field(default="", max_length=64)


class CompareRequest(BaseModel):
    # 与 config.MAX_COMPARE_COUNT、services.compare_products、前端 MAX_SELECTED 同源，
    # 避免「Pydantic 放行 8 件、业务层拒绝 6 件」这种两层口径打架。
    product_ids: list[str] = Field(
        default_factory=list, max_length=config.MAX_COMPARE_COUNT
    )
    text: str = Field(default="", max_length=2000)


class QARequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class FavoriteRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=128)


class PreferencesUpdate(BaseModel):
    ai_enhanced: bool = True
    price_priority: Literal["none", "value", "performance", "brand"] = "none"
    show_over_budget: bool = True
    auto_apply: bool = True
