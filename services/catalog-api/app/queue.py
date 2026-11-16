"""Redis client for the order queue."""

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

# A dead or unreachable Redis must make /readyz and POST /orders fail in about
# 2 s (contracts/api.md: 503, process stays up), not hang the request.
REDIS_TIMEOUT_SECONDS = 2


def make_redis(redis_url: str) -> redis.Redis:
    return redis.Redis.from_url(
        redis_url,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
        # No retries, set explicitly: redis.Redis() (not from_url) defaults to
        # 10 retries with backoff, which would turn 2 s into 20 s or more.
        retry=Retry(NoBackoff(), 0),
    )
