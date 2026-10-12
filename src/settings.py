"""用户偏好设置的读写。

存成独立的 JSON 文件（`storage/settings.json`），不放进数据库：
设置项很少，而且它与「分析历史」是性质完全不同的数据——历史是不可变的
记录，设置是可随时改的配置。混在一张表里反而要额外区分。
阶段四接入 SQLite 时若确实需要统一存储再迁移。

放在业务层而不是界面层，是为了让「偏好如何影响需求」这件事可以被单元测试。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src import config
from src.demand_parser import Demand

#: 价格取向。取值与界面选项一一对应。
PricePriority = Literal["none", "value", "performance", "brand"]

#: 价格取向 → 中文名
PRICE_PRIORITY_LABELS: dict[str, str] = {
    "none": "不限",
    "value": "性价比优先",
    "performance": "性能优先",
    "brand": "品牌优先",
}

#: 价格取向 → 自动补进「核心需求」的词。
#: 品牌优先不在此列——它影响的是筛选范围，不是评分维度。
_PRIORITY_TO_NEED: dict[str, str] = {
    "value": "性价比",
    "performance": "性能",
}

#: 可选的关注项。与解析器识别的核心需求词保持一致。
FOCUS_OPTIONS: tuple[str, ...] = ("性能", "性价比", "续航", "便携", "音质", "降噪", "静音", "拍照")


class UserPreferences(BaseModel):
    """用户偏好设置。所有字段都有默认值，文件缺失时也能正常构造。"""

    model_config = ConfigDict(extra="ignore")

    #: 常用品牌。填了就在分析时优先按这些品牌筛选。
    brand_preferences: list[str] = Field(default_factory=list)

    #: 价格取向。
    #: 默认 **"none"** 而不是某个具体取向：全新安装时用户并没有做过这个选择，
    #: 替他默认「性价比优先」等于每次分析都悄悄往需求里塞一个核心需求。
    price_priority: PricePriority = "none"

    #: 长期关注的点，会自动并入每次分析的核心需求。
    focus_areas: list[str] = Field(default_factory=list)

    #: 是否在结果里展示超预算商品。关掉后只保留预算内。
    show_over_budget: bool = True

    #: 是否在分析时自动带上上面的偏好。关掉则完全手动。
    auto_apply: bool = True

    def price_priority_label(self) -> str:
        return PRICE_PRIORITY_LABELS.get(self.price_priority, self.price_priority)

    def effective_core_needs(self) -> list[str]:
        """偏好折算出的核心需求词，去重且保持顺序。"""
        needs: list[str] = []
        priority_need = _PRIORITY_TO_NEED.get(self.price_priority)
        if priority_need:
            needs.append(priority_need)
        for area in self.focus_areas:
            if area not in needs:
                needs.append(area)
        return needs


def default_preferences() -> UserPreferences:
    return UserPreferences()


def settings_path(path: Path | None = None) -> Path:
    return Path(path) if path is not None else config.settings_path()


def load_preferences(path: Path | None = None) -> UserPreferences:
    """读取偏好设置。

    **不抛异常**：设置文件损坏或缺失时静默退回默认值。
    理由是这个文件只影响便利性，不影响正确性——为它中断整个应用不值得。
    想排查的话，返回值上的 `loaded` 标记可以看。
    """
    target = settings_path(path)
    if not target.is_file():
        return default_preferences()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return default_preferences()

    if not isinstance(raw, dict):
        return default_preferences()

    try:
        return UserPreferences.model_validate(raw)
    except Exception:  # noqa: BLE001 - 字段类型不对就整体退回默认值
        return default_preferences()


def save_preferences(prefs: UserPreferences, path: Path | None = None) -> Path:
    """写入偏好设置，返回实际写入的路径。

    先写临时文件再原子替换，避免写到一半被中断留下半个 JSON。
    """
    target = settings_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(prefs.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, target)
    return target


def apply_preferences(prefs: UserPreferences, demand: Demand) -> Demand:
    """把偏好并进一份需求里，**只补空缺、不覆盖用户本次的输入**。

    这条顺序很重要：用户在分析页明确填了预算或品牌，就必须以他这次填的为准；
    偏好只是「懒得每次重填」的默认值，不能反过来盖掉用户的当次选择。
    """
    if not prefs.auto_apply:
        return demand

    merged_needs = list(demand.core_needs)
    for need in prefs.effective_core_needs():
        if need not in merged_needs:
            merged_needs.append(need)

    merged_brands = list(demand.brand_preferences)
    if not merged_brands:
        merged_brands = list(prefs.brand_preferences)

    # Demand 是 pydantic 模型，用 model_copy 而不是 dataclasses.replace
    return demand.model_copy(
        update={
            "core_needs": merged_needs,
            "brand_preferences": merged_brands,
            "source": "merged",
        }
    )
