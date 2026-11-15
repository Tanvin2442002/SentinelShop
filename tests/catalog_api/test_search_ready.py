def test_search_case_insensitive_substring(client):
    r = client.get("/search", params={"q": "MOUSE"})
    assert r.status_code == 200
    assert [p["id"] for p in r.json()] == [1]


def test_search_no_match_is_empty_list(client):
    r = client.get("/search", params={"q": "' OR 1=1 --"})
    assert r.status_code == 200
    assert r.json() == []


def test_search_q_missing_or_too_long_is_422(client):
    assert client.get("/search").status_code == 422
    assert client.get("/search", params={"q": "a" * 101}).status_code == 422
    assert client.get("/search", params={"q": "a" * 100}).status_code == 200


def test_readyz_ok(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_readyz_reports_each_failing_dependency(client, store, fake_redis):
    store.db_down = True
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"status": "not_ready", "failing": ["db"]}

    fake_redis.down = True
    r = client.get("/readyz")
    assert r.json() == {"status": "not_ready", "failing": ["db", "queue"]}

    store.db_down = False
    r = client.get("/readyz")
    assert r.json() == {"status": "not_ready", "failing": ["queue"]}
