## 1. 配置层

- [ ] 1.1 `src/api_config.py`：路径（`ZHIGOU_API_CONFIG_PATH`，默认 `storage/api_config.json`）、读写、白名单、空值跳过、原子写、脱敏、容错
- [ ] 1.2 `src/config.py`：`llm_*` / `embedding_*` getter 改为「文件 > 环境变量 > 默认」
- [ ] 1.3 单测：覆盖优先级、空值不覆盖、损坏文件回退、清除覆盖、脱敏
- [ ] 1.4 `tests/conftest.py`：隔离配置路径，保证测试永远不读真实密钥
- [ ] 1.5 `.gitignore`：忽略 `storage/api_config.json`

## 2. 服务重载

- [ ] 2.1 `src/ai_service.py`：新增 `reset_service()`（与 embeddings 对称）
- [ ] 2.2 单测：重置后 `get_service()` 使用新配置

## 3. 项目说明页「API 配置」

- [ ] 3.1 状态区：对话模型（DeepSeek）与向量化（百炼）的当前端点/模型/维度/密钥脱敏
- [ ] 3.2 管理员编辑区：端点、模型、密钥（密码框，留空不改）、维度；保存并立即生效
- [ ] 3.3 「测试连接」：对话探测 + 向量测试（校验维度）
- [ ] 3.4 「恢复为环境变量配置」：删除覆盖文件并重置单例
- [ ] 3.5 普通用户：只读状态与「管理员可修改」说明
- [ ] 3.6 单测：管理员/普通用户可见性、保存生效、密钥不回显

## 4. 文档与验收

- [ ] 4.1 `.env.example` / `README.md`：配置分层说明与界面修改方式
- [ ] 4.2 `pytest` 全绿；`openspec validate --all` 通过
- [ ] 4.3 浏览器实测：修改模型名保存 → 状态刷新；密钥不回显
- [ ] 4.4 归档合并 delta
