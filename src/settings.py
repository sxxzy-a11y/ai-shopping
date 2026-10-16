"""用户偏好设置的读写。

**按用户存在数据库里**（`user_preferences` 表，见 `src/database.py`）。

旧版本是一份全局的 `storage/settings.json`。那在多用户下不是「功能缺失」，
而是**一个人的设置作用在另一个人身上**：李四的分析会被张三的偏好影响
（design D6）。

那份文件没有丢：内容被收编成**新用户的初始偏好模板**（`preference_template`
表），文件本身改名为 `settings.json.bak`。不把它归给初始管理员——
单用户时期那份偏好是谁设的我们并不知道，编一个归属不如让它成为默认值。

放在业务层而不是界面层，是为了让「偏好如何影响需求」这件事可以被单元测试。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src import config
from src.auth import User
from src.demand_parser import Demand
from src.errors import PermissionDenied, ZhigouError
from src import database

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


class UserPreferences(BaseModel):
    """用户偏好设置。所有字段都有默认值，没有记录时也能正常构造。"""

    model_config = ConfigDict(extra="ignore")

    #: **全局 AI 总开关**。开启且已配置密钥时，智能分析与 AI 问答走 AI 增强；
    #: 关闭则全部走本地规则。默认开启——「一直保持增强」是默认体验。
    ai_enhanced: bool = True

    #: 价格取向。
    #: 默认 **"none"** 而不是某个具体取向：全新安装时用户并没有做过这个选择，
    #: 替他默认「性价比优先」等于每次分析都悄悄往需求里塞一个核心需求。
    price_priority: PricePriority = "none"

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
        return needs


def default_preferences() -> UserPreferences:
    return UserPreferences()


def settings_path(path: Path | None = None) -> Path:
    """单用户时期那份 JSON 文件的路径。

    **它已经不是偏好的存储了**，只剩下一个用途：`adopt_legacy_settings_file()`
    要知道去哪儿找那份需要收编的旧文件。
    """
    return Path(path) if path is not None else config.settings_path()


def _parse(raw: str) -> UserPreferences:
    """把一段 JSON 解析成偏好。字段类型不对就整体退回默认值。

    偏好只影响便利性，不影响正确性——为它中断整个应用不值得。
    旧版本可能留着 `brand_preferences` / `focus_areas` 键，
    `extra="ignore"` 会静默忽略。
    """
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default_preferences()
    if not isinstance(decoded, dict):
        return default_preferences()
    try:
        return UserPreferences.model_validate(decoded)
    except Exception:  # noqa: BLE001 - 字段类型不对就整体退回默认值
        return default_preferences()


def _template_preferences(path: Path | None = None) -> UserPreferences:
    """新用户的初始偏好：模板 → 没有模板则代码默认值。"""
    try:
        raw = database.read_template_json(path)
    except ZhigouError:
        return default_preferences()
    return _parse(raw) if raw is not None else default_preferences()


def load_preferences(user: User | None, path: Path | None = None) -> UserPreferences:
    """读取**该用户**的偏好。

    - 未登录（`user is None`）→ 默认值，**不碰数据库**
    - 没有记录 → 用「新用户初始模板」，仍没有则用代码默认值。
      **不写库**：读操作不留副作用，第一次保存设置时才落行。
    - 数据库读不出来 → 默认值（偏好坏了不该让页面打不开）
    """
    if user is None:
        return default_preferences()

    try:
        raw = database.read_preferences_json(user.username, path)
    except ZhigouError:
        return default_preferences()

    return _parse(raw) if raw is not None else _template_preferences(path)


def save_preferences(
    user: User | None, prefs: UserPreferences, path: Path | None = None
) -> None:
    """保存该用户的偏好。

    Raises:
        PermissionDenied: 未登录。**这是刻意的**——偏好必须有归属，
        没有归属就只能丢掉；静默丢掉一个用户刚点的保存，比报错更糟。
    """
    if user is None:
        raise PermissionDenied(
            "未登录，无法保存偏好设置。", detail="save_preferences 收到 user=None"
        )

    database.write_preferences_json(
        user.username,
        json.dumps(prefs.model_dump(), ensure_ascii=False),
        path,
    )


def adopt_legacy_settings_file(path: Path | None = None) -> Path | None:
    """把单用户时期那份 `settings.json` 收编成「新用户初始偏好模板」。

    两件事的顺序**不能反**：先把内容读进模板，再把文件改名。
    反过来先改名的话，中途失败就只剩一个 `.bak`，模板里什么都没有。

    幂等：文件不在就什么都不做。返回改名后的备份路径（没做事则 `None`）。

    注意 `path` 只指定**那份旧文件**在哪；模板写进当前生效的数据库
    （与其他读写一样走 `database` 的默认路径）。
    """
    source = settings_path(path)
    if not source.is_file():
        return None

    try:
        raw = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raw = ""

    prefs = _parse(raw) if raw else default_preferences()
    database.write_template_json(json.dumps(prefs.model_dump(), ensure_ascii=False))

    backup = source.with_name(source.name + ".bak")
    try:
        os.replace(source, backup)
    except OSError:
        # 改名失败不影响已经写好的模板：下次启动还会再试一遍（幂等）。
        return None
    return backup


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

    # Demand 是 pydantic 模型，用 model_copy 而不是 dataclasses.replace。
    # source 改为 "merged"：标记这条需求混入了偏好，界面据此提示。
    return demand.model_copy(
        update={"core_needs": merged_needs, "source": "merged"}
    )
