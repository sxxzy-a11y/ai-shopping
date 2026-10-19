# 部署到公网

这个项目是 Streamlit + SQLite，公网部署要同时解决三件事：

1. 让服务监听 `0.0.0.0:8501`（Dockerfile 已处理）；
2. 提供一个 HTTPS 地址；
3. 给 `storage/` 一个持久磁盘，否则账号、历史、收藏、商品库会随重启消失。

## 最快：Streamlit Community Cloud

适合演示。缺点：**文件系统是临时的**，应用休眠/重新部署后，SQLite 里的账号、历史、收藏会重置；商品会从 `data/products.json` 重新种子导入。

1. 把当前仓库推到 GitHub（当前项目还没有 remote）：
   ```bash
   git remote add origin https://github.com/<你的账号>/<仓库名>.git
   git push -u origin main
   ```
2. 打开 <https://share.streamlit.io>，用 GitHub 登录，New app：
   - Repository：刚推送的仓库
   - Branch：`main`
   - Main file path：`app.py`
   - Python：3.12
3. 在 App → Settings → Secrets 里填写：
   ```toml
   ZHIGOU_ADMIN_USERNAME = "admin"
   ZHIGOU_ADMIN_PASSWORD = "换成一个强密码"
   # 演示期允许朋友注册；稳定后改成 "false" 关闭注册
   ZHIGOU_ALLOW_REGISTRATION = "true"
   ZHIGOU_LLM_API_KEY = "你的模型密钥"
   ZHIGOU_EMBEDDING_API_KEY = "你的向量密钥"
   ```
   应用启动时会把这些 Secrets 桥接成环境变量（`config.adopt_streamlit_secrets()`）。
4. Deploy，得到 `https://<app>.streamlit.app`。

## 推荐：Railway / Render（Docker + 持久卷）

适合长期使用，SQLite 数据能保留。

- 用仓库里的 `Dockerfile` 构建。
- **必须挂载一个持久卷到 `/app/storage`**。
- 只跑 **1 个实例**（SQLite 不适合多副本并发写）。
- 在平台的环境变量面板填写与上面相同的变量；演示期可保留 `ZHIGOU_ALLOW_REGISTRATION=true`，稳定后改 `false`。
- 生成公网域名，平台会自动提供 HTTPS。

本地自测（需要 Docker Desktop）：
```bash
docker compose up -d --build
```
打开 <http://localhost:8501>。

> 当前开发机没有安装 Docker，所以 Dockerfile 只做了静态检查，没有在本机实际构建过。

## 最稳：自己的 VPS + 域名

1. 把仓库放到服务器，准备 `.env`（不要提交）。
2. 启动：
   ```bash
   docker compose up -d --build
   ```
3. 用 Caddy/Nginx 反代 `127.0.0.1:8501`，例如 Caddy：
   ```caddyfile
   app.example.com {
       reverse_proxy 127.0.0.1:8501
   }
   ```
4. 持久化目录是 `./storage`；定期备份。

## 临时公网链接（不推荐长期使用）

如果只是今天给朋友看，可以在本机开一个 Cloudflare 隧道：

```bash
cloudflared tunnel --url http://localhost:8501
```

它会输出一个 `https://xxx.trycloudflare.com` 地址。电脑关机/进程停止后失效，每次重启地址会变。

## 上线前必须做

- **改掉 `admin / 12345678`**：在首次启动前设置 `ZHIGOU_ADMIN_PASSWORD` 为强密码。账号表已存在后，改环境变量不会改旧密码，需要登录后在个人设置里修改。
- **管理自助注册**：演示期可以保留 `ZHIGOU_ALLOW_REGISTRATION=true`，让朋友注册；稳定后改成 `false`，只保留已有账号。注意：关闭后管理员页面**不能新建账号**，只能改角色/重置密码；要做邀请制，先让对方注册，再关闭注册。
- **轮换密钥**：不要把 `.env` 提交或打进镜像；平台 Secret 面板填写，定期轮换。
- **限制 AI 花费**：给模型服务设置额度上限；不需要 AI 时可关闭「AI 增强模式」。
- **只跑一个实例**：SQLite 不能多副本同时写。
- **备份 `storage/`**：账号、历史、收藏、商品库都在这里。
- **如需仅限受邀用户**：在应用前再加一层 Cloudflare Access / 反向代理 Basic Auth；应用内登录只是应用层鉴权。

## 当前状态

服务已经监听 `0.0.0.0:8501`，同一 Wi‑Fi 可尝试：

```text
http://10.214.199.41:8501
```

如果同网段打不开，需要在 Windows 防火墙放行 TCP 8501。
