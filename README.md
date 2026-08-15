# AI 旅行规划助手

一个基于 **LangGraph + FastAPI + DeepSeek + 高德地图 + Vue 3** 的多智能体旅行规划应用。用户输入目的地、天数、预算和偏好后，系统通过多个 Agent 协作生成包含真实 POI、每日行程、美食推荐和预算审核的完整旅行方案，并支持实时进度、多轮调整和历史保存。

## 技术栈

| 层级 | 技术 | 用途 |
| --- | --- | --- |
| Agent 编排 | LangGraph | 多 Agent 状态管理、并行分支、条件路由 |
| 后端 | FastAPI | REST API、SSE 流式接口、SQLite 存储 |
| LLM | DeepSeek | 需求分析、行程编排、预算审核 |
| 地图数据 | 高德 Web 服务 API | 真实景点与美食 POI 检索 |
| 前端 | Vue 3 + TypeScript + Vite | 表单、进度、行程展示、高德地图可视化 |
| 地图渲染 | 高德 JS API 2.0 | 景点与美食地图标记 |
| 历史存储 | SQLite | 行程保存、查询、删除 |

## 系统架构

```mermaid
flowchart TD
    U[用户输入] --> A[需求解析 Agent]
    A --> B[景点 Agent<br/>高德真实 POI]
    A --> C[美食 Agent<br/>高德真实 POI]
    B --> D[行程编排 Agent]
    C --> D
    D --> E[预算校验 Agent]
    E -->|超出预算| D
    E -->|预算内| F[行程结果]
    F --> G[SSE 实时输出]
    F --> H[前端地图可视化]
    F --> I[历史保存 SQLite]
```

## 五个 Agent 职责

| Agent | 输入 | 输出 | 职责 |
| --- | --- | --- | --- |
| 需求解析 Agent | 用户请求 | 需求分析 + 搜索关键词 | 分析目的地、天数、预算、偏好，生成高德搜索词 |
| 景点 Agent | 需求分析 | 景点候选列表 | 调用高德 POI 搜索，返回真实景点及坐标 |
| 美食 Agent | 需求分析 | 美食候选列表 | 调用高德 POI 搜索，返回真实餐厅及坐标 |
| 行程编排 Agent | 候选景点 + 候选美食 | 每日行程 | 从真实候选清单中选择并编排每日行程 |
| 预算校验 Agent | 行程计划 | 预算报告 | 校验总花费，超支时自动触发重新编排 |

## 接口清单

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| POST | `/api/trip/plan` | 生成行程 |
| POST | `/api/trip/plan/stream` | SSE 流式生成行程，带 Agent 进度 |
| POST | `/api/trip/plan/adjust` | 基于当前行程执行多轮调整 |
| POST | `/api/history` | 保存行程 |
| GET | `/api/history` | 获取历史列表 |
| GET | `/api/history/{id}` | 获取历史行程详情 |
| DELETE | `/api/history/{id}` | 删除历史行程 |

## 项目结构

```text
ai-travel-planner/
├─ backend/
│  ├─ app/
│  │  ├─ agents/
│  │  │  ├─ requirement_agent.py   # 需求解析 Agent
│  │  │  ├─ attraction_agent.py    # 景点 Agent
│  │  │  ├─ food_agent.py          # 美食 Agent
│  │  │  ├─ itinerary_agent.py     # 行程编排 Agent
│  │  │  ├─ budget_agent.py        # 预算校验 Agent
│  │  │  ├─ graph.py               # LangGraph 工作流
│  │  │  └─ orchestrator.py        # 编排入口
│  │  ├─ schemas/
│  │  │  └─ trip.py                # Pydantic 数据模型
│  │  ├─ services/
│  │  │  ├─ deepseek_client.py     # DeepSeek 调用
│  │  │  ├─ prompt_builder.py      # 提示词构造
│  │  │  ├─ amap_client.py         # 高德 POI 检索
│  │  │  └─ history_service.py     # SQLite 历史存储
│  │  └─ main.py                   # FastAPI 入口
│  ├─ requirements.txt
│  └─ test_*.py                    # 各模块测试脚本
├─ frontend/
│  ├─ src/
│  │  └─ App.vue                   # 前端主页面
│  ├─ vite.config.ts
│  └─ package.json
├─ .gitignore
└─ README.md
```

## 本地运行

### 1. 后端

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

后端默认运行在 `http://127.0.0.1:8000`，Swagger 文档位于 `http://127.0.0.1:8000/docs`。

### 2. 前端

```powershell
cd frontend
npm install
npm run dev
```

前端默认运行在 `http://localhost:5173`。

## 环境变量

在项目根目录创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=sk-你的DeepSeekKey
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

AMAP_WEB_KEY=你的高德Web服务Key

VITE_AMAP_JS_KEY=你的高德JS API Key
VITE_AMAP_SECURITY_CODE=你的高德安全密钥
```

注意：

- `AMAP_WEB_KEY` 用于后端 POI 搜索，需在高德控制台申请“Web服务”类型 Key。
- `VITE_AMAP_JS_KEY` 用于前端地图，需申请“Web端(JS API)”类型 Key，并在域名白名单中加入 `localhost:5173`。
- `.env` 已被 `.gitignore` 忽略，不要提交到 Git。

## 当前功能

- [x] LangGraph 五 Agent 协作
- [x] SSE 实时 Agent 进度
- [x] 高德真实景点与美食 POI
- [x] 高德酒店 / 天气 / 周边游玩 / 驾车路线数据
- [x] 前端高德地图可视化
- [x] 按天切换路线并播放动画
- [x] 多轮对话调整行程
- [x] SQLite 历史保存与加载
- [x] 预算超支自动重排
- [x] 左侧对话 + 右侧行程一体化布局

## 核心亮点

1. **LLM 与真实数据结合**
   需求分析 Agent 生成具体搜索词，高德 API 召回真实 POI，避免 LLM 编造不存在的景点和餐厅。

2. **LangGraph 条件路由**
   预算校验 Agent 检测超支后，自动将流程路由回行程编排 Agent 重新生成，最多重试 3 次。

3. **SSE 实时反馈**
   前端能实时看到“需求解析 -> 景点筛选 -> 美食筛选 -> 行程编排 -> 预算审核”的完整执行过程。

4. **可交互修正**
   生成行程后，用户可以用自然语言继续调整，例如“把第二天的餐厅换成更便宜的”，系统会保留不需要改动的部分。

5. **完整工程化闭环**
   包含数据模型、服务分层、测试脚本、历史存储、前端渲染与 Git 里程碑管理。

## 面试话术参考

> 我实现了一个多智能体旅行规划系统。核心设计是让 LLM 负责需求理解和行程编排，让高德 API 负责召回真实 POI，再通过 LangGraph 的状态图把五个 Agent 串联起来。预算校验 Agent 会检查总花费，超支时通过条件路由自动回到行程编排节点重新生成。前端使用 SSE 实时展示每个 Agent 的执行状态，并支持自然语言多轮调整和 SQLite 历史保存。
