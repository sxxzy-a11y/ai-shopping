# 部署说明

项目是 Streamlit + SQLite。公网部署需要解决三件事：服务监听、HTTPS 访问、数据持久化。

## 当前演示部署

- 地址：<https://ai-shopping-muofh8jcwgc3weydpvmagc.streamlit.app/>
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

- 当前账号体系是演示级：没有登录限流、没有会话过期；
- 默认开放注册，任何访问者都能创建普通用户；
- 不要输入真实个人信息、真实密码或其他敏感数据；
- 公开演示只用于比赛和体验，不是生产服务。

如果要长期公开使用，至少需要加登录限流、会话管理、CSRF 防护，并在应用前加一层访问控制。

## Docker + Railway / Render

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

当前开发机没有安装 Docker，Dockerfile 做过静态检查，但没有在本机实际构建。首次在服务器上部署时，建议先跑一次完整分析、比较和历史记录，再对外演示。

## VPS + Docker + 反向代理

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

## 本地运行

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

## 临时公网链接

如果只是当天给朋友看，可以用 Cloudflare 隧道：

```bash
cloudflared tunnel --url http://localhost:8501
```

电脑关机或进程停止后链接失效，每次重启地址会变化。它不适合比赛正式演示，也不适合长期使用。

## 上线前检查

- [ ] 管理员密码已设置，不使用默认密码；
- [ ] 模型密钥和 Embedding 密钥只放在 Secrets 或环境变量；
- [ ] 关闭不需要的自助注册；
- [ ] 演示数据已确认，价格和参数口径能在界面上看到；
- [ ] 只跑一个实例；
- [ ] `storage/` 有备份，或明确接受 Cloud 临时存储会重置；
- [ ] 演示前跑过一遍三条示例输入，确认分数和排名没有异常；
- [ ] 检查日志里没有密钥或用户输入全文。
