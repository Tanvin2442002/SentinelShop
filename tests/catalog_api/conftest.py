"""Fakes for Postgres and Redis so the API can be tested without the stack."""

import pytest
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


class FakeRedis:
    def __init__(self):
        self.lists = {}
        self.down = False

    def llen(self, key):
        if self.down:
            raise ConnectionError("redis down")
        return len(self.lists.get(key, []))


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
