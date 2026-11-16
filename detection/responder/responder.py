import ipaddress
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TTL = int(os.environ.get("BLOCK_TTL_SECONDS", "600"))
ALLOWLIST_PATH = os.environ.get("ALLOWLIST_PATH", "/config/allowlist.txt")
REPUTATION_PATH = os.environ.get("REPUTATION_PATH", "/config/reputation.json")
BLOCKLIST_PATH = os.environ.get("BLOCKLIST_PATH", "/etc/nginx/blocklist/blocklist.conf")
DATA_DIR = os.environ.get("DATA_DIR", "/data")
EDGE_URL = os.environ.get("EDGE_URL", "http://edge:8080")
PROBE_URL = os.environ.get("ATTACKER_PROBE_URL", "http://attacker:9000/probe")
ATTACKER_IP = os.environ.get("ATTACKER_IP", "172.30.0.50")

lock = threading.Lock()
blocks = {}


def now():
    return datetime.now(timezone.utc)


def audit(decision, ip, alert, **extra):
    entry = {"ts": now().isoformat(), "decision": decision, "ip": ip,
             "rule": alert.get("rule"), "mitre": alert.get("mitre"),
             "owasp": alert.get("owasp"), **extra}
    with open(os.path.join(DATA_DIR, "audit.jsonl"), "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(json.dumps(entry), flush=True)


def normalize(p):
    if "source_ip" in p:
        return {"ip": p["source_ip"], "rule": p.get("rule", ""), "mitre": p.get("mitre", ""),
                "owasp": p.get("owasp", ""), "severity": p.get("severity", ""),
                "path": p.get("path", "")}
    rule = p.get("rule", {})
    data = p.get("data", {})
    groups = rule.get("groups", [])
    return {"ip": data.get("remote_addr"),
            "rule": rule.get("description", "").split(":")[0],
            "mitre": ",".join(rule.get("mitre", {}).get("id", [])),
            "owasp": next((g for g in groups if g.startswith("owasp_")), ""),
            "severity": rule.get("level"),
            "path": data.get("uri", "")}


def load_allowlist():
    nets = []
    with open(ALLOWLIST_PATH) as f:
        for line in f:
            entry = line.split("#")[0].strip()
            if entry:
                nets.append(ipaddress.ip_network(entry, strict=False))
    return nets


def lookup_reputation(ip):
    with open(REPUTATION_PATH) as f:
        entries = json.load(f)
    for key, info in entries.items():
        if ip in ipaddress.ip_network(key, strict=False):
            return info
    return {"score": 0, "label": "unknown"}


def load_blocks():
    try:
        with open(BLOCKLIST_PATH) as f:
            for line in f:
                m = re.match(r"deny (\S+); # expires=(\d+) rule=(\S*)", line)
                if m:
                    blocks[m[1]] = {"expires": int(m[2]), "rule": m[3]}
    except FileNotFoundError:
        pass


def write_blocklist():
    lines = [f"deny {ip}; # expires={int(info['expires'])} rule={info['rule']}\n"
             for ip, info in blocks.items()]
    tmp = BLOCKLIST_PATH + ".tmp"
    with open(tmp, "w") as f:
        f.writelines(lines)
    os.replace(tmp, BLOCKLIST_PATH)


def fetch_status(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


def probe_attacker():
    try:
        with urllib.request.urlopen(PROBE_URL + "?path=/api/products", timeout=5) as r:
            return json.load(r)["status"]
    except (OSError, ValueError, KeyError):
        return 0


def verify(ip):
    result = {"normal_status": 0}
    for _ in range(6):
        time.sleep(0.5)
        result["normal_status"] = fetch_status(EDGE_URL + "/api/products")
        if ip == ATTACKER_IP:
            result["attacker_status"] = probe_attacker()
            if result["attacker_status"] == 403:
                break
        elif result["normal_status"] == 200:
            break
    return result


def write_case(alert, ip, reputation, verified, received):
    created = now()
    case_id = f"case-{created:%Y%m%dT%H%M%SZ}-{ip.replace(':', '_')}"
    case = {"case_id": case_id, "created": created.isoformat(), "severity": alert["severity"],
            "source_ip": ip,
            "rule": {"name": alert["rule"], "mitre": alert["mitre"], "owasp": alert["owasp"]},
            "observables": [{"type": "ip", "value": ip}, {"type": "path", "value": alert["path"]}],
            "enrichment": reputation,
            "timeline": [{"ts": received.isoformat(), "event": "alert received"},
                         {"ts": created.isoformat(), "event": "blocked and verified"}],
            "action": {"type": "block", "ttl": TTL, "verified": verified}}
    os.makedirs(os.path.join(DATA_DIR, "cases"), exist_ok=True)
    with open(os.path.join(DATA_DIR, "cases", case_id + ".json"), "w") as f:
        json.dump(case, f, indent=2)
    return case_id


def handle_alert(payload):
    alert = normalize(payload)
    received = now()
    try:
        ip = ipaddress.ip_address(alert["ip"])
    except (ValueError, TypeError):
        audit("error", str(alert.get("ip")), alert, reason="invalid source ip")
        return 400, {"decision": "error", "reason": "invalid source ip"}
    key = str(ip)
    if any(ip in net for net in load_allowlist()):
        audit("skipped_allowlisted", key, alert, reason="source is allowlisted")
        return 200, {"decision": "skipped_allowlisted"}
    reputation = lookup_reputation(ip)
    with lock:
        if key in blocks and blocks[key]["expires"] > time.time():
            audit("duplicate_ignored", key, alert, reason="already blocked")
            return 200, {"decision": "duplicate_ignored"}
        blocks[key] = {"expires": time.time() + TTL, "rule": alert["rule"],
                       "mitre": alert["mitre"], "owasp": alert["owasp"]}
        write_blocklist()
    verified = verify(key)
    case_id = write_case(alert, key, reputation, verified, received)
    audit("blocked", key, alert, ttl=TTL, case_id=case_id, reason="rule fired", verified=verified)
    return 200, {"decision": "blocked", "case_id": case_id}


def expire_loop():
    while True:
        time.sleep(5)
        with lock:
            expired = [ip for ip, info in blocks.items() if info["expires"] <= time.time()]
            for ip in expired:
                info = blocks.pop(ip)
                audit("expired", ip, {"rule": info["rule"], "mitre": info.get("mitre"),
                                  "owasp": info.get("owasp")}, reason="ttl reached")
            if expired:
                write_blocklist()


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            self.reply(200, {"status": "ok"})
        elif self.path == "/blocks":
            with lock:
                self.reply(200, dict(blocks))
        else:
            self.reply(404, {"detail": "not found"})

    def do_POST(self):
        if self.path != "/alert":
            self.reply(404, {"detail": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            status, body = handle_alert(json.loads(self.rfile.read(length)))
        except Exception as exc:
            audit("error", "unknown", {}, reason=str(exc))
            status, body = 500, {"decision": "error"}
        self.reply(status, body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    load_blocks()
    threading.Thread(target=expire_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8088), Handler).serve_forever()
