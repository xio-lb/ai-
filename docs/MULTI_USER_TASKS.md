# 多用户与异步任务架构

本文对应"最具面试价值的改造方案 B"：把单用户同步应用升级为**多用户隔离 + 异步任务化**的后端。核心目标是让"高并发""数据隔离""任务编排"这三类面试话题都能落到真实代码上，而不是停留在口头设计。

## 1. 为什么要改

改造前的形态是典型的单用户原型：

- `trip_history`、`chat_sessions`、`user_memory` 都没有归属字段，任何请求都能看到全部数据。
- `/api/trip/plan` 同步执行 LangGraph，一次生成要 30 秒左右，期间请求一直占着连接。
- 同时来多个用户，只能靠线程池硬扛，无法排队、无法限流、无法查任务状态。

改造后：

- 每个请求先解析身份，所有业务表都按 `user_id` 读写。
- 生成任务改成"提交-轮询/订阅"两段式，接口立即返回 `task_id`。
- 任务有独立状态机、进度、取消和限流，可以横向迁移到 Redis 队列。

## 2. 认证与用户身份

### 2.1 密码存储

`app/services/auth_service.py` 使用 `PBKDF2-HMAC-SHA256`，每个密码独立随机盐：

```
pbkdf2_sha256$迭代次数$盐(base64url)$摘要(base64url)
```

校验使用 `hmac.compare_digest` 做恒定时间比较，避免通过响应耗时猜测密码。选标准库而不是 bcrypt，是为了不引入 C 扩展依赖，同时保留"加盐 + 慢哈希 + 恒定时间比较"这三个关键属性。

### 2.2 JWT 会话

- 算法 `HS256`，签名密钥优先读 `JWT_SECRET`，未配置时自动生成 `jwt_secret.key`。
- 载荷包含 `sub`（用户 ID）、`iss`、`iat`、`exp`、`jti`。
- `jti` 写入 `auth_tokens` 表，因此 token 可以**主动吊销**：登出后该 token 立即失效。

这比"纯无状态 JWT"多了一次数据库查询，换来的是可登出、可禁用账号，属于有意识的取舍。如果将来要极致降延迟，可以把 `jti` 黑名单放到 Redis。

### 2.3 匿名演示模式

默认 `REQUIRE_AUTH=false`：没有 token 的请求落到保留的"公共演示账号"（`id=1`），保证线上 Demo 打开即用。把 `REQUIRE_AUTH=true` 后，所有业务接口都会返回 401，进入严格多用户模式。

历史数据不会丢：`id=10` 是保留的"历史数据"账号，迁移时旧行会自动归属到它。

## 3. 数据隔离

所有业务表都增加 `user_id` 列并建立复合索引：

| 表 | 归属字段 | 关键索引 |
| --- | --- | --- |
| `trip_history` | `user_id` | `(user_id, id DESC)` |
| `chat_sessions` | `user_id` | `(user_id, updated_at DESC)` |
| `user_memory` | `user_id` 主键 | 每用户一行 |
| `plan_tasks` | `user_id` | `(user_id, created_at DESC)` |

读写都在 SQL 的 `WHERE` 里带 `user_id`，而不是在 Python 里查出来再过滤。跨用户读取统一返回 404 而不是 403，避免泄露"这个资源确实存在"。

迁移方式采用幂等 DDL：启动时检测列是否存在，缺失才 `ALTER TABLE`。旧数据通过 `DEFAULT 10` 自动归属到历史账号。生产环境接 PostgreSQL 时，这套检测逻辑可以平滑换成 Alembic 迁移脚本。

## 4. 异步任务

### 4.1 状态机

```
queued ──> running ──> succeeded
   │           │
   └───────────┴────-> failed
   └───────────┴────-> cancelled
```

状态持久化在 `plan_tasks` 表，字段包括请求 JSON、结果 JSON、进度文案、错误、`trace_id`、取消标记和时间戳。

### 4.2 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/tasks/plan` | 提交任务，返回 202 + `task_id` |
| GET | `/api/tasks/{task_id}` | 查询状态；成功时带完整行程 |
| GET | `/api/tasks/{task_id}/stream` | SSE 订阅进度直到终态 |
| POST | `/api/tasks/{task_id}/cancel` | 取消任务 |
| GET | `/api/tasks` | 当前用户的任务列表 |

### 4.3 执行与取消

- 进程内启动 `TASK_WORKER_COUNT` 个 worker 线程，`SELECT ... LIMIT 1` 抢占任务并把状态改成 `running`。
- 进度通过 `contextvars` 回调写入任务行，SSE 端按需推送。
- 取消检查挂在与 LangGraph 共用的 context var 上：每个节点开始前调用 `raise_if_cancelled()`，任务取消后会在下一个节点边界安全退出，而不是杀线程。
- `TASK_MAX_RUNNING_PER_USER` 限制单用户同时在跑的任务数，`TASK_SUBMIT_MAX_PER_WINDOW` 限制提交频率。
- 进程崩溃遗留的 `running` 任务在启动时按 `TASK_STALE_RUNNING_SECONDS` 重新排队。

### 4.4 从单机到分布式的升级路径

当前实现刻意把对外接口收敛成四个函数：`create_task` / `get_task` / `cancel_task` / `list_tasks`。要换成 Redis 队列时：

1. `plan_tasks` 表结构不变，改由独立 Worker 进程消费 Redis Stream。
2. `create_task` 写入 Redis 后返回 `task_id`，状态仍落库。
3. API 进程不再启动 worker，只负责提交和查询。
4. 多实例共享同一份 Redis + PostgreSQL，任务天然跨实例可见。

对外的 API 契约不需要改，前端无感知。

## 5. 兼容性

原有的同步接口全部保留：`/api/trip/plan`、`/api/trip/plan/stream`、`/api/trip/plan/variants*`、`/api/history`、`/api/chat`、`/api/memory`。区别只是它们现在都带用户作用域。前端可以在不改交互的前提下逐步切到异步任务接口。

## 6. 测试覆盖

`backend/tests/` 中与方案 B 直接相关的用例：

- `test_auth.py`：注册、登录、token 篡改、过期、登出吊销、登录失败限流、密码加盐。
- `test_async_tasks.py`：任务完成、结果可见性、跨用户隔离、取消、提交限流。
- `test_history.py` / `test_chat_sessions.py`：归属校验与越权返回 404。

运行：

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
```