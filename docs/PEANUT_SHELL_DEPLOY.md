# 贝锐花生壳临时部署指南

> 用途：Railway 等云后端不可用时，用花生壳把本机运行的项目临时映射到公网。
> 定位：面试演示 / 临时访问，不是生产部署方案。

---

## 1. 推荐架构

推荐只映射前端开发服务器，不用改 Vercel：

```text
面试官 / 外部访问
        ↓
花生壳公网地址
        ↓
本机 Vite 5173（前端 + /api 代理）
        ↓
本机 FastAPI 8000（后端 + 本地 SQLite）
```

优点：

- 只映射一个端口，页面和 API 同源，不会有跨域和 HTTPS/HTTP 混合内容问题。
- 不需要修改 Vercel 的 `VITE_API_BASE`，也不依赖 Vercel 配置权限。
- 本地 SQLite 直接使用，历史行程、用户记忆和聊天会话都能继续用。

---

## 2. 前置条件

1. 安装贝锐花生壳客户端并登录：`https://hsk.oray.com/`
2. 完成实名认证；部分映射类型有带宽和流量限制。
3. 保持电脑开机、联网，不要进入睡眠模式。
4. 保持后端、前端和花生壳三个程序同时运行。

---

## 3. 启动本地服务

### 3.1 后端

后端需要 DeepSeek 和高德环境变量。可以用原来的 Railway 变量启动，也可以自己创建 `backend/.env`（该文件已被 `.gitignore` 忽略）。

在项目根目录执行：

```powershell
cd "C:\Users\26566\Documents\New project\ai-travel-planner"

$vars = railway variables --json | ConvertFrom-Json
$env:DEEPSEEK_API_KEY = $vars.DEEPSEEK_API_KEY
$env:DEEPSEEK_BASE_URL = $vars.DEEPSEEK_BASE_URL
$env:DEEPSEEK_MODEL = $vars.DEEPSEEK_MODEL
$env:AMAP_WEB_KEY = $vars.AMAP_WEB_KEY
$env:HISTORY_DB_PATH = "C:\Users\26566\Documents\New project\ai-travel-planner\trip_history.db"
$env:AMAP_CACHE_DB_PATH = "C:\Users\26566\Documents\New project\ai-travel-planner\amap_cache.db"

cd backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

看到 `Uvicorn running on http://127.0.0.1:8000` 表示成功。

### 3.2 前端

另开一个 PowerShell：

```powershell
cd "C:\Users\26566\Documents\New project\ai-travel-planner\frontend"
npm run dev -- --host 127.0.0.1 --port 5173
```

看到 `Local: http://127.0.0.1:5173/` 表示成功。

### 3.3 本地验证

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:5173/api/chat/sessions
```

预期：

- `/health` 返回 `{"status":"ok"}`
- `/api/chat/sessions` 返回本地历史会话数组

---

## 4. 花生壳映射配置

在花生壳客户端或管理后台新增“内网穿透”映射：

| 配置项 | 值 |
| --- | --- |
| 应用名称 | ai-travel-planner-demo |
| 映射类型 | HTTPS 优先，HTTP 也可以 |
| 内网主机 | 127.0.0.1 |
| 内网端口 | 5173 |
| 外网域名/端口 | 由花生壳分配，复制生成的公网地址 |

保存后，花生壳会给出类似下面的地址：

```text
https://xxxxx.oray.net
或
http://xxxxx.vicp.net:端口
```

用这个公网地址访问网站。前端页面里的 `/api` 请求会由 Vite 代理到本机 FastAPI。

---

## 5. 如果一定要保留 Vercel 前端

也可以只映射后端 8000：

1. 花生壳映射 `127.0.0.1:8000`。
2. 必须使用花生壳的 HTTPS 映射，否则 Vercel 的 HTTPS 页面会被浏览器拦截 HTTP 请求。
3. 在 Vercel 项目里把 `VITE_API_BASE` 改成花生壳公网地址。
4. 重新部署 Vercel 前端。

这个方案依赖 Vercel 配置权限，且 SSE 长连接经过花生壳和 Vercel 两跳，稳定性不如直接映射 5173。

---

## 6. 安全注意事项

1. 公网地址不要公开发到群里，知道地址的人都能调用 DeepSeek 和高德接口，消耗你的额度。
2. 演示结束后立即停止花生壳映射，或关闭本地后端。
3. 不要把 `.env`、数据库文件、API Key 提交到 Git。
4. 花生壳免费版可能限速、限流量或自动断开，面试前必须提前测试。
5. 电脑休眠会导致映射失效，建议临时把电源计划改成“从不休眠”。

---

## 7. 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 公网地址打开 502 | 本地 5173 没启动或端口写错 | 先访问 `http://127.0.0.1:5173` 确认 |
| 页面返回 `Blocked request` | Vite 不允许花生壳域名 | 当前配置已允许 `.oray.net` / `.vicp.net`，自定义域名需要补进 `allowedHosts` |
| 页面能开但接口 404 | 后端没启动或代理目标不对 | 检查 `127.0.0.1:8000/api/chat/sessions` |
| 接口报错 Application not found | 访问到了已停用的 Railway 地址 | 改用花生壳公网地址 |
| 生成行程卡住 | 本地后端没有加载 DeepSeek/高德变量 | 检查后端启动环境变量和日志 |
| 花生壳地址打不开 | 电脑休眠、客户端退出、映射过期 | 检查花生壳客户端状态和电脑电源设置 |

---

## 8. 演示前检查清单

- [ ] 后端 `/health` 正常
- [ ] 前端 `127.0.0.1:5173` 正常
- [ ] Vite 代理 `/api/chat/sessions` 正常
- [ ] 花生壳映射状态为“在线”
- [ ] 手机 4G/5G 网络能打开公网地址
- [ ] 电脑电源设置为不休眠
- [ ] 演示账号和 API 额度可用
