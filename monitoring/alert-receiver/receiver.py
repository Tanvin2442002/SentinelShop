import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            alerts = json.loads(self.rfile.read(length)).get("alerts", [])
        except (ValueError, AttributeError):
            self.send_response(400)
            self.end_headers()
            return
        for alert in alerts:
            labels = alert.get("labels", {})
            print(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "ERROR" if labels.get("severity") == "critical" else "WARNING",
                "service": "alert-receiver",
                "message": "alert " + alert.get("status", "unknown"),
                "alertname": labels.get("alertname"),
                "severity": labels.get("severity"),
                "route": labels.get("route"),
                "container": labels.get("name"),
                "runbook_url": alert.get("annotations", {}).get("runbook_url"),
            }), flush=True)
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
