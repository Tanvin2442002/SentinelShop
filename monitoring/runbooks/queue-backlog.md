# QueueBacklog (warning)

Fires when `order_queue_depth` is above 50 for 10 minutes.

## Symptom
Orders stay PENDING. Orders created keeps rising while orders processed falls behind.

## Likely causes
| Cause | Hint |
|---|---|
| Workers slower than usual | `order_processing_seconds` p95 has jumped |
| Workers down or restarting | Fewer worker targets up, restart alert |
| Traffic spike | Created rate far above normal |

## Queries
- Depth: `order_queue_depth`
- Created vs processed: `rate(orders_created_total[5m])` and `sum(rate(orders_processed_total[5m]))`
- Processing time p95: `histogram_quantile(0.95, sum by (le)(rate(order_processing_seconds_bucket[5m])))`
- Worker logs: `{service="order-worker"} | json`

## Fix
1. Compare created and processed rates to see which side moved.
2. If processing time rose, look at worker logs for slow steps.
3. If workers are down, restart them and watch the queue drain.
4. If it is only a spike, add worker replicas temporarily.
5. Confirm depth falls below 50 and keeps falling.

## Escalate
If the queue keeps growing for 30 minutes, escalate to the service owner.
