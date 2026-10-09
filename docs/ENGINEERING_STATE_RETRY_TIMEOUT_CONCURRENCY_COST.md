# 工程五问：状态、重试、超时、并发、成本

> 适用场景：AI 应用开发实习面试，围绕 LangGraph 多 Agent、RAG、FastAPI、Spring Boot、Redis 追问。

## 1. 状态存哪

### 1.1 先分两类状态

| 类型 | 存在哪 | 例子 |
| --- | --- | --- |
| 执行态 | 内存 / Checkpointer | AgentState、当前节点、feedback、retry_count |
| 业务态 | 数据库 / Redis | 历史行程、用户记忆、聊天会话、消息日志、缓存 |

### 1.2 旅行项目

- 单次图执行：`AgentState` 存在内存里，由 LangGraph 合并节点返回的增量。
- 图执行态已经接入 `SyncMemorySaver` 检查点：每次写入用 `thread_id` 隔离，`durability="sync"` 保证节点写入在返回前落盘，单个生成任务可以按 thread 恢复。
- 需要跨请求保存：SQLite（`trip_history`、`user_memory`、`chat_sessions`）。
- 外部 API 结果缓存：SQLite `amap_cache`。
- 当前检查点是进程内实现，进程重启后中间状态仍会丢失；要跨进程恢复需要把 `SyncMemorySaver` 换成 SQLite / Postgres / Redis saver，接口不变。

### 1.3 辅导员 AI

- Redis：答案缓存、Redis List 队列、限流计数、熔断/紧急事件。
- MariaDB：消息日志、人工待办、危机事件。
- 单次 RAG 请求状态：函数内局部变量，不跨请求。

### 1.4 生产环境怎么升级

- LangGraph Checkpointer：当前用 `SyncMemorySaver`（进程内、同步写）支持恢复和 thread 隔离；`InMemorySaver` 只适合本地，生产用 SQLite / Postgres / Redis。
- 用 `thread_id` 或 `session_id` 关联一次任务。
- 支持断点恢复、人工介入、失败重放。
- 不要把完整 Prompt、PII、密钥写进状态存储。

## 2. 失败怎么重试

### 2.1 先区分错误类型

| 错误类型 | 例子 | 是否重试 |
| --- | --- | --- |
| 瞬时错误 | 网络抖动、429、超时 | 重试，指数退避 + 抖动 |
| 永久错误 | 参数错误、400、权限不足 | 不重试，直接失败 |
| 结构错误 | LLM 非 JSON、字段缺失 | 校验后重试 1 次 |
| 业务不满足 | 预算超支、质量不过、路线不闭环 | 带 feedback 回退重排 |

### 2.2 两层重试

- 节点内重试：高德搜索 `_search_pois` 最多重试 3 次。
- 图级重试：预算 / 质量 / 路线失败带 feedback 回到 itinerary，`retry_count < 3`。

### 2.3 重试要加保护

- 有界：不能让 LLM 或外部 API 无限重试。
- 退避：1s、2s、4s + 随机抖动，避免雪崩。
- 幂等：重试写库、扣费、发消息必须带幂等键。
- 熔断：连续失败到阈值就暂停调用。
- 死信队列：异步任务重试耗尽后进 DLQ，人工排查。

### 2.4 辅导员 AI 的做法

- Redis List 队列里的 payload 带 `attempt`，最多重试 3 次。
- `recordRagFailure` 连续失败 3 次，熔断 30 秒。
- 消息失败后重新入队，超过次数标记 FAIL。

## 3. 超时怎么兜

### 3.1 三层超时

| 层级 | 作用 |
| --- | --- |
| 客户端超时 | HTTP connect / read timeout |
| 节点超时 | 单个 Agent 或外部调用最多跑多久 |
| 全链路超时 | 一次生成任务总预算，例如 60 秒 |

### 3.2 你项目里已有

- 高德请求：`httpx.get(..., timeout=15)`。
- 辅导员 LLM：`call_llm(timeout=8)`。
- Feign：connect 3s，read 10s。
- Java 快查缓存：RestTemplate 3 秒。

### 3.3 还缺什么

- 旅行项目的 DeepSeek 调用还没有显式 timeout。
- LangGraph 没有全链路超时。
- 超时后没有统一返回“部分成功 + warning”。

