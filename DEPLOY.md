# 部署说明

> **版本状态（2026-11-07）**：当前推荐部署方式是 **Vue 3 + FastAPI 单端口**（下面第 1 节）。
> 原 Streamlit Cloud 部署完整保留为 legacy 方案（第 2 节及之后），用于回退与历史参考。
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
6. **守护进程**：用 systemd 托管 `backend/run.py` 并设 `Restart=always`，
   否则 SSH 断开或机器重启后站点就打不开了。
7. **持久化**：挂卷到 `storage/`，SQLite 只跑一个实例；重启后数据保留，但内存中的登录会话失效。
8. **密钥**：`ZHIGOU_LLM_API_KEY` / `ZHIGOU_EMBEDDING_*` 等只放服务端环境变量，
   不会下发到浏览器。**本地 `.env` 不入库，部署时必须手动把这几项迁过去**——
   漏了的话 AI 问答与语义检索不可用（其余功能仍正常，很容易被误认为「功能没做」）。
   配置后用 `/api/admin/api-config` 返回的 `configured` 字段确认是否真的生效。
9. **上线前**：补登录限流与会话空闲超时（见 `SECURITY.md`），否则不适合长期公网开放。

> 现有 `Dockerfile` / `docker-compose.yml` 仍是 **legacy Streamlit 版**（8501 端口），
> 尚未改为多阶段构建 Vue 前端。用它部署 Vue 版之前请先按上述方式替换，
> 或直接 `python backend/run.py` 托管构建产物。

## 2. 旧版演示部署（Streamlit Cloud / legacy）

- 地址：<https://ai-shopping-10.streamlit.app/>
- 平台：Streamlit Community Cloud
- 代码仓库：<https://github.com/sxxzy-a11y/ai-shopping>

Cloud 的文件系统是临时的。应用休眠或重新部署后，SQLite 里的账号、历史和收藏可能重置，商品会从 `data/products.json` 重新导入。比赛演示可以接受，长期使用不合适。

### 更新代码

```bash
git add .
git commit -m "your message"
git push origin main
```

Streamlit Cloud 会自动拉取并重新部署。如果页面还是旧版本，在应用的 **Manage app → Reboot app** 手动重启。

### Secrets

在 Streamlit Cloud 的 **App → Settings → Secrets** 中配置，格式为 TOML：

```toml
ZHIGOU_ADMIN_USERNAME = "admin"
ZHIGOU_ADMIN_PASSWORD = "一个强密码"
ZHIGOU_RESET_ADMIN_PASSWORD = "仅在需要重置管理员时临时填写"
ZHIGOU_ALLOW_REGISTRATION = "true"
ZHIGOU_LLM_API_KEY = "你的模型密钥"
ZHIGOU_LLM_BASE_URL = "https://api.deepseek.com/v1"
ZHIGOU_LLM_MODEL = "deepseek-flash"
ZHIGOU_EMBEDDING_API_KEY = "可选的向量检索密钥"
```

说明：

- `ZHIGOU_ADMIN_PASSWORD` 只在账号表为空、首次创建管理员时生效；已有管理员不会被它修改。
- 忘记管理员密码时，临时设置 `ZHIGOU_RESET_ADMIN_PASSWORD` 并重启；启动时会覆盖已有管理员密码。登录成功后删除这个变量，再重启一次。
- `ZHIGOU_LLM_API_KEY` 留空时，智能分析、商品比较、历史记录仍可用，AI 问答不可用。
- `ZHIGOU_EMBEDDING_API_KEY` 留空时，知识检索使用 BM25；配置后优先使用向量检索。
- Secrets 不要提交到仓库，也不要发在聊天或截图里。

### 公开演示的安全边界

- 当前账号体系是演示级：没有登录限流；会话 12 小时绝对过期，但没有空闲超时；
- 默认开放注册，任何访问者都能创建普通用户；
- 不要输入真实个人信息、真实密码或其他敏感数据；
- 公开演示只用于比赛和体验，不是生产服务。

如果要长期公开使用，至少需要加登录限流、会话管理、CSRF 防护，并在应用前加一层访问控制。

## 3. Docker + Railway / Render（legacy 版）

适合需要保留数据的长期演示。

1. 使用仓库里的 `Dockerfile` 构建；
2. 挂载持久卷到 `/app/storage`；
3. 只跑一个实例，SQLite 不适合多副本并发写；
4. 在平台环境变量面板配置与 Secrets 相同的变量；
5. 平台提供 HTTPS 域名。

本地自测（需要 Docker Desktop）：

```bash
docker compose up -d --build
```

打开 <http://localhost:8501>。

当前开发机没有安装 Docker，Dockerfile 做过静态检查，但没有在本机实际构建。作为补充，`.github/workflows/ci.yml` 里的 `docker` job 会在 ubuntu runner 上执行 `docker build`、启动容器并轮询 `/_stcore/health`；首次 CI 运行结果确认通过后，把该 job 的 `continue-on-error` 去掉即可转为阻断门禁。首次在服务器上部署时，建议先跑一次完整分析、比较和历史记录，再对外演示。

## 4. VPS + Docker + 反向代理（legacy 版）

1. 把仓库放到服务器，准备 `.env`，不要提交；
2. 启动：

   ```bash
   docker compose up -d --build
   ```

3. 用 Caddy 或 Nginx 反向代理 `127.0.0.1:8501`，例如 Caddy：

   ```caddyfile
   app.example.com {
       reverse_proxy 127.0.0.1:8501
   }
   ```

4. 持久化目录是 `./storage`，定期备份；
5. 只跑一个实例。

## 5. 本地运行（legacy 版）

```bash
pip install -r requirements.txt
streamlit run app.py
```

打开 <http://localhost:8501>。不配置模型密钥也能使用核心分析功能。

### 管理员账号

首次启动且账号表为空时，系统会创建初始管理员：

- 账号和密码取自 `ZHIGOU_ADMIN_USERNAME` / `ZHIGOU_ADMIN_PASSWORD`；
- 没有配置时生成随机密码，只在启动终端打印一次；
- 密码太短或用户名不合规时，系统会换成随机密码或默认用户名，不会静默放行。

如果账号已经存在，修改环境变量不会改旧密码。需要重置时使用上面的 `ZHIGOU_RESET_ADMIN_PASSWORD`。

## 6. 临时公网链接（legacy 版）

如果只是当天给朋友看，可以用 Cloudflare 隧道：

```bash
cloudflared tunnel --url http://localhost:8501
```

电脑关机或进程停止后链接失效，每次重启地址会变化。它不适合比赛正式演示，也不适合长期使用。

## 7. 上线前检查

- [ ] 管理员密码已设置，不使用默认密码；
- [ ] 模型密钥和 Embedding 密钥只放在 Secrets 或环境变量；
- [ ] 关闭不需要的自助注册；
- [ ] 演示数据已确认，价格和参数口径能在界面上看到；
- [ ] 只跑一个实例；
- [ ] `storage/` 有备份，或明确接受 Cloud 临时存储会重置；
- [ ] 演示前跑过一遍三条示例输入，确认分数和排名没有异常；
- [ ] 检查日志里没有密钥或用户输入全文。
