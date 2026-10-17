# 规格覆盖追溯表

把 `openspec/changes/archive/2026-10-12-add-zhigou-mvp/specs/` 下的
**99 条 Scenario** 逐条对应到测试函数或验证方式。

（这些规格已归档合并进 `openspec/specs/`，成为后续改动的依据。
**注意两份的数字不同**：归档快照是 39 条需求 / 99 条场景；
此后每个变更归档都会往规格里加内容，当前 `openspec/specs/` 已有
**12 份能力规格、78 条需求 / 296 条场景**。

**本表核对的是归档快照的 99 条**，后续变更新增的需求与场景**尚未纳入这张追溯表**。
它不是失效了，而是只覆盖到 MVP 那一次迭代——新变更的追溯在各变更自己的
`specs/` 与 `tasks.md` 里。

（商品数据集换成真实电子产品后，本表里由该变更改名的测试函数已就地换成现行名：
键盘品类移除使 `test_keyboard_scores_exclude_portability_with_reason` 变成
`test_headphone_scores_exclude_portability_with_reason`；「演示数据标识」相关的两条
换成 `test_data_boundary_notice_is_visible_on_home` 与 `test_markdown_keeps_the_data_disclaimer`。
场景名与统计仍以归档快照为准。）

**这份表是人工核对的，不是脚本生成的。** 我第一版写了个脚本拿中文 Scenario 名
去搜英文测试函数名，结果把几乎全部标成「缺口」——那是假报告，已经废弃。
下面的每一行都是实际看过测试之后填的。

图例：

- ✅ **自动** —— 有 pytest 断言守着
- 🔍 **实测** —— 靠浏览器 / 断网等手工实测覆盖，未固化为断言
- ⚠️ **弱覆盖** —— 只在提示词或代码层面约束，没有独立断言
- ❌ **缺口** —— 完全没有覆盖（本节末尾统一列出）

---

## product-catalog（5 需求 / 10 场景）

| Scenario | 覆盖 |
|---|---|
| 字段完整的商品被正常加载 | ✅ `test_all_products_are_complete` |
| 缺失核心参数的商品不导致崩溃 | ✅ `test_record_missing_specs_is_degraded_not_rejected` |
| 数据集满足规模要求 | ✅ `test_dataset_has_at_least_20_products` |
| 商品之间具有可区分差异 | ✅ `test_products_have_unique_ids_and_vary_within_category` |
| 商品卡片显示演示数据标识 | ✅ `test_product_card_carries_the_demo_data_source` |
| 报告与导出结果保留标注 | ✅ `test_markdown_keeps_the_data_disclaimer`、`test_csv_keeps_the_data_source` |
| 数据文件不存在 | ✅ `test_missing_file_raises_domain_error`、`test_missing_product_file_shows_a_hint_and_keeps_the_app_alive` |
| 数据文件内容非法 | ✅ `test_invalid_json_raises_domain_error`、`test_corrupt_product_file_shows_a_hint` |
| 数据文件为空列表 | ✅ `test_empty_product_list_raises_empty_catalog`、`test_empty_product_catalog_shows_a_hint` |
| 修改数据文件即刻生效 | ✅ `test_editing_the_file_changes_the_result` |

## demand-parsing（4 需求 / 10 场景）

| Scenario | 覆盖 |
|---|---|
| 完整需求被正确解析 | ✅ `test_full_example_is_parsed_into_structured_fields` |
| 部分信息缺失时保留空值 | ✅ `test_missing_fields_stay_empty_instead_of_being_guessed` |
| 未配置大模型时也能完成解析 | ✅ `test_parsing_makes_no_network_calls` + 断网实测 |
| 只追问缺失字段 | ✅ `test_follow_up_only_asks_about_the_missing_key_field` |
| 关键字段缺失时提出追问 | ✅ `test_follow_up_only_asks_about_the_missing_key_field` |
| 结构化取值覆盖自然语言取值 | ✅ `test_structured_value_overrides_natural_language` |
| 仅结构化输入也可运行 | ✅ `test_structured_only_input_is_usable` |
| 空输入被拒绝 | ✅ `test_empty_input_is_rejected`、`test_empty_input_is_rejected_with_a_chinese_hint` |
| 负数预算被拒绝 | ✅ `test_non_positive_budget_is_rejected`、`test_negative_budget_in_free_text_is_rejected` |
| 非数值预算被拒绝 | ✅ `test_unparseable_budget_is_rejected`、`test_malformed_budget_is_rejected_with_an_example` |

