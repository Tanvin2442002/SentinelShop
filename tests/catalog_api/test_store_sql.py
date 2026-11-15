"""Store tests with a recording fake pool: prove every query is parameterised."""

from contextlib import contextmanager

from app.store import Store


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, pool):
        self.pool = pool

    def execute(self, sql, params=None):
        self.pool.calls.append((sql, params))
        return FakeCursor(self.pool.rows)


class FakePool:
    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows or []

    @contextmanager
    def connection(self, timeout=None):
        yield FakeConn(self)


def test_search_pattern_is_a_bound_parameter_with_wildcards_escaped():
    pool = FakePool()
    Store(pool).search_products("50%_off\\'; DROP TABLE products;--")
    sql, params = pool.calls[-1]
    # User text never appears in the SQL string itself.
    assert "DROP" not in sql and "%s" in sql
    assert params == ("%50\\%\\_off\\\\'; DROP TABLE products;--%",)


def test_login_uses_contract_query_with_params():
    pool = FakePool(rows=[{"username": "alice", "role": "customer"}])
    user = Store(pool).check_login("alice", "pw' OR '1'='1")
    sql, params = pool.calls[-1]
    assert sql == ("SELECT username, role FROM users "
                   "WHERE username = %s AND password_hash = crypt(%s, password_hash)")
    assert params == ("alice", "pw' OR '1'='1")
    assert user == {"username": "alice", "role": "customer"}


def test_create_order_returns_none_for_unknown_product():
    pool = FakePool(rows=[])
    assert Store(pool).create_order(999, 1) is None
    sql, params = pool.calls[-1]
    assert params == (1, 999)


def test_create_order_returns_new_id():
    pool = FakePool(rows=[{"id": 7}])
    assert Store(pool).create_order(1, 2) == 7


def test_all_store_queries_use_placeholders():
    pool = FakePool(rows=[{"id": 1, "product_id": 1, "quantity": 1, "status": "PENDING",
                           "name": "x", "price": 1, "stock": 1}])
    s = Store(pool)
    s.get_product(1)
    s.get_order(1)
    s.mark_order_failed(1)
    for sql, params in pool.calls:
        assert "%s" in sql and params == (1,)
