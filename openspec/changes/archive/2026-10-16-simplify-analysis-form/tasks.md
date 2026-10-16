> **关于这份清单的时间顺序**：与 `refine-ai-qa` 一样，这是**事后补写的记录**——
> 代码先落地，提案 2026-10-16 01:16 才建。清单里的勾是 2026-10-16 逐条对着
> 代码核的。
>
> 核对时补了三处：`current_mode()` 三态与品牌级联的界面用例、
> 「页面上不存在『主要用途』控件」的断言。另外 delta 里 `MODIFIED 个人设置页`
> 丢了四个正式规格里的场景（含「偏好只补空缺」这条核心不变量），
> 也已补回并同步到「偏好按账号存」的现状——见文末「归档前的修正」。

## 1. 设置层（先做，其余都依赖它）

- [x] 1.1 `src/settings.py`：`UserPreferences` 移除 `brand_preferences` / `focus_areas`，新增 `ai_enhanced: bool = True`
- [x] 1.2 `FOCUS_OPTIONS` 常量删除；`effective_core_needs()` 只按价格取向折算
- [x] 1.3 `apply_preferences()` 不再合并品牌偏好
- [x] 1.4 单测适配：偏好字段、`effective_core_needs`、`apply_preferences`

## 2. 全局 AI 状态

- [x] 2.1 `src/ui/state.py` 新增 `ai_enhanced_active()`（设置开关 + 密钥配置）
- [x] 2.2 `current_mode()` 三态：本地演示模式 / 本地模式（AI 增强已关闭）/ AI 增强模式
- [x] 2.3 单测：三种状态各自返回正确的模式名
      （`test_mode_label_covers_all_three_states`，2026-10-16 补。
      注意这一条**必须走界面**：`current_mode()` 读的是当前登录用户的偏好，
      裸调时没有会话，取到的是默认值——写这条用例时第一版就栽在这儿）

## 3. 设置页

- [x] 3.1 移除「品牌偏好」「长期关注项」两个区块与对应控件键
- [x] 3.2 「AI 设置」区新增「AI 增强模式」开关（默认开，help 写明数据范围）
- [x] 3.3 「偏好会怎么影响分析」列表更新
- [x] 3.4 页面 docstring 与「AI 设置」区文案更新
- [x] 3.5 单测适配：设置页保存/恢复的字段断言

## 4. 智能分析页

- [x] 4.1 移除「启用 AI 增强」开关控件
- [x] 4.2 AI 生效时展示当前模型与数据说明（常驻，不需要确认动作）
- [x] 4.3 表单：移除「主要用途」「比较看重」「品牌偏好（多选）」
- [x] 4.4 品牌选择：选定类别后出现单选下拉（「不限品牌」+ 该类别品牌），未选类别不渲染
- [x] 4.5 空需求判断、`_input_signature`、`_run_analysis` 同步精简
- [x] 4.6 解析引擎提示（`zg_parse_engine`）改读 `state.ai_enhanced_active()`
- [x] 4.7 单测适配：开关断言移除、品牌级联断言、表单精简断言
      —— 2026-10-16 补：`test_brand_control_only_appears_after_a_category_is_chosen`、
      `test_brand_options_follow_the_category_and_reset_on_switch`、
      `test_the_analysis_form_has_no_usage_or_priority_controls`

## 5. AI 问答页接入全局开关

- [x] 5.1 `_ai_ready()` 改读 `state.ai_enhanced_active()`
- [x] 5.2 全局关闭时的形态：提示「AI 增强已在个人设置中关闭」
- [x] 5.3 单测：全局关闭时该页的提示断言
      （`test_ai_qa_respects_the_global_switch_being_off`，2026-10-16 补。
      顺带断言它**不是**「需要配置模型密钥」——两种原因混成一句，用户会去错地方）

## 6. 文档与验收

- [x] 6.1 `README.md`：表单描述、设置项描述、模式说明
      （核对：README 与 docs 里已无「主要用途」「比较看重」；
      剩下的「品牌偏好」字样都是**需求解析识别品牌**的意思，不是被移除的设置项）
- [x] 6.2 `docs/requirements.md` / `docs/demo_script.md`：表单与设置口径
- [x] 6.3 `pytest` 全绿 —— 实测 **959 条**（2026-10-16）
- [x] 6.4 浏览器实测：级联品牌、无开关、AI 恒开、设置开关生效
      —— 由无头运行真实应用的用例覆盖；**浏览器目视未单独记录**
- [x] 6.5 `openspec validate --all` 通过

---

## 归档前的修正（2026-10-16）

`MODIFIED 个人设置页` 原稿丢了正式规格里的四个场景，照原样归档会**删掉它们**：

| 丢掉的场景 | 为什么不能丢 |
|---|---|
| 偏好只补空缺 | **核心不变量**：用户在分析页手填的内容必须优先于设置里的偏好。这条代码里一直在守，规格里丢了就再没有依据 |
| 恢复默认 | 功能在（设置页有「恢复默认」按钮） |
| 未设置偏好时不显示已应用提示 | 功能在（分析页据 `zg_prefs_applied` 决定要不要提示） |
| 设置文件损坏不影响使用 | 概念已变：偏好从全局 JSON 文件改成了**按账号存库**（`add-login-and-user-roles`），已改写成「偏好数据不可读时不影响使用」 |

同时把「偏好持久化到本机」改成「**按账号**持久化到本机数据库」，并补了一条
「偏好只对自己生效」的场景——这两点是 `add-login-and-user-roles` 落地后的现状，
原稿写于它之前。
