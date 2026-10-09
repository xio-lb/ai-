# 方案 C：LangGraph 可靠性与生成质量改造

> 对应提交：方案 C（在方案 A 可观测性、方案 B 多用户隔离之后）
> 目标：把"能生成"升级为"失败可恢复、问题可定位、结果可验证、成本可下降"。

## 1. 改造清单

| 编号 | 改造点 | 解决的问题 | 主要文件 |
| --- | --- | --- | --- |
| C1 | LangGraph Checkpointer | 进程内任务可恢复、并行方案状态互不污染 | `app/services/graph_checkpoint.py`、`app/agents/graph.py` |
| C2 | 日级修复 | 质量失败后整段重生成，Token 浪费且可能引入新错误 | `app/agents/itinerary_agent.py`、`app/agents/graph.py` |
| C3 | 中间结果共享缓存 | 三套候选方案重复查景点/美食/酒店/天气 | `app/services/context_cache.py`、`app/agents/graph.py` |
| C4 | 路线顺序优化 | LLM 按主题排点，可能在城市里来回折返 | `app/services/route_optimizer.py`、`app/agents/graph.py` |
| C5 | 天气驱动编排 | 天气只作为参考文本，雨天仍可能排满户外景点 | `app/agents/graph.py`、`app/services/prompt_builder.py` |

## 2. C1 LangGraph Checkpointer

- 编译图时接入 `SyncMemorySaver`：进程内保存、同步写入，不依赖线程池。
- 每次任务用 `thread_id` 隔离：普通生成、调整、三套候选分别使用独立线程。
- 调用方式统一为 `invoke(..., config={"configurable": {"thread_id": ...}}, durability="sync")`。
- 支持失败后按 thread 恢复，也为后续人工介入、断点重放留出接口。
- 生产升级路径：把 `SyncMemorySaver` 换成 SQLite / Postgres / Redis saver，图代码不用改。

## 3. C2 日级修复

- 质量校验输出带天号的 issue，例如"第 2 天景点坐标不可用"。
- `quality_node` 用正则提取 `invalid_days`，写入状态。
- 能定位天数时走 `repair_days` 节点，只让 LLM 重生成问题天数，再合并回原计划。
- 无法定位天数、天数不匹配等结构性问题仍走整段重排，避免错误地只修局部。
- 修复后重新进入预算校验和质量校验，仍受 3 次总重试预算约束。

## 4. C3 中间结果共享缓存

- 缓存层级在单次请求的 Agent 候选池：景点 / 美食 / 酒店 / 天气。
- 缓存键：`kind + 城市 + 出行月份 + 需求关键词集合`。
- 关键词参与键，避免人文、 美食、自然三套主题拿到同一批候选。
- 命中 / 未命中通过 `record_context_reuse` 写入 trace，可观测缓存收益。
- 与高德底层缓存互补：这一层减少 Agent 重复查询，底层缓存减少单个 POI 查询。

## 5. C4 路线顺序优化

- 每天第一个停靠点固定，景点和餐厅保持相对槽位，避免把午餐优化到早上。
- 先用最近邻构造初始顺序，再用 2-opt 做有界改进。
- 只有路径距离至少下降 10% 才接受重排，防止噪声导致方案抖动。
- 优化发生在路线构建之前，因此轨迹、时长、距离都基于优化后的顺序计算。
- 每天的优化前 / 后距离写入 trace 和 `plan.route_optimization`。

## 6. C5 天气驱动编排

- `build_weather_policy` 把预报转成结构化策略：风险等级、风险日、逐日提示。
- 降水概率 >= 50% 或天气包含雨 / 雪 / 雷 / 冰 / 霾 / 风时标记风险日。
- 风险日要求优先室内景点、准备同区域替代方案，并把备选写入 notes。
- 策略同时传入行程编排 Prompt，雨天不再是"参考信息"，而是硬约束。

## 7. 可观测指标

方案 A 的 trace 之外，本次新增：

| 指标 | 含义 |
| --- | --- |
| `context_reuse_hits / lookups / hit_rate` | Agent 候选池复用率 |
| `route_saved_meters` | 路线优化累计节省距离 |
| `route_optimization[].saved_ratio` | 每天优化前后距离变化 |
| `retry_count / retries[].stage` | 预算、质量、路线各阶段重试 |

## 8. 验证结果

- `backend/tests/test_route_optimizer.py`：最近邻、2-opt、槽位保持、10% 阈值。
- `backend/tests/test_context_cache.py`：关键词隔离、城市 / 月份隔离。
- `backend/tests/test_graph_checkpoint.py`：失败恢复、thread 隔离。
- `backend/tests/test_weather_policy.py`：风险日识别、无预报降级。
- `backend/tests/test_graph_context_and_routes.py`：整图跑通，候选复用命中、路线优化元数据落盘。
- 全量 `pytest` 通过。

## 9. 面试口径

> 方案 C 解决的是可靠性和质量，不是再加一个功能。检查点让图执行可恢复；日级修复把失败重试从"整段重生成"降到"只修问题天"；中间结果缓存让多方案共享候选池；路线优化把 LLM 不擅长的地理顺序交给确定性算法；天气策略把风险日从提示信息升级为编排约束。每一项都有对应的测试和 trace 指标，可以量化命中率、节省距离和重试次数。