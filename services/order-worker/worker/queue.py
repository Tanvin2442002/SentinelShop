"""Redis client for the order queue."""

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

QUEUE_KEY = "orders:pending"

# BRPOP blocks on the server for this long, then returns None. Short, so a
# SIGTERM is noticed within about a second even when the queue is empty.
BRPOP_TIMEOUT_SECONDS = 1

# Must be longer than BRPOP_TIMEOUT_SECONDS, or every empty BRPOP would end
# in a client-side TimeoutError.
REDIS_TIMEOUT_SECONDS = 2


def make_redis(redis_url: str) -> redis.Redis:
    return redis.Redis.from_url(
        redis_url,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
        # No hidden retries: the worker loop does its own retry with a pause.
        retry=Retry(NoBackoff(), 0),
    )
