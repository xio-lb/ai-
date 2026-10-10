# 方案 D：Redis 跨实例缓存与限流升级

> 对应提交：方案 D（在方案 A 可观测性、方案 B 多用户隔离、方案 C LangGraph 可靠性之后）
> 目标：把进程内缓存和进程内限流升级为跨 worker / 跨实例共享，同时保留零配置可运行能力。

## 1. 为什么做这次改造

方案 A-C 解决了可观测、用户隔离、失败恢复和取数复用，但缓存与限流仍然只在一个 Python 进程里生效：

- 每个 uvicorn worker 各自保留一份高德结果缓存，命中率随 worker 数增加而下降。
- 三套候选方案的中间候选池只在当前进程复用，换一个 worker 就要重新查询。
- 任务提交限流在进程内计数，多 worker 下用户可以通过命中不同 worker 绕过额度。
- 登录失败计数同样依赖单个进程，横向扩容后限流失效。

这不是功能缺失，而是"单进程能跑、扩容失效"的典型工程问题。方案 D 只做一件事：在缓存和限流前面加一层可选的 Redis 共享层，并把 Redis 故障降级做成自动行为。

## 2. 设计原则

| 原则 | 落地方式 |
| --- | --- |
| Redis 可选，不是硬依赖 | `REDIS_URL` 为空时全部使用进程内存实现，部署方式不变 |
| 缓存分层 | 进程内 LRU 负责最快命中，Redis 负责跨 worker / 跨实例共享，SQLite 负责单机持久化 |
| 读路径不回退正确性 | Redis 命中直接返回；Redis 未命中先查本地持久层，再把结果回填 Redis |
| 限流语义与原来一致 | 固定窗口原子计数，窗口内第 N 次提交仍允许，超过 N 次后拒绝 |
| 故障自动收敛 | Redis 连接或执行失败后进入 30 秒冷却，冷却期内直接走内存实现，不让每个请求都踩 2 秒超时 |
| Key 可观测 | 所有 key 带可配置前缀 `REDIS_KEY_PREFIX`（默认 `atp`），便于监控和清理 |

## 3. 模块结构

```
app/services/shared_cache.py    # Redis 优先、内存兜底的基础设施层
app/services/cache_service.py   # 高德 SQLite 缓存 + Redis 热层
app/services/context_cache.py   # Agent 候选池：本地 LRU + Redis 共享层
app/services/tasks_service.py   # 任务提交限流：Redis 原子计数 + SQLite 兜底
app/services/auth_service.py    # 登录失败计数：Redis 共享计数 + SQLite 审计
```

### 3.1 shared_cache

对外暴露最小接口：

- `get_json` / `set_json` / `delete` / `delete_prefix`：共享值读写与按前缀失效。
- `hit(key, limit, window_seconds)`：固定窗口原子计数，返回 `(exceeded, current_count)`。
- `current_counter(key)`：只读计数，用于登录失败次数这类"读取但不消费额度"的场景。
- `reset_counter(key)`：成功登录、清理等场景归零。
- `health()` / `stats()`：健康检查和运行指标。

实现要点：

- 使用 `redis.Redis.from_url(..., decode_responses=True)`，连接和读写超时各 2 秒。
- `hit` 使用 `INCR`（跨 worker 原子），首次计数时 `EXPIRE` 设置窗口 TTL。
- 连接失败或运行异常后 `_mark_failure` 清空客户端并进入 30 秒冷却，随后自动降级到内存 OrderedDict。
- Redis 存在时不再在进程内镜像整份数据，避免"缓存放大"和失效时出现双份状态。
- `reset_for_tests` / `use_client_for_tests` 让测试可以注入 `fakeredis`，不需要真实 Redis。

Key 设计：

| 用途 | Key 形态 | 示例 |
| --- | --- | --- |
| 高德热层 | `cache:{namespace}:{cache_key}` | `atp:cache:amap:poi:成都|宽窄巷子||5` |
| Agent 候选池 | `context:{kind}:{destination}:{scope}` | `atp:context:attractions:成都:2026-10|人文` |
| 任务提交限流 | `rate:task_submit:{user_id}` | `atp:rate:task_submit:12` |
| 登录失败限流 | `rate:login_failure:{subject}` | `atp:rate:login_failure:user@example.com` |

## 4. 读路径

### 4.1 高德缓存

```
get_cached(namespace, key)
  -> Redis 热层命中：直接返回，记录 shared hit
  -> Redis 未命中：查 SQLite
       -> SQLite 命中：按剩余 TTL 回填 Redis，返回
       -> SQLite 未命中：返回 None，由调用方请求高德
```

写入时同时写 Redis 和 SQLite，清除缓存时按 `cache:{namespace}:` 前缀同时清理两层。SQLite 仍然是单机持久层，Redis 只是让它能被多个 worker / 实例共享。

### 4.2 Agent 候选池