## recommendation-engine（7 需求 / 14 场景）

| Scenario | 覆盖 |
|---|---|
| 预算内商品被优先展示 | ✅ `test_budget_splits_candidates_into_within_and_over` |
| 超预算商品不会被隐藏成预算内 | ✅ `test_over_budget_products_are_never_labelled_within_budget` |
| 评分包含各维度得分 | ✅ `test_score_total_is_weighted_average_of_dimensions` |
| 评分命名不暗示市场口碑 | ✅ `test_score_is_never_presented_as_market_reputation` |
| 缺参数商品仍能得到评分 | ✅ `test_missing_specs_exclude_dimensions_instead_of_defaulting` |
| 类别权重差异生效 | ✅ `test_categories_use_different_dimensions`、`test_laptop_scores_include_portability`、`test_headphone_scores_exclude_portability_with_reason` |
| 权重集中可查 | ✅ `test_weight_table_sums_to_one`（权重集中在 `config.SCORING_WEIGHTS` 单一位置，该测试守住其合法性） |
| 高分商品排在低价商品之前 | ✅ `test_higher_need_match_outranks_cheaper_weak_item` |
| 排序结果随需求变化 | ✅ `test_changing_core_needs_changes_the_order` |
| 给出提高预算的建议 | ✅ `test_budget_below_cheapest_gives_price_specific_suggestion` |
| 给出放宽需求的建议 | ✅ `test_unknown_brand_gives_brand_relaxation`、`test_unsatisfiable_hard_constraint_gives_relaxation` |
| 加分扣分项与维度得分一致 | ✅ `test_bonus_and_penalty_track_dimension_ranks`、`test_bonus_and_penalty_are_deterministic_under_ties` |
| 推荐依据引用商品数据 | ✅ `test_reasons_trace_back_to_product_data` |
| 修改预算后结果更新 | ✅ `test_changing_budget_recomputes_candidates` |

## product-comparison（3 需求 / 7 场景）

| Scenario | 覆盖 |
|---|---|
| 三件商品比较表生成 | ✅ `test_three_products_produce_a_complete_table` |
| 比较数量不足时提示 | ✅ `test_fewer_than_three_products_is_rejected`、`test_comparison_with_too_few_products_shows_hint` |
| 选择数量上限被限制 | ✅ `test_more_than_the_cap_is_rejected` |
| 缺失字段被显式标注 | ✅ `test_missing_field_is_labelled_not_left_blank` |
| 差异维度被高亮 | ✅ `test_differing_values_are_flagged_for_highlighting`（标记层面）；视觉效果 🔍 浏览器实测 |
| 比较表显示预算匹配状态 | ✅ `test_budget_match_column_reflects_the_budget` |
| 未设定预算时的处理 | ✅ `test_unset_budget_is_labelled_unset_not_within_budget` |

## history-store（4 需求 / 11 场景）

| Scenario | 覆盖 |
|---|---|
| 分析完成后写入历史 | ✅ `test_analysis_is_saved_to_history`、`test_save_and_list` |
| 历史列表按时间倒序展示 | ✅ `test_list_is_newest_first` |
| 历史记录可再次打开 | ✅ `test_history_report_can_be_reopened` |
| 收藏商品后被持久化 | ✅ `test_favorites_persist_across_connections`、`test_favorite_round_trip` |
| 取消收藏 | ✅ `test_unfavorite_removes_it`、`test_remove_favorite` |
| 收藏的商品已从数据文件移除 | ✅ `test_favorite_of_a_missing_product_is_labelled` |
| 数据库损坏时仍可分析 | ✅ `test_corrupt_history_database_does_not_block_analysis` |
| 写入失败时给出提示 | ✅ `test_write_failure_keeps_the_result_on_screen` |
| 记录内容限于决策所需字段 | ✅ `test_stored_columns_contain_no_personal_information` |
| 外部调用前告知数据范围 | ✅ `test_enabling_ai_shows_the_data_sharing_notice` |
| 本地模式不发起外部请求 | 🔍 断网复跑（拦截 socket，网络调用 0 次） |

