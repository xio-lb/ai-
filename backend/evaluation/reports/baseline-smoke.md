# AI Travel Planner Evaluation Report

- Tag: baseline-smoke
- Generated at: 2026-10-09T10:02:33+00:00
- Cases: 3/3
- Data source: real LangGraph pipeline plus configured LLM/Amap services

## Summary

| Metric | Value |
|---|---:|
| Success rate | 100.0% |
| Quality pass rate | 100.0% |
| Route closure rate | 100.0% |
| Budget compliance rate | 100.0% |
| Invalid POI run rate | 0.0% |
| Cache hit rate | 61.0% |
| Latency P50 | 24854.42 ms |
| Latency P95 | 24922.74 ms |
| Average tokens per run | 9556.33 |
| Estimated cost per run | 0.000000 CNY |
| Amap calls per run | 21.67 |
| Total retries | 0 |

## Per-case Results

| Case | Destination | Success | Duration (ms) | Quality | Route | Budget | Tokens | Error |
|---|---|---:|---:|---:|---:|---:|---:|---|
| chengdu-2d-food | 成都 | yes | 24854 | yes | yes | yes | 8781 |  |
| chengdu-3d-standard | 成都 | yes | 22468 | yes | yes | yes | 10078 |  |
| chengdu-4d-relaxed | 成都 | yes | 24930 | yes | yes | yes | 9810 |  |

## Node Latency

| Node | Count | Avg (ms) | P95 (ms) | Max (ms) |
|---|---:|---:|---:|---:|
| analyze | 3 | 2887.78 | 4472.28 | 4743.21 |
| attractions | 3 | 2822.89 | 4646.02 | 4828.18 |
| budget | 3 | 2709.37 | 2913.92 | 2939.00 |
| foods | 3 | 2212.50 | 3505.84 | 3711.97 |
| hotels | 3 | 490.49 | 1324.23 | 1471.36 |
| itinerary | 3 | 7483.55 | 8163.43 | 8182.33 |
| quality | 3 | 0.22 | 0.38 | 0.41 |
| surrounding | 3 | 7816.33 | 8851.45 | 8939.90 |
| weather | 3 | 1229.18 | 2356.15 | 2554.44 |

## Top Errors

No generation errors recorded.

## Notes

- A full run can be started with: `python -m evaluation.run_eval --concurrency 1`.
- LLM cost is zero unless DEEPSEEK_INPUT_COST_PER_1M and DEEPSEEK_OUTPUT_COST_PER_1M are configured.
- Traces are stored in TRACE_DB_PATH; query one run with `GET /api/metrics/traces/{trace_id}`.
