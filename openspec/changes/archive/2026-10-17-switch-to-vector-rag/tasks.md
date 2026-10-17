## 1. Embedding 客户端

- [ ] 1.1 `src/config.py`：新增 Embedding 环境变量（KEY/BASE_URL/MODEL/DIM）与默认值；相似度阈值、条数上限
- [ ] 1.2 `src/knowledge/embeddings.py`：`EmbeddingService`（httpx 直连 `/embeddings`，批量 ≤10、超时、错误翻译、密钥脱敏、`configured` 判定）
- [ ] 1.3 单测：打桩返回、批量拆分、空输入、超时/鉴权/响应非法、未配置
- [ ] 1.4 `.env.example` 增加 Embedding 配置样例（含「DeepSeek 无 embedding 接口」的说明）
- [ ] 1.5 `requirements.txt` 显式登记 numpy（pandas 已带）

## 2. 切片与向量存储

- [ ] 2.1 `src/knowledge/chunking.py`：标题优先、超长按段落切、500 字上限、标题前缀、稳定 slice_id
- [ ] 2.2 单测：标题分段、超长切分、上限、ID 稳定
- [ ] 2.3 `src/knowledge/vector_store.py`：建表、增量写入（content_hash+model+dim）、删除陈旧切片、统计、切换模型后过期判定
- [ ] 2.4 单测：增量跳过未变化、内容变化重建、模型/维度变化过期、删除陈旧、统计
- [ ] 2.5 余弦检索：numpy 矩阵计算、阈值 + 相对截断 + 条数上限、按当前模型过滤
- [ ] 2.6 单测：排序正确、阈值生效、相对截断、模型过滤

## 3. 检索调度与问答接入

- [ ] 3.1 `src/knowledge/retrieval.py`：`retrieve()` 向量优先 / BM25 回退，返回 `(passages, mode)` 或等价结构
- [ ] 3.2 单测：向量可用走向量、未配置走关键词、向量调用失败回退并带降级说明
- [ ] 3.3 `src/ui/state.py`：暴露统一检索入口与向量库访问；缓存策略与语料变更失效
- [ ] 3.4 `src/ui/pages/knowledge.py`：改用统一入口，界面标注「语义检索 / 关键词检索（回退）」
- [ ] 3.5 Agent 的 `search_knowledge` 工具改走统一入口（保持返回结构不变）

## 4. 管理页「知识库管理」（仅管理员）

- [ ] 4.1 `src/ui/pages/knowledge_admin.py`：概览（文档/切片/已向量化/模型/维度）
- [ ] 4.2 生成全部向量：显示待生成数量、进度、失败明细；成功后统计刷新
- [ ] 4.3 切片表：标题/小节/状态（可用/过期/未生成）/维度/更新时间，分页或截断并说明
- [ ] 4.4 检索调试台：输入问题 → 命中切片、分数、来源；无结果时明确说明
- [ ] 4.5 `app.py` 导航新增「知识库管理」（admin_only）
- [ ] 4.6 单测：管理员可见、普通用户不可见、页面渲染、调试检索

## 5. 文档与规格

- [ ] 5.1 `README.md`：知识库章节改为语义检索、环境变量、管理页说明、已知限制更新
- [ ] 5.2 `docs/architecture.md`：检索层架构（向量库、调度、回退）
- [ ] 5.3 `docs/requirements.md` / `docs/testing.md` / `docs/demo_script.md`
- [ ] 5.4 `openspec/project.md`：约束修订（本变更已完成）
- [ ] 5.5 归档时合并 delta 进 `openspec/specs/`

## 6. 验收

- [ ] 6.1 `pytest` 全绿
- [ ] 6.2 未配置 Embedding 时：问答与 Agent 检索仍可用（关键词回退），界面标注
- [ ] 6.3 配置 Embedding 后：管理页可生成向量、调试检索出分
- [ ] 6.4 换模型（模拟）后：旧切片显示过期、检索不使用、重建后恢复
- [ ] 6.5 断网/服务失败：问答回退关键词并提示，不崩溃
- [ ] 6.6 `openspec validate --all` 通过
