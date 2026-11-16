# ContainerRestarting (critical)

Fires when a container's start time changed in the last 10 minutes, meaning it restarted or was killed and restarted by Docker.

## Symptom
Brief outage or a stalled queue. The alert label `container` says which one.

## Likely causes
| Cause | Hint |
|---|---|
| Out of memory kill | Memory climbed steadily to the limit before the restart |
| Crash on startup or runtime | Error or traceback in the container logs |
| Manual restart | A planned `docker restart` (does not apply to a recreate) |

## Queries
- Restarts: `changes(container_start_time_seconds{name=~"sentinelshop-.+"}[10m])`
- Memory per container: `container_memory_working_set_bytes{name=~"sentinelshop-.+"}`
- OOM kills: `increase(container_oom_events_total{name=~"sentinelshop-.+"}[10m])`
- Last logs: `{container="<name>"}`

## Fix
1. Check memory and OOM kills first.
2. If memory grew steadily until the kill, find what changed and revert it in Git.
3. If it crashed, read the last log lines and fix the error.
4. Confirm the container has stayed up for 10 minutes.

## Escalate
If it restarts more than three times in 30 minutes, escalate to the service owner.
