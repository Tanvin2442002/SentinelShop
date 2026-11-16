# HighLatency (warning)

Fires when p95 latency on one route is above 1 second for 5 minutes.

## Symptom
Pages feel slow on one route. The alert label `route` says which.

## Likely causes
| Cause | Hint |
|---|---|
| Slow code path or slow dependency | Only one route is slow, others are flat |
| CPU throttling or memory pressure | Container CPU at its limit |
| Database slow or saturated | Latency rises on every route that queries it |

## Queries
- p95 per route: `histogram_quantile(0.95, sum by (le, route)(rate(http_request_duration_seconds_bucket[5m])))`
- Slowest requests: `{service="catalog-api"} | json | request_time > 1`
- Container CPU: `rate(container_cpu_usage_seconds_total{name=~"sentinelshop-.+"}[5m])`

## Fix
1. Check whether one route or all routes are slow.
2. Open a slow request by trace_id and compare its timing to a normal one.
3. If a recent change started it, revert it in Git and redeploy.
4. Confirm p95 is back under 1 second.

## Escalate
If still slow after 30 minutes, escalate to the service owner.
