# 可观测性与离线评测

本文档描述方案 A 的实现：为每次行程生成建立 trace，提供指标查询接口，并用固定评测集输出可比较的基线报告。目标不是堆监控组件，而是让后续 Prompt、路线和并发优化都有 before/after 数据。

## 1. 一次生成会记录什么

每次生成对应一个 `TraceContext`，包含：

- 基础信息：`trace_id`、`request_id`、目的地、天数、预算、节奏、生成来源。
- 节点耗时：LangGraph 每个节点的执行次数、成功/失败状态和耗时。
- LLM 调用：模型、Prompt 名称、Prompt 哈希、Prompt 版本、输入/输出 Token 和预估费用。
- 外部调用：高德 POI、地理编码、天气、路线、OpenStreetMap/Open-Meteo 等调用的次数、耗时和成功状态。
- 缓存：内存缓存和 SQLite 持久缓存各查询一次是否命中。
- 质量指标：质量校验是否通过、问题数量、无效 POI 数量。
- 预算指标：是否在预算内。
- 路线指标：路线是否闭环，以及重试次数和原因。
- 结果摘要：景点数、餐厅数、酒店数、路线段数、总花费。

Trace 默认写入 `observability.db`，可通过 `TRACE_DB_PATH` 修改。生产 Docker 部署写入 `/data/observability.db`。

## 2. 接入位置

```text
API / 评测脚本
  -> trace_generation()
    -> LangGraph 节点计时
      -> DeepSeek 调用记录 Token
      -> 高德/天气/路线记录外部调用
      -> 缓存记录命中与未命中
    -> 质量、预算、路线结果写入 trace
  -> trace 落库
```

核心实现位于 `backend/app/services/observability.py`。所有记录函数都是 fail-open 的：可观测性写入失败不会影响行程生成。

## 3. 查询指标

### JSON 汇总

```bash
curl http://127.0.0.1:8000/api/metrics/summary?days=30
```

返回内容包括：

- `totals`：总运行数、成功/失败数、独立请求数。
- `rates`：成功率、质量通过率、路线闭环率、预算符合率、无效 POI 运行占比、缓存命中率。
- `latency_ms`：平均、P50、P95、最小和最大生成耗时。
- `tokens`：总 Token、每次运行平均 Token。
- `cost`：预估费用。只有配置了价格环境变量时才会大于 0。
- `external`：高德调用次数、缓存命中与查询次数。
- `retries`：预算、质量和路线重试总数。
- `nodes`：每个 LangGraph 节点的次数、平均耗时、P95 和最大耗时。
- `top_errors`：最常见的错误及次数。

### 查询单次 trace

```bash
curl "http://127.0.0.1:8000/api/metrics/traces?limit=20"
curl "http://127.0.0.1:8000/api/metrics/traces/<trace_id>"
```

### Prometheus 文本格式

```bash
curl http://127.0.0.1:8000/metrics
```

当前暴露的指标包括：

- `travel_planner_runs_total`
- `travel_planner_success_rate`
- `travel_planner_quality_pass_rate`
- `travel_planner_route_closure_rate`
- `travel_planner_budget_compliance_rate`
- `travel_planner_generation_duration_ms`
- `travel_planner_llm_tokens_total`
- `travel_planner_estimated_cost_cny_total`
- `travel_planner_amap_calls_total`
- `travel_planner_cache_hit_rate`
- `travel_planner_node_duration_ms`

## 4. 运行离线评测

评测集位于 `backend/evaluation/cases.json`，当前包含 32 个案例，覆盖不同城市、天数、预算、节奏、人数和饮食限制。

### 冒烟运行

```bash
cd backend
python -m evaluation.run_eval --limit 3 --tag smoke-baseline
```

### 全量运行

```bash
cd backend
python -m evaluation.run_eval --concurrency 1 --tag baseline
```

默认串行执行，避免瞬时打满高德和 LLM 配额。并发运行前请确认账户配额和限流策略。

### 只运行指定案例

