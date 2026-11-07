"""API 请求体模型。

只约束外部输入的边界；业务领域模型继续用 `src/demand_parser.Demand` 等。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(LoginRequest):
    pass


class AnalysisRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    category: str = Field(default="", max_length=64)
    budget: str | float | None = None
    brand: str = Field(default="", max_length=64)


class CompareRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list, max_length=8)
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
