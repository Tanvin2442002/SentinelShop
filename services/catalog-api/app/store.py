"""Database access. Every statement uses bound parameters (%s), never string formatting."""

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def make_pool(database_url: str) -> ConnectionPool:
    # open=False: the pool is opened in the app lifespan without waiting, so the
    # process starts even while Postgres is still booting (/readyz reports it).
    return ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=10,
        timeout=5,
        open=False,
        kwargs={"row_factory": dict_row},
    )


def _product(row: dict) -> dict:
    # NUMERIC comes back as Decimal; the API contract shows price as a JSON number.
    return {
        "id": row["id"],
        "name": row["name"],
        "price": float(row["price"]),
        "stock": row["stock"],
    }


class Store:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def open(self) -> None:
        self.pool.open(wait=False)

    def close(self) -> None:
        self.pool.close()

    def list_products(self) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, price, stock FROM products ORDER BY id"
            ).fetchall()
        return [_product(r) for r in rows]

    def get_product(self, product_id: int) -> dict | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT id, name, price, stock FROM products WHERE id = %s",
                (product_id,),
            ).fetchone()
        return _product(row) if row else None