## decision-report（4 需求 / 10 场景）

| Scenario | 覆盖 |
|---|---|
| 报告包含全部必需小节 | ✅ `test_report_contains_every_required_section` |
| 待核实项基于真实缺口生成 | ✅ `test_verification_items_come_from_real_gaps`、`test_stale_dataset_is_flagged`、`test_incomplete_product_is_flagged_by_name` |
| 无推荐结果时报告说明原因 | ✅ `test_report_has_no_recommendations_section_when_nothing_matched`、`test_conclusion_says_nothing_when_there_is_nothing_at_all` |
| 导出 Markdown | ✅ `test_markdown_keeps_the_demo_data_disclaimer` + 🔍 浏览器真实下载 |
| 导出 CSV | ✅ `test_csv_has_one_row_per_product`、`test_csv_bytes_start_with_a_bom` |
| 导出失败时给出提示 | ✅ `test_export_error_carries_a_chinese_message`（导出不落盘，由浏览器负责写入与失败提示） |
| 历史报告还原原始结论 | ✅ `test_report_does_not_change_when_the_catalog_changes`、`test_get_analysis_restores_the_original_conclusions` |
| 历史报告标注生成时间 | ✅ `test_reopened_report_is_marked_with_its_generation_time` |
| 数据不足时明确说明 | ✅ `test_verification_items_come_from_real_gaps` |
| 不使用未提供的数据背书推荐 | ✅ `test_reasons_trace_back_to_product_data`、`test_overview_with_an_invented_price_is_dropped` |

## ai-enhancement（5 需求 / 14 场景）

| Scenario | 覆盖 |
|---|---|
| 无密钥时本地模式完整可用 | ✅ `test_without_a_key_the_app_runs_fully_locally` |
| 配置密钥后启用 AI 增强 | ✅ `test_ai_toggle_appears_when_configured` |
| 模式状态对用户可见 | ✅ `test_ai_toggle_is_hidden_when_not_configured` + 🔍 浏览器实测侧栏显示 |
| 密钥未配置时提前报错 | ✅ `test_unconfigured_service_raises_before_any_request`（断言**没有**发出请求） |
| 日志不泄露密钥 | ✅ `test_redact_removes_the_configured_key` + 🔍 日志文件全量扫描 |
| 界面不回显密钥 | ✅ `test_describe_never_leaks_the_key`、`test_error_body_never_leaks_the_key_into_the_message` |
| 网络超时触发降级 | ✅ `test_timeout_becomes_a_domain_error`、`test_ai_timeout_degrades_gracefully` |
| 返回内容非法触发降级 | ✅ `test_complete_json_raises_when_the_model_will_not_cooperate`、`test_unexpected_structure_is_rejected` |
| 鉴权失败给出明确原因 | ✅ `test_auth_failure_is_named_clearly` |
| 缺失参数时声明信息不足 | ⚠️ 仅在系统提示词里要求；**没有独立断言** |
| 输出被限制在传入数据范围内 | ✅ `test_explanation_with_a_wrong_price_is_dropped`、`test_explanation_for_an_unknown_product_is_dropped` |
| 模型不可用时结果仍可解释 | ✅ `test_explanation_failure_keeps_the_recommendations`、`test_ai_failure_degrades_to_local_rules` |
| 调用逻辑集中 | ⚠️ 结构性约束（`ai_service` 是唯一发起 HTTP 的模块），靠代码审查 |
| 可替换模型端点 | ✅ `test_endpoint_is_replaceable_without_code_changes` |

