## Why

知识问答页已改为「AI 恒开」（`refine-ai-qa`），但智能分析页还留着一个每次都要手动打开的「启用 AI 增强」开关，两页口径不一致；同时分析页的结构化表单有五项输入（类别、预算、主要用途、比较看重、品牌偏好），对一问一答之外的表单而言过重——用途与看重点完全可以在自然语言描述里表达。

## What Changes

- **智能分析页**
  - 移除「启用 AI 增强」开关：配置了密钥即自动走 AI 增强（需求解析 + Agent 编排），无需每次打开
  - 未配置密钥时仍走本地规则（分析有本地形态，**不阻断**——这是它与 AI 问答页的区别），并保留「如何配置」的提示
  - 表单精简为：自然语言描述 + 商品类别 + 预算 + **品牌（选类别后才出现，可选）**
  - 移除「主要用途」「比较看重」「品牌偏好（多选）」三个控件——用途与看重点在描述里写
- **个人设置页**
  - 移除「品牌偏好」「长期关注项」两个设置项（与表单精简对齐：偏好不再替用户决定品牌与关注点）
  - 新增「**AI 增强模式**」开关（默认开启）——这是全局 AI 总开关：开启且已配置密钥时，分析页与 AI 问答页都走 AI；关闭则全部走本地
- **AI 问答页**：尊重全局开关（页面本身仍无开关）；全局关闭时提示「AI 增强已在个人设置中关闭」
- **数据说明保留**：AI 生效时分析页仍展示「会把哪些数据发给模型服务」的说明（开关即长期确认）

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `web-ui`：「需求输入与实时校验反馈」（表单精简 + 品牌级联选择）；「个人设置页」（设置项增删 + AI 总开关）
- `ai-enhancement`：「两种运行模式」（AI 增强的启停位置由个人设置的全局开关控制，默认开启；分析页不再有页级开关）

## Impact

**代码**

| 文件 | 改动 |
|---|---|
| `src/settings.py` | `UserPreferences` 移除 `brand_preferences`/`focus_areas`，新增 `ai_enhanced`（默认 True）；`apply_preferences` 不再合并品牌 |
| `src/ui/pages/analysis.py` | 表单重构（类别 → 品牌级联）、移除开关、AI 判定改读全局 |
| `src/ui/pages/settings.py` | 设置项增删、AI 总开关 |
| `src/ui/state.py` | 新增 `ai_enhanced_active()`；`current_mode()` 反映全局关闭状态 |
| `src/ui/pages/knowledge.py` | AI 就绪判定改读全局；新增「已在设置中关闭」的形态 |

**测试**：`tests/test_settings.py`（偏好字段增删）、`tests/test_app.py`（开关、表单控件、设置页断言）、`tests/test_acceptance.py`（如引用被删控件）

**文档**：`README.md`、`docs/requirements.md`、`docs/demo_script.md` 相关表述

**风险**

- 偏好文件里已存的 `brand_preferences`/`focus_areas` 键会被 pydantic `extra="ignore"` 静默忽略——不迁移、不报错，符合「设置只影响便利性」的定位。
- 分析页 AI 默认开启后，「调用外部服务前说明数据范围」的知情要求由**设置开关 + 页面常驻说明**共同承担，规格 delta 中明确。