```bash
python -m evaluation.run_eval --case-id chengdu-3d-standard --case-id beijing-3d-culture
```

### 生成文档报告

```bash
python -m evaluation.run_eval --limit 3 --tag smoke-baseline --docs-report docs/EVAL_REPORT.md
```

报告会写入 `backend/evaluation/reports/`，同时可选写入 `docs/EVAL_REPORT.md`。

## 5. 指标定义

| 指标 | 定义 | 说明 |
|---|---|---|
| 成功率 | 成功运行 / 总运行 | 失败包括异常和中途未返回计划 |
| 质量通过率 | 质量通过 / 已检查运行 | 只统计实际执行了质量校验的运行 |
| 路线闭环率 | 闭环通过 / 已检查运行 | 检查每天是否从酒店出发并返回酒店 |
| 预算符合率 | 预算内 / 已检查运行 | 只统计执行了预算校验的运行 |
| 无效 POI 率 | 无效 POI 数 / 计划景点数 | 来自质量校验中的候选项和坐标问题 |
| P95 延迟 | 95% 运行不超过的耗时 | 对延迟长尾比平均值更敏感 |
| 缓存命中率 | 缓存命中 / 缓存查询 | 同时包含内存缓存和持久缓存 |
| 单次 Token | 总 Token / 运行数 | 用于比较 Prompt 和模型优化效果 |
| 单次成本 | 总预估费用 / 运行数 | 需要配置价格环境变量后才准确 |

## 6. 成本配置

默认价格是 0，只统计 Token，不伪造费用。要得到预估成本，在 `.env` 中配置：

```env
DEEPSEEK_INPUT_COST_PER_1M=输入价格
DEEPSEEK_OUTPUT_COST_PER_1M=输出价格
```

价格单位是人民币元/百万 Token。模型调价后应同步更新。

## 7. Prompt 版本

每次 LLM 调用会记录：

- `name`：调用名称，例如 `requirement_analyze`、`itinerary_generate`。
- `prompt_version`：环境变量 `PROMPT_VERSION`，默认 `v1`。
- `prompt_hash`：系统 Prompt 的 SHA-256 前 12 位。

Prompt 内容变化后，即使名称相同，`prompt_hash` 也会变化，可用于区分不同版本的生成结果。

## 8. 当前限制

- Trace 仍存放在单机 SQLite，多实例部署前需要迁移到 PostgreSQL。
- 进度状态仍是进程内 ContextVar，不解决多 Worker 的 SSE 进度共享问题。
- 费用是估算值，不包含缓存命中折扣、汇率变化和平台计费差异。
- 离线评测会调用真实 LLM 和高德接口，运行前需要确认 API 配额。
- 当前没有自动 CI 评测门槛，后续可把 `--fail-under-success` 接到 GitHub Actions。

## 9. 面试叙述

> 我为生成链路增加了 trace_id、节点耗时、Token、外部 API、缓存命中、质量、预算和路线指标，并建立了 32 条固定评测集。这样每次修改 Prompt 或路线策略后，都能用同一组样本比较成功率、P95 延迟、无效 POI 率和单次 Token 成本，而不是凭感觉判断优化效果。

## 10. 当前基线

2026-10-09 使用 6 条跨城市案例完成第一轮冒烟基线：

| 指标 | 数值 |
|---|---:|
| 成功率 | 100% |
| 质量通过率 | 100% |
| 路线闭环率 | 100% |
| 预算符合率 | 100% |
| 无效 POI 运行占比 | 0% |
| 缓存命中率 | 55.0% |
| P50 生成耗时 | 27.3 秒 |
| P95 生成耗时 | 34.8 秒 |
| 平均 Token/次 | 10344.83 |
| 平均高德调用/次 | 26.33 |
| 重试次数 | 0 |

说明：这是 6 条案例的冒烟基线，不是完整 32 条的全量结论；LLM 费用因未配置价格环境变量而显示为 not configured。后续优化应保留同一组案例和相同采样口径。
