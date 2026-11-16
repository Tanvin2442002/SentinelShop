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

    def search_products(self, query: str) -> list[dict]:
        # The LIKE pattern is built here and sent as a bound parameter.
        # %, _ and \ typed by the user are escaped so they match literally.
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, price, stock FROM products "
                "WHERE name ILIKE %s ESCAPE '\\' ORDER BY id",
                (pattern,),
            ).fetchall()
        return [_product(r) for r in rows]

    def create_order(self, product_id: int, quantity: int) -> int | None:
        """Insert a PENDING order. Returns its id, or None if the product does not exist."""
        # INSERT ... SELECT inserts nothing when the product is missing, so the
        # existence check and the insert are one atomic statement.
        with self.pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO orders (product_id, quantity, status) "
                "SELECT id, %s, 'PENDING' FROM products WHERE id = %s "
                "RETURNING id",
                (quantity, product_id),
            ).fetchone()
        return row["id"] if row else None

    def mark_order_failed(self, order_id: int) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE orders SET status = 'FAILED', updated_at = now() WHERE id = %s",
                (order_id,),
            )

    def get_order(self, order_id: int) -> dict | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT id, product_id, quantity, status FROM orders WHERE id = %s",
                (order_id,),
            ).fetchone()
        return dict(row) if row else None

    def check_login(self, username: str, password: str) -> dict | None:
        """Return {"username", "role"} if the password matches, else None."""
        # crypt() re-hashes the given password with the stored salt/cost and
        # compares inside Postgres; the password never leaves this call.
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT username, role FROM users "
                "WHERE username = %s AND password_hash = crypt(%s, password_hash)",
                (username, password),
            ).fetchone()
        return dict(row) if row else None

    def ping(self) -> None:
        """Raise if the database cannot answer. Short timeout: /readyz must not hang."""
        with self.pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
