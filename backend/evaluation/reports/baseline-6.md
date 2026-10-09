# AI Travel Planner Evaluation Report

- Tag: baseline-6
- Generated at: 2026-10-09T10:05:35+00:00
- Cases: 6/6
- Data source: real LangGraph pipeline plus configured LLM/Amap services

## Summary

| Metric | Value |
|---|---:|
| Success rate | 100.0% |
| Quality pass rate | 100.0% |
| Route closure rate | 100.0% |
| Budget compliance rate | 100.0% |
| Invalid POI run rate | 0.0% |
| Cache hit rate | 55.0% |
| Latency P50 | 27253.56 ms |
| Latency P95 | 34782.71 ms |
| Average tokens per run | 10344.83 |
| Estimated cost per run | not configured |
| Amap calls per run | 26.33 |
| Total retries | 0 |

## Per-case Results

| Case | Destination | Success | Duration (ms) | Quality | Route | Budget | Tokens | Error |
|---|---|---:|---:|---:|---:|---:|---:|---|
| chengdu-3d-standard | 成都 | yes | 18473 | yes | yes | yes | 10556 |  |
| beijing-3d-culture | 北京 | yes | 29713 | yes | yes | yes | 10076 |  |
| shanghai-2d-city | 上海 | yes | 25009 | yes | yes | yes | 8777 |  |
| xian-3d-history | 西安 | yes | 26835 | yes | yes | yes | 9455 |  |
| chongqing-3d-city | 重庆 | yes | 36473 | yes | yes | yes | 12755 |  |
| sanya-4d-resort | 三亚 | yes | 27672 | yes | yes | yes | 10450 |  |

## Node Latency

| Node | Count | Avg (ms) | P95 (ms) | Max (ms) |
|---|---:|---:|---:|---:|
| analyze | 6 | 1712.09 | 2037.05 | 2072.86 |
| attractions | 6 | 3770.83 | 5141.37 | 5267.72 |
| budget | 6 | 2828.86 | 3281.33 | 3391.18 |
| foods | 6 | 2678.72 | 3899.61 | 4123.13 |
| hotels | 6 | 1668.46 | 2067.77 | 2080.81 |
| itinerary | 6 | 8585.78 | 11005.19 | 11688.15 |
| quality | 6 | 0.19 | 0.37 | 0.43 |
| surrounding | 6 | 10168.75 | 13140.00 | 13594.91 |
| weather | 6 | 2642.03 | 5489.08 | 6502.12 |

## Top Errors

No generation errors recorded.

## Notes

- A full run can be started with: `python -m evaluation.run_eval --concurrency 1`.
- LLM cost is zero unless DEEPSEEK_INPUT_COST_PER_1M and DEEPSEEK_OUTPUT_COST_PER_1M are configured.
- Traces are stored in TRACE_DB_PATH; query one run with `GET /api/metrics/traces/{trace_id}`.