### 3.4 超时后的兜底策略

- 读缓存：上次成功的 POI、路线、天气。
- 切备用源：高德天气失败切 Open-Meteo。
- 降级返回：路线失败就返回文字行程。
- 快速失败：关键节点超时直接返回明确错误。
- SSE 心跳：长连接定期发心跳，避免代理断连。

### 3.5 Python 注意点

- 线程不能强杀，超时要靠协作式取消或进程隔离。
- 后台线程要支持 cancel 标志，避免用户断连后继续烧 token。

## 4. 并发怎么控

### 4.1 并发来源

- 多个用户同时请求。
- 单个请求内多个 Agent 并行。
- 多个外部 API 同时调用。
- 多个实例共享 Redis / DB。

### 4.2 控制手段

| 控制点 | 手段 |
| --- | --- |
| 用户级 | 限流，例如每人每分钟 10 次 |
| 全局级 | 信号量，例如同时最多 20 个生成任务 |
| 外部 API | Semaphore / 令牌桶，限制高德和 LLM 并发 |
| 缓存 | Single-flight，同一个 key 只回源一次 |
| 队列 | 有界队列 + 背压，满了就排队或 429 |
| 多实例 | Redis 分布式锁 / 幂等键 |

### 4.3 你项目里已有

- 高德调用用 `_amap_lock` 全局串行化。
- 辅导员 AI 用 Redis 队列削峰 + 固定窗口限流。
- SSE 每个请求一个后台线程。

### 4.4 建议增强

- 全局锁改成 per-key 锁，不然所有城市搜索都串行。
- 加 Semaphore 限制 LLM 和高德并发。
- 加全局任务并发上限，超过就排队或拒绝。
- 相同 POI 请求做 single-flight，避免重复回源。

## 5. 成本怎么算

### 5.1 成本构成

```text
单次成本 =
  LLM 输入 token × 输入单价
  + LLM 输出 token × 输出单价
  + 外部 API 调用次数 × 单价
  + 基础设施摊销（CPU / 内存 / DB / Redis / 存储）
```

### 5.2 更重要的指标

```text
成本 / 成功交付 = 总成本 / 成功交付数
```

要把失败重试、多方案生成、LLM 多节点调用都算进去。

### 5.3 旅行项目的成本点

- 需求解析、行程编排、预算审核、意图识别都要调 LLM。
- 多方案一次生成 3 套，成本约等于 3 次完整链路。
- 预算 / 质量 / 路线失败重试会继续消耗 token。
- 高德 POI 缓存能省钱，但 LLM 调用没有缓存。

### 5.4 控制成本

- 缓存：外部 API 结果缓存，减少重复请求。
- 模型分级：意图识别用便宜模型，复杂编排用强模型。
- Prompt 瘦身：历史只取最近几条，候选池只传必要字段。
- 结构化输出：减少解析失败和重试。
- 上限：单请求 max tokens、max LLM calls、max retries、总超时。
- 指标：tokens_in、tokens_out、llm_calls、cache_hit_rate、retry_count、cost_per_success。

## 6. 面试回答模板

> 状态分两层：执行态放在 LangGraph 的 AgentState 和 Checkpointer 里，业务态放 SQLite、Redis 和 MariaDB。重试分节点内和图级两层：外部 API 做有界退避重试，业务校验失败带 feedback 回到行程节点，最多 3 次。超时做客户端、节点、全链路三层，超时后优先读缓存、切备用源或降级返回。并发用限流、信号量、队列和 single-flight 控制，多实例用 Redis 锁。成本按 token、外部 API 调用和基础设施摊销算，核心指标是成本除以成功交付数；优化靠缓存、模型分级、Prompt 瘦身和单请求预算上限。

## 7. 高频追问

1. 状态为什么要分执行态和业务态？
2. Checkpointer 用什么存？
3. 重试一定安全吗，怎么做幂等？
4. 超时后线程还在跑怎么办？
5. 并发限制放在服务端还是客户端？
6. 多实例下本地锁为什么不够？
7. 怎么估算一次旅行规划的成本？
8. 多方案生成成本怎么摊到每个成功交付上？
