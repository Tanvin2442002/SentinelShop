import json

from app.auth import make_token, verify_token

KEY = "test-only-not-a-secret"


def _log_text(settings):
    with open(settings.log_file) as f:
        return f.read()


def test_login_success_returns_signed_token(client, settings):
    r = client.post("/login", json={"username": "alice", "password": "alice-demo-pw"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert verify_token(settings.secret_key, body["token"]) == "alice"


def test_login_wrong_password_is_401_and_logged_without_password(client, settings):
    r = client.post("/login", json={"username": "alice", "password": "WRONG-pw-xyz"},
                    headers={"X-Real-IP": "172.30.0.50"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid credentials"}

    lines = [json.loads(l) for l in _log_text(settings).splitlines() if l.strip()]
    failed = [l for l in lines if l["message"] == "login failed"][-1]
    assert failed["level"] == "WARNING"
    assert failed["user"] == "alice"
    assert failed["client_ip"] == "172.30.0.50"
    assert failed["trace_id"] == r.headers["X-Trace-Id"]
    access = [l for l in lines if l["message"] == "request" and l["path"] == "/login"][-1]
    assert access["level"] == "WARNING" and access["status"] == 401
    assert "WRONG-pw-xyz" not in _log_text(settings)


def test_login_unknown_user_same_401(client):
    r = client.post("/login", json={"username": "mallory", "password": "x"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid credentials"}


def test_login_bad_body_is_422_and_never_queries_db(client, store):
    r = client.post("/login", json={"username": "alice"})
    assert r.status_code == 422
    r = client.post("/login", json={"username": "alice", "password": "x" * 129})
    assert r.status_code == 422
    assert store.login_calls == []


def test_token_rejects_tampering_wrong_key_and_expiry():
    token = make_token(KEY, "alice", 60, now=1000)
    assert verify_token(KEY, token, now=1000) == "alice"
    assert verify_token("other-key", token, now=1000) is None
    assert verify_token(KEY, token, now=1061) is None
    forged = make_token("other-key", "admin", 60, now=1000).split(".")[0] + "." + token.split(".")[1]
    assert verify_token(KEY, forged, now=1000) is None
    for junk in ("", "abc", "a.b", "!!!.00"):
        assert verify_token(KEY, junk, now=1000) is None


def _login_failed_lines(settings):
    lines = [json.loads(l) for l in _log_text(settings).splitlines() if l.strip()]
    return [l for l in lines if l["message"] == "login failed"]


def test_login_422_oversized_password_is_logged_without_password(client, settings):
    secret = "P" * 200
    r = client.post("/login", json={"username": "alice", "password": secret},
                    headers={"X-Real-IP": "172.30.0.50"})
    assert r.status_code == 422
    failed = _login_failed_lines(settings)[-1]
    assert failed["level"] == "WARNING"
    assert failed["user"] == "alice"
    assert failed["client_ip"] == "172.30.0.50"
    assert failed["trace_id"] == r.headers["X-Trace-Id"]
    assert secret not in _log_text(settings)


def test_login_422_long_username_truncated_to_64(client, settings):
    r = client.post("/login", json={"username": "u" * 500, "password": "x"})
    assert r.status_code == 422
    assert _login_failed_lines(settings)[-1]["user"] == "u" * 64


def test_login_422_missing_username_logged_as_dash(client, settings):
    r = client.post("/login", json={"password": "hunter2-zz"})
    assert r.status_code == 422
    assert _login_failed_lines(settings)[-1]["user"] == "-"
    assert "hunter2-zz" not in _log_text(settings)


def test_other_422s_do_not_log_login_failed(client, settings):
    client.post("/orders", json={"product_id": 0, "quantity": 1})
    client.get("/search")
    assert _login_failed_lines(settings) == []
