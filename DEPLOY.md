# 部署上线指南

## 一、整体架构

这个项目需要两部分分开部署：

- 前端（Vue 3 + Vite）：部署到 Vercel，访客通过网址直接访问。
- 后端（FastAPI + DeepSeek + 高德）：Python 服务，部署到 Railway / Render / Fly.io，或自己的 Docker 服务器。

Vercel 适合托管静态前端，不适合运行 FastAPI 长连接和 SSE 流式接口，所以后端必须单独托管。

## 二、推送代码到 GitHub

1. 在 GitHub 新建一个空仓库，例如 `ai-travel-planner`，不要勾选 README 和 .gitignore。
2. 本地项目目录执行：

```bash
git init
git add .
git commit -m "feat: travel planner production ready"
git branch -M main
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

3. 推送前确认 `.env`、`*.db`、`node_modules/`、`venv/`、`dist/`、`test-results/` 都不会被提交，项目根目录的 `.gitignore` 已配置好。

## 三、前端部署到 Vercel

1. 打开 https://vercel.com，使用 GitHub 账号登录。
2. 点击 `Add New > Project`，选择刚推送的仓库。
3. 项目配置：
   - Framework Preset：`Vite`
   - Root Directory：如果仓库根目录就是前端代码，保持 `/`；如果仓库是外层目录，则填 `frontend`
   - Build Command：`npm run build`
   - Output Directory：`dist`
4. 添加环境变量：
   - `VITE_AMAP_JS_KEY`：高德 JS API Key
   - `VITE_AMAP_SECURITY_CODE`：高德 JS API 安全密钥
   - `VITE_API_BASE`：后端地址，例如 `https://your-backend.example.com`
5. 点击 `Deploy`，Vercel 会自动生成 `*.vercel.app` 网址并签发 HTTPS。

## 四、后端部署

推荐二选一：

### 方式 A：PaaS 平台

在 Railway / Render / Fly.io 中新建服务，选择 `backend/` 目录或直接用 `backend/Dockerfile` 构建：

- 启动命令：`python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 环境变量：
  - `DEEPSEEK_API_KEY`
  - `DEEPSEEK_BASE_URL`（可选，默认 `https://api.deepseek.com`）
  - `DEEPSEEK_MODEL`（可选，默认 `deepseek-chat`）
  - `AMAP_WEB_KEY`
  - `HISTORY_DB_PATH`：SQLite 持久化路径，例如 `/data/trip_history.db`
  - `AMAP_CACHE_DB_PATH`：例如 `/data/amap_cache.db`
- 后端需要挂载持久化磁盘，否则数据库会在重启后丢失。

### 方式 B：自己的服务器

```bash
cp .env.example .env
```

编辑 `.env` 填入真实密钥后执行：

```bash
docker compose up -d --build
```

访问 `http://服务器IP`，健康检查地址为 `http://服务器IP/health`。

## 五、域名与 HTTPS

- Vercel 默认提供 `*.vercel.app` 域名，别人可以直接通过该网址访问。
- 绑定自己的域名：在 Vercel 项目 `Settings > Domains` 添加域名，并按提示配置 DNS 的 CNAME 或 A 记录，Vercel 会自动签发 HTTPS 证书。
- 你已有的国内域名**没有备案也可以绑定 Vercel**，因为 Vercel 服务器在海外，不需要 ICP 备案。
- 只有把服务放在中国大陆服务器或使用中国大陆 CDN 时，才必须完成 ICP 备案。

## 六、上线后检查

- 打开网站，确认高德地图能正常加载（JS Key 需要启用 `Web端(JS API)`，并配置安全密钥）。
- 生成一次完整行程，确认 SSE 进度、天气、路线、记账、历史记录都正常。
- 打开浏览器开发者工具，确认没有 CORS 跨域报错。
- 检查后端日志，确认 DeepSeek 和高德请求都成功。