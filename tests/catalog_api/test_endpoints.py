def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_products(client):
    r = client.get("/products")
    assert r.status_code == 200
    body = r.json()
    assert body[0] == {"id": 1, "name": "Wireless Mouse", "price": 19.99, "stock": 100}


def test_get_product(client):
    r = client.get("/products/2")
    assert r.status_code == 200
    assert r.json()["name"] == "USB-C Hub"


def test_get_product_missing_is_404(client):
    r = client.get("/products/999")
    assert r.status_code == 404
    assert r.json() == {"detail": "product not found"}


def test_get_product_non_integer_is_422_with_text_detail(client):
    r = client.get("/products/abc")
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)


def test_unknown_path_uses_default_404(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_unhandled_error_is_generic_500(client, store):
    store.fail = True
    r = client.get("/products")
    assert r.status_code == 500
    assert r.json() == {"detail": "internal error"}
    assert "X-Trace-Id" in r.headers


def test_lifespan_opens_store(client, store):
    assert store.opened is True
