# 部署说明

> **版本状态（2026-11-10，v2.18）**：当前部署方式是 **Vue 3 + FastAPI 单端口**（下面第 1 节）。
> legacy 部署方案压缩为第 2 节历史说明；旧版入口仍保留（CI 与测试依赖）。
> 迁移范围、页面覆盖矩阵、API 清单与已知限制见 [docs/VUE_MIGRATION.md](docs/VUE_MIGRATION.md)。

## 1. 当前版本：Vue + FastAPI 单端口（推荐）

一个 Uvicorn 进程同时提供 `/api/*` 接口与前端静态资源，绑定域名后即可直接打开网址。

```bash
pip install -r requirements-vue.txt   # Vue 版专用，不含 streamlit
cd frontend && npm install && npm run build && cd ..
python backend/run.py                 # 默认 127.0.0.1:8000
```

> `requirements-vue.txt` 与 `requirements.txt` 版本完全一致，只少了 `streamlit`。
> 后端已不再 import streamlit（数据集与知识索引缓存抽到了 `src/runtime_cache.py`），
> 所以只部署 Vue 版时不需要它。要跑 legacy 界面或完整测试套件，仍装全量
> `requirements.txt`。

云端要点：

1. **先构建再启动**：`frontend/dist/` 是构建产物、不入库；后端启动时检测该目录并自动托管。
   改动前端源码后必须重新 `npm run build` 并重启后端，否则仍指向旧产物。
   内存只有 2G 的机器建议**在本地构建**后上传 `dist/`，避免 `vue-tsc` 构建时 OOM。
2. **启动时自动初始化**：进程启动会幂等地导入商品种子、在账号表为空时创建初始管理员，
   因此新机器首次启动即可登录，**不再要求手动执行 `scripts/init.py`**（该脚本仍保留，
   可作为「只体检」或独立初始化手段）。初始化失败只记日志，不会阻断服务启动。
3. **管理员密码必须显式配置**：`ZHIGOU_ADMIN_PASSWORD` 未设置时会随机生成，
   且明文只出现在本次启动日志里 —— 用 systemd 部署时容易错过。请写进 `.env`。
   忘记密码时临时设置 `ZHIGOU_RESET_ADMIN_PASSWORD` 重启一次，成功后再删除并重启。
4. **绑定地址**：容器或服务器内设 `ZHIGOU_API_HOST=0.0.0.0`、`ZHIGOU_API_PORT=8000`，
   HTTPS 由平台或反向代理提供。默认值 `127.0.0.1` 只能本机访问。
5. **放行端口**：云服务器需在安全组 / 防火墙放行 `8000`（测试期）或 `80`、`443`（正式）。
   服务在本机 `curl` 正常、外部却连接超时，通常就是这一步没做。
6. **守护进程**：线上以 `/opt/zhigou` 为 WorkingDirectory、`zhigou.service` 托管 `backend/run.py` 并设 `Restart=always`，
   否则 SSH 断开或机器重启后站点就打不开了。
7. **持久化**：挂卷到 `storage/`，SQLite 只跑一个实例；重启后数据保留，但内存中的登录会话失效。当前发布流程：本地 `npm run build` → 上传 `frontend/dist` 到 `/opt/zhigou/frontend/dist` → `systemctl restart zhigou`；旧产物留 `.bak` 便于回滚。
8. **密钥**：`ZHIGOU_LLM_API_KEY` / `ZHIGOU_EMBEDDING_*` 等只放服务端环境变量，
   不会下发到浏览器。**本地 `.env` 不入库，部署时必须手动把这几项迁过去**——
   漏了的话 AI 问答与语义检索不可用（其余功能仍正常，很容易被误认为「功能没做」）。
   配置后用 `/api/admin/api-config` 返回的 `configured` 字段确认是否真的生效。
9. **上线前**：确认 `.env` 已关闭自助注册并使用强密码。登录失败限流（5 次锁 15 分钟）、
   会话 12 小时绝对过期与 30 分钟空闲超时**已经实现**，无需另行补做；仍未做的是
   CSRF 防护与生产级会话存储，见 `SECURITY.md`。

> 现有 `Dockerfile` / `docker-compose.yml` 仍是 **legacy Streamlit 版**（8501 端口，仅历史参考），
> 尚未改为多阶段构建 Vue 前端。用它部署 Vue 版之前请先按上述方式替换，
> 或直接 `python backend/run.py` 托管构建产物。

## 2. legacy 部署（历史归档）

当前部署只用第 1 节的单端口方式。以下均为历史参考，不再维护：

- 旧版入口：`streamlit run app.py`（8501 端口）；`Dockerfile` / `docker-compose.yml` 是 legacy Streamlit 镜像。
- 旧版 Streamlit Community Cloud 演示地址已停用；临时公网隧道、Railway / Render、VPS + 反向代理等方案均已废弃。
- 环境变量与管理员账号规则与当前版一致，见 `.env.example`、`SECURITY.md`；当前版密钥只放服务端 `.env`。
- `.github/workflows/ci.yml` 的 `docker` job 仍会构建 legacy 镜像并轮询 `/_stcore/health`（阻断门禁）；
  `app.py`、`src/ui/`、Streamlit 依赖、AppTest 因此成套保留，不要单独删除。
- 旧版仓库外源码快照 zip 已清理；git 分支 `backup/streamlit-v1` 与标签 `v1.0.0-streamlit` 仍可回退。
