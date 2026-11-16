import json

REQUIRED = {"timestamp", "level", "service", "message", "trace_id", "client_ip",
            "method", "path", "status", "duration_ms"}


def _lines(settings):
    with open(settings.log_file) as f:
        return [json.loads(line) for line in f if line.strip()]


def _access(settings, path):
    return [l for l in _lines(settings) if l["message"] == "request" and l["path"] == path]


def test_access_line_has_all_contract_fields(client, settings):
    client.get("/products?x=1", headers={"X-Real-IP": "203.0.113.7"})
    line = _access(settings, "/products")[-1]
    assert REQUIRED <= line.keys()
    assert line["service"] == "catalog-api"
    assert line["level"] == "INFO"
    assert line["client_ip"] == "203.0.113.7"
    assert line["path"] == "/products"  # query string stripped
    assert line["status"] == 200
    assert line["timestamp"].endswith("Z")


def test_incoming_trace_id_is_echoed_and_logged(client, settings):
    tid = "0123456789abcdef0123456789abcdef"
    r = client.get("/products", headers={"X-Trace-Id": tid})
    assert r.headers["X-Trace-Id"] == tid
    assert _access(settings, "/products")[-1]["trace_id"] == tid


def test_missing_or_bad_trace_id_gets_new_uuid_hex(client):
    r1 = client.get("/products")
    r2 = client.get("/products", headers={"X-Trace-Id": "bad id\nwith newline"})
    for r in (r1, r2):
        tid = r.headers["X-Trace-Id"]
        assert len(tid) == 32 and int(tid, 16) >= 0


def test_probe_paths_logged_at_debug(client, settings):
    client.get("/healthz")
    client.get("/metrics")
    assert _access(settings, "/healthz")[-1]["level"] == "DEBUG"
    assert _access(settings, "/metrics")[-1]["level"] == "DEBUG"


def test_5xx_logged_at_error(client, settings, store):
    store.fail = True
    client.get("/products")
    assert _access(settings, "/products")[-1]["level"] == "ERROR"


def test_every_line_is_valid_json(client, settings):
    import logging
    client.get("/products")
    client.get("/nope")
    # Library loggers must also come out as JSON, not plain text.
    logging.getLogger("psycopg.pool").warning("error connecting in 'pool-1'")
    logging.getLogger("uvicorn.error").info("Started server process")
    with open(settings.log_file) as f:
        for line in f:
            json.loads(line)
