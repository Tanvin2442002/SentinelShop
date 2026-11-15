"""Fakes for Postgres and Redis so the API can be tested without the stack."""

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PRODUCTS = [
    {"id": 1, "name": "Wireless Mouse", "price": 19.99, "stock": 100},
    {"id": 2, "name": "USB-C Hub", "price": 34.5, "stock": 80},
]


class FakeStore:
    def __init__(self):
        self.opened = False
        self.fail = False
        self.db_down = False
        self.create_fails = False
        self.mark_fails = False
        self.orders = {}
        self.login_calls = []

    def open(self):
        self.opened = True

    def close(self):
        self.opened = False

    def list_products(self):
        if self.fail:
            raise RuntimeError("db down")
        return list(PRODUCTS)

    def get_product(self, product_id):
        return next((p for p in PRODUCTS if p["id"] == product_id), None)

    def search_products(self, query):
        return [p for p in PRODUCTS if query.lower() in p["name"].lower()]

    def create_order(self, product_id, quantity):
        if self.create_fails:
            raise psycopg.OperationalError("db down")
        if self.get_product(product_id) is None:
            return None
        order_id = len(self.orders) + 1
        self.orders[order_id] = {"id": order_id, "product_id": product_id,
                                 "quantity": quantity, "status": "PENDING"}
        return order_id

    def mark_order_failed(self, order_id):
        if self.mark_fails:
            raise psycopg.OperationalError("db down")
        self.orders[order_id]["status"] = "FAILED"

    def get_order(self, order_id):
        return self.orders.get(order_id)

    def check_login(self, username, password):
        self.login_calls.append((username, password))
        if USERS.get(username, (None,))[0] == password:
            return {"username": username, "role": USERS[username][1]}
        return None

    def ping(self):
        if self.db_down:
            raise RuntimeError("db down")


# DEMO credentials, same fake lab values as db/init.sql.
USERS = {"alice": ("alice-demo-pw", "customer")}


class FakeRedis:
    def __init__(self):
        self.lists = {}
        self.down = False

    def _check(self):
        if self.down:
            raise redis.exceptions.ConnectionError("redis down")

    def llen(self, key):
        self._check()
        return len(self.lists.get(key, []))

    def lpush(self, key, value):
        self._check()
        self.lists.setdefault(key, []).insert(0, value)

    def ping(self):
        self._check()
        return True


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url="postgresql://fake",
        redis_url="redis://fake",
        secret_key="test-only-not-a-secret",
        log_level="DEBUG",
        log_file=str(tmp_path / "api.json"),
    )


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def client(settings, store, fake_redis):
    app = create_app(settings=settings, store=store, redis_client=fake_redis)
    with TestClient(app) as c:
        yield c
