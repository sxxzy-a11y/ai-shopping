> **关于这份清单的时间顺序**：本变更的代码写在 2026-10-16 00:40–00:57，
> 而提案与任务清单是 00:59 才建的——也就是说，**它是事后补写的记录**：
> 改动先落地，规格文档随后补上。清单里的勾是 2026-10-16 逐条对着代码核的，
> 不是当时边做边勾的。
>
> 核的时候发现三处文档确实没做（§4 的 4.3 / 4.4 / 4.5），已补齐；
> 另外 delta 里两处会导致归档出错的地方也一并修了（见文末「归档前的修正」）。

## 1. 检索精度（先做，可独立验证）

- [x] 1.1 `src/config.py`：新增 `KNOWLEDGE_RELATIVE_CUT`（初值 0.35）
- [x] 1.2 `src/config.py`：`KNOWLEDGE_MAX_RESULTS` 5 → 3
- [x] 1.3 `src/knowledge/search.py`：结果保留条件改为 `score >= max(min_score, top_score × 相对截断)`
- [x] 1.4 单测：相对截断——最高分与次高分的差距决定是否保留第二条
      （`test_relative_cut_drops_hits_an_order_of_magnitude_below_the_top`、
      `test_relative_cut_keeps_a_close_second_hit`）
- [x] 1.5 单测：条数上限为 3
      （`test_result_count_never_exceeds_the_configured_cap`、`test_limit_is_respected`）
- [x] 1.6 回归：固定查询集（正例排第一的文档类型不变、语料外反例仍返回空）
- [x] 1.7 用实际问题集复测截断效果，确认系数 0.35 不漏掉并列相关的第二篇（否则放宽）
- [x] 1.8 片段抽取按重合度取前几段（不再要求相邻），`EXCERPT_MAX_CHARS` 420 → 600
- [x] 1.9 单测：问「笔记本多重适合带出门」时片段必须包含重量分档数字
      （`test_excerpt_covers_the_key_numbers_of_the_matched_section`）
- [x] 1.10 品牌加权：`KNOWLEDGE_BRAND_BOOST`，品类约束（点名品类时不跨品类加权）
- [x] 1.11 单测：只问品牌有结果且只含该品牌商品；品牌 + 品类不跨品类；语料外品牌不误伤
      （`test_brand_only_question_hits_brand_products`、
      `test_brand_boost_respects_the_mentioned_category`、
      `test_brand_boost_does_not_rescue_off_corpus_queries`）

## 2. AI 问答页（改名 + 恒开 + 去片段区）

- [x] 2.1 `app.py` 导航项「知识问答」→「AI 问答」
- [x] 2.2 `src/ui/pages/knowledge.py` 页头改名，文案改为「一问一答」口径
- [x] 2.3 移除「启用 AI 增强」开关（该页恒走 AI）
- [x] 2.4 未配置密钥时的形态：提示需要配置（含环境变量名与重启步骤）+ 去「智能分析」的入口
- [x] 2.5 AI 调用失败时的形态：提示失败原因与重试建议，不展示半成品
- [x] 2.6 删除「找到的资料」区与来源引用（`_render_results` 只保留回答卡片）
- [x] 2.7 保留价格/预算类问题的引导（不走 AI 问答）
- [x] 2.8 保留语料外问题的说明（「知识库里没有相关资料」）
- [x] 2.9 作答提示词改为直接回答口径：禁止「资料/片段/没有覆盖」元话语，宽问题综合品牌/品类要点

## 3. 测试适配与新增

- [x] 3.1 `tests/test_app.py`：页面名改为「AI 问答」
- [x] 3.2 `tests/test_app.py`：断言不再出现「找到的资料」区与来源引用
- [x] 3.3 `tests/test_app.py`：断言该页不再有 AI 开关
- [x] 3.4 `tests/test_app.py`：未配置密钥时的提示断言
- [x] 3.5 `tests/test_app.py`：AI 调用失败时的提示断言（打桩，不联网）
- [x] 3.6 `tests/test_knowledge_search.py`：相对截断与条数上限的新断言

## 4. 文档同步

- [x] 4.1 `README.md`：页面清单、场景表、知识问答章节、检索参数表
- [x] 4.2 `docs/requirements.md`：FR 知识问答相关条目的形态描述
- [x] 4.3 `docs/architecture.md`：检索取舍（相对截断）说明
      —— **核对时发现没做，2026-10-16 补**：§8.3 扩成「三层加权与两道取舍」
      （补上品牌系数、绝对阈值 vs 相对截断 vs 条数上限的分工）
- [x] 4.4 `docs/demo_script.md`：演示话术由「展示原文」改为「展示回答」
      —— **核对时发现没做，2026-10-16 补**。这一处不能拖：脚本原文写的是
      「系统展示：检索到的资料原文片段 + 来源」，而界面早就没有片段区与来源了，
      照着演示会当场翻车
- [x] 4.5 `docs/testing.md`：检索回归基线的口径
      —— **核对时发现没做，2026-10-16 补**：正例数由过期的「8 条」改为实测的
      **9 条**，表格里的例子换成固定查询集里真实在用的（原来的「主动降噪」
      已随耳机品类一起移除、「索尼 WH-1000XM5」已不在商品库），并补上
      「条数上限 + 相对截断」这条口径

## 5. 验收

- [x] 5.1 `pytest` 全绿，记录实际条数 —— 实测 **959 条**（2026-10-16）
- [x] 5.2 浏览器实测：改名生效、无开关、只展示回答、无片段区
      —— 由无头运行真实应用的用例覆盖（`test_app` 的问答小节）；
      **浏览器目视未单独记录**
- [x] 5.3 未配置密钥路径实测：提示可行动，不是错误堆栈
      （`test_ai_qa_without_key_explains_how_to_configure`）
- [x] 5.4 价格类问题仍被引导、语料外问题仍明确说明
      （`test_ai_qa_refuses_price_questions`、`test_ai_qa_says_so_when_nothing_is_found`）
- [x] 5.5 `scripts/evaluate.py` 评测集不回归 —— 实测 **41/41 通过**
- [x] 5.6 `openspec validate --all` 通过

---

## 归档前的修正（2026-10-16）

这份 delta 有两处会让归档**做错事**，归档前修掉了：

1. **`REMOVED Requirements` 段用的是 `### Reason:` 作标题**，而 CLI 的
   `parseRemovedNames()` 只认 `### Requirement: <名字>`（正则
   `/^###\s*Requirement:\s*(.+)\s*$/i`）。照原样归档**一条都删不掉**：
   「两种回答模式」与「引用来源展示」会原样留在正式规格里，
   与新加的「单一 AI 回答模式」直接打架。已改成标准标题 + `**Reason**`。
2. **`MODIFIED 页面构成` 用的是旧文本**（只列七个页面、五个场景），
   而正式规格在这份提案之后已经被别的变更改过——多了登录页、注册页与三个
   管理员页及其场景。照原样归档会把那些**全部覆盖掉**。已按线上现文本重建，
   只做「知识问答页 → AI 问答页」这一处改名，其余一字不动。
