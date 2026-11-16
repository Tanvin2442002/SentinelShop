# HighErrorRate (critical)

Fires when more than 5% of requests on one route return 5xx for 5 minutes.

## Symptom
Users get errors on one route. The alert label `route` says which; other routes may be fine.

## Likely causes
| Cause | Hint |
|---|---|
| Application bug or bad change | Errors started right after a deploy or config change |
| Dependency down (database, Redis) | 503 responses, "unavailable" in the logs |
| Resource exhaustion | CPU or memory at the limit on the Golden Signals dashboard |

## Queries
- 5xx share per route: `sum by (route)(rate(http_requests_total{status=~"5.."}[5m])) / sum by (route)(rate(http_requests_total[5m]))`
- Failing requests: `{service="catalog-api"} | json | status=~"5.."`
- Every log line for one request: `{service=~".+"} | json | trace_id="<id>"`

## Fix
1. Find the route and copy the `trace_id` of one failing request.
2. Follow that trace_id through edge, API and worker logs to see where it fails.
3. If a recent change started it, revert it in Git and redeploy.
4. If a dependency is down, restore it (`docker compose ps`).
5. Confirm the 5xx share stays under 5% for 5 minutes.

## Escalate
If unresolved after 15 minutes, or orders may be lost, escalate to the service owner.
