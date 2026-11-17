# RCA: orders slow to complete (chaos drill)

## Summary
Orders were accepted quickly but took far longer to complete. The queue grew until QueueBacklog fired.

## Timeline (UTC, 2026-11-17)
| Time | Event |
|---|---|
| 06:56:36 | Chaos applied, load started |
| 06:59:55 | QueueBacklog pending |
| 07:10 | QueueBacklog firing (queue > 50 for 10 min) |
| 07:11:28 | Suspected worker side |
| 07:18:22 | Processing time per order about 5.5 s on both workers, baseline about 1.5 s |
| 07:27:58 | Trace 5995bc62f807d6fbdc72be5ff775cdda: 15 min queue wait, 5.03 s processing |
| 07:29:51 | POST /orders p99 87.4 ms, API normal |
| 07:36:35 | Root cause identified |
| 07:49:09 | make chaos-revert |
| 07:49:33 | Processing time back to about 1.5 s, queue under 50 |

## First alert
QueueBacklog. It fires when order_queue_depth stays above 50 for more than 10 minutes. It is a symptom alert, so it fires late.

## Investigation
1. Alert pointed at the queue, so I compared the dashboard with the baseline.
2. API routes and POST /orders latency were normal. The problem was on the worker side.
3. Created orders were higher than processed orders, and the backlog kept growing.
4. Processing time per order was about 5.5 s on both workers against about 1.5 s at baseline.
5. A trace showed the order waited about 15 min in the queue and then took 5.03 s to process.
6. No worker restarts, so not a crash. Memory flat, so not a leak. No failed orders, so not an error-rate fault.

## Root cause
Slow database writes in the worker: about 4 s extra per order, which matches 2 updates x 2 s. The slower workers could not keep up with the arrival rate (20 rps), so the queue grew.

## Time to recover
About 24 s after make chaos-revert. About 53 min from fault to recovery, of which 40 min was detection and diagnosis.

## Preventive measure
Add an alert on worker processing time (average above 3 s for 2 min). It would fire in minutes, before the queue builds up.

## Confirmation
After the revert, chaos/active.env showed CHAOS_SLOW_DB=true was the injected fault. This matched the diagnosis.
