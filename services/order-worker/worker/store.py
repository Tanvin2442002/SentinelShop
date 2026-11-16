"""Database access. Every statement uses bound parameters (%s), never string formatting."""

from psycopg_pool import ConnectionPool

# Only orders still in flight may move forward. This stops a duplicate message
# from touching a finished order, and stops the worker from completing an order
# the API already marked FAILED (e.g. LPUSH timed out but Redis did store it).
_ADVANCE = (
    "UPDATE orders SET status = %s, updated_at = now() "
    "WHERE id = %s AND status IN ('PENDING', 'PROCESSING') "
    "RETURNING id"
)


def make_pool(database_url: str) -> ConnectionPool:
    # open=False plus open(wait=False): the worker starts even while Postgres
    # is still booting; a failed update is pushed back and retried.
    return ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=2,
        timeout=2,
        open=False,
    )


class Store:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def open(self) -> None:
        self.pool.open(wait=False)

    def close(self) -> None:
        self.pool.close()

    def set_status(self, order_id: int, status: str) -> bool:
        """Move an in-flight order to `status`. False if no such in-flight order."""
        with self.pool.connection() as conn:
            row = conn.execute(_ADVANCE, (status, order_id)).fetchone()
        return row is not None