```
get_or_load(kind, destination, loader, scope, keywords)
  -> 本地 LRU 命中：最快返回
  -> Redis 命中：反序列化为 Pydantic 模型，回填本地 LRU，返回
  -> 都未命中：执行 loader，写本地 LRU + Redis
```

候选池的序列化按 kind 分派：

- `attractions` / `foods` / `hotels`：`list[Candidate]`，用 `model_dump()` / `model_validate()` 往返。
- `weather`：`WeatherInfo`，同样用 Pydantic 序列化，避免把对象直接 JSON 化。

这层解决的是"同一批候选方案三套主题重复查景点、餐厅、酒店、天气"的问题；它和高德底层缓存互补，不互相替代。

## 5. 限流

### 5.1 任务提交

`submit_rate_limited(user_id)` 先走 Redis 原子计数，再查任务表作为权威兜底：

- Redis 计数保证多 worker 共享同一个窗口计数。
- 任务表计数保证进程重启、Redis 清空或降级时额度不会被绕过。
- 判定采用 `max(共享计数, 数据库计数) > 额度` 才拒绝，与原有"窗口内第 N 次仍允许"的语义一致。

### 5.2 登录失败

- 失败：`hit` 增加共享计数，窗口默认 900 秒，额度默认 10 次。
- 成功：`reset_counter` 归零。
- 读取：`current_counter` 只读，不消耗额度。
- SQLite 的登录审计表保留，Redis 只承担跨实例限流，审计和限流职责分离。

## 6. 配置与部署

`.env.example` 新增：

```env
# 留空则使用进程内存实现，单机部署无需 Redis
REDIS_URL=
REDIS_KEY_PREFIX=atp
```

`docker-compose.yml` 新增可选 Redis 服务：

- 镜像 `redis:7-alpine`，开启 AOF 持久化。
- 健康检查 `redis-cli ping`，后端在 Redis 健康后启动。
- 命名卷 `redis_data` 独立于原有 `app_data`，不会清理或覆盖用户已有数据。
- 后端环境变量 `REDIS_URL=redis://redis:6379/0`。

本地不使用 Docker 时，只需在 `.env` 中把 `REDIS_URL` 指向本机 Redis；不配置时行为和改造前一致。

## 7. 可观测性

`GET /health` 现在返回：

```json
{
  "status": "ok",
  "cache": {
    "backend": "redis",
    "configured": true,
    "status": "ok",
    "prefix": "atp"
  }
}
```

`backend` 为 `redis` 表示共享层生效；为 `memory` 表示当前实例正在使用进程内存降级。`context_cache.stats()` 额外暴露 `shared_hits`、`shared_misses`、`shared_backend`，便于比较本地命中与共享命中。

## 8. 验证

本次新增 / 扩展的测试：

- `tests/test_shared_cache.py`：JSON 往返、TTL、前缀删除、原子计数、跨 worker 可见、Redis 不可用降级、只读计数。
- `tests/test_cache.py`：Redis 命中不访问 SQLite；SQLite 命中后回填 Redis。
- `tests/test_context_cache.py`：Redis 候选池命中不调用 loader，并还原 Pydantic 模型；失效清理共享层。
- `tests/test_async_tasks.py`：任务提交额度；健康检查返回缓存后端。
- `tests/test_auth.py`：登录失败计数在共享层可见，成功后归零。

全量测试：`cd backend && .\venv\Scripts\python.exe -m pytest tests -q`。

> 说明：LangGraph 在测试退出时会打印后台 Future 清理噪音，退出码为 0、全部用例通过，属于已知现象。

## 9. 面试口径

可以这样概括这次改造：

> 项目最初用进程内缓存放高德结果和候选池，用进程内计数做提交限流。单实例没问题，但一旦把 uvicorn worker 调到 2 个以上，每个 worker 都有自己的缓存和计数器，缓存命中率下降，限流也可以被绕过。方案 D 抽了一个 `shared_cache` 基础设施层：Redis 优先、进程内存自动降级；高德 SQLite 缓存加 Redis 热层；LangGraph 的候选池放到 Redis 共享；任务提交和登录失败改成 Redis 原子计数。Redis 没有配置或挂掉时，系统自动回退到原来的单进程实现，所以部署方式不变。最后用 fakeredis 覆盖了跨 worker 可见性、回填路径和降级路径。

可继续展开的点：

- 为什么用 `INCR` 而不是先 GET 再 SET：读改写不是原子操作，多 worker 会丢计数。
- 为什么不用 Redis 替换 SQLite：SQLite 承担单机持久化和审计，Redis 是热层和共享层，职责不同。
- 为什么保留数据库计数兜底：Redis 可能被清空或降级，数据库是最终事实来源，额度不能因为缓存故障被绕过。
- 为什么缓存失效要按前缀：候选池按城市失效、高德缓存按 namespace 失效，避免误删其他业务 key。