## web-ui（7 需求 / 23 场景）

| Scenario | 覆盖 |
|---|---|
| 五个页面均可打开 | ✅ `test_every_page_renders_without_exception` |
| 首页提供入口与说明 | ✅ `test_app_uses_the_expected_page_layout`、`test_quick_start_prefills_the_analysis_page` |
| 项目说明页披露数据限制 | ✅ `test_data_boundary_notice_is_visible_on_home` + 页面内容审查 |
| 结构化控件可用 | ✅ `test_ai_parse_is_used_when_enabled`（用到结构化控件路径） |
| 非法输入就地提示 | ✅ `test_invalid_budget_shows_a_chinese_error` |
| 商品卡片信息完整 | ✅ `test_product_card_carries_the_demo_data_source` |
| 评分构成可展开 | ✅ `test_score_display_name_is_shown_with_results` + 🔍 浏览器实测展开 |
| 比较表格清晰可读 | 🔍 浏览器实测 |
| 配色符合规范 | 🔍 浏览器实测（读侧栏计算样式）；样式令牌集中在 `theme.py` |
| 图标不使用 emoji 作为主要图标系统 | ✅ `test_every_icon_name_is_defined`（图标全部是内联 SVG） |
| 窄屏可读 | 🔍 浏览器实测（390px，无横向滚动、无文本溢出） |
| 自定义样式不依赖不稳定内部结构 | ✅ `test_sidebar_is_dark`（守住唯一一处 `data-testid` 依赖） |
| 各异常均给出中文提示 | ✅ `test_acceptance.py` 全组（16 条） |
| 不暴露堆栈 | ✅ `_assert_no_leak` 在每条验收测试里断言无 Traceback / 文件路径 / 库名 |
| 重复提交不产生重复记录 | ✅ `test_repeated_submission_creates_one_record` |
| 处理中给出状态反馈 | ⚠️ 用的是 `st.spinner`，AppTest 取不到；只断言了结果同步产出 |
| 偏好被持久化 | ✅ `test_preferences_are_applied_and_reported`、`test_round_trip` |
| 未设置偏好时不显示已应用提示 | ✅ `test_preference_notice_is_not_shown_when_nothing_was_applied` |
| 恢复默认 | ✅ `test_reset_preferences_restores_defaults` |
| 设置文件损坏不影响使用 | ✅ `test_corrupt_or_wrong_shape_falls_back_to_defaults` |
| 侧栏为深色并保持生效 | ✅ `test_sidebar_is_dark` + 🔍 浏览器读取计算样式确认 `rgb(15, 41, 66)` |
| 图标名写错会被发现 | ✅ `test_no_page_uses_an_undefined_icon` |

---

## 统计

| 覆盖方式 | 条数 |
|---|---|
| ✅ 有自动化断言 | 88 |
| 🔍 靠实测覆盖 | 8 |
| ⚠️ 弱覆盖 | 3 |
| ❌ 完全缺口 | 0 |
| **合计** | **99** |

## 弱覆盖与实测项说明

这三条**不是漏做，是当前测试手段够不着**，如实列出来：

1. **「缺失参数时声明信息不足」** —— 这条约束写在系统提示词里，
   模型的输出质量无法用单元测试断言。间接防线是
   `find_invented_prices`（编造价格会被丢弃），但那管的是另一件事。
   真实联调时观察到的行为是符合要求的。

2. **「处理中给出状态反馈」** —— `st.spinner` 在 Streamlit 的测试框架
   `AppTest` 里不产生可断言的元素。断言了「点击后结果同步产出」这个前提，
   视觉上的 spinner 靠浏览器实测。

3. **「调用逻辑集中」** —— 这是结构性约束，靠代码审查：
   只有 `src/ai_service.py` 发起 HTTP 请求。

八条 🔍 实测项（浏览器交互、窄屏、配色、断网、真实下载等）
在提交记录里都有当时的实测输出，但它们依赖真实浏览器环境，
没有固化成 CI 可跑的断言。
