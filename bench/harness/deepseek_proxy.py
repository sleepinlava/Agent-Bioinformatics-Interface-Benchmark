#!/usr/bin/env python3
"""Tiny reverse proxy that injects the correct Authorization header.

OpenCode v1.17.6 auto-detects DeepSeek and puts the API key in the
request *body* instead of the ``Authorization: Bearer`` header.
DeepSeek rejects that with ``Authentication Fails``.

This proxy listens on 127.0.0.1:18900, strips any ``apiKey`` from the
JSON body, injects the proper ``Authorization`` header, and forwards
everything else to https://api.deepseek.com.
"""

import http.server
import json
import os
import ssl
import sys
import urllib.request

DEEPSEEK_BASE = "https://api.deepseek.com"
API_KEY = os.environ.get(
    "ABI_BENCH_API_KEY", "sk-14c5273d9dd64f81b2f6f71542948f2f"
)
LISTEN = ("127.0.0.1", 18900)
TIMEOUT = 300  # seconds


class Proxy(http.server.BaseHTTPRequestHandler):
    def _forward(self, method: str) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        # Strip apiKey from JSON body (OpenCode puts it there for native deepseek)
        if body:
            try:
                data = json.loads(body)
                data.pop("apiKey", None)
                body = json.dumps(data).encode()
            except (json.JSONDecodeError, TypeError):
                pass

        url = DEEPSEEK_BASE + self.path
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {API_KEY}")

        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp.read())
        except urllib.error.HTTPError as exc:
            self.send_response(exc.code)
            self.end_headers()
            self.wfile.write(exc.read())
        except Exception as exc:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(exc).encode())

    def do_POST(self) -> None: self._forward("POST")
    def do_GET(self) -> None:  self._forward("GET")

    def log_message(self, fmt, *args):
        print(f"  [proxy] {args[0]}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    print(f"DeepSeek auth proxy listening on http://{LISTEN[0]}:{LISTEN[1]}",
          file=sys.stderr, flush=True)
    srv = http.server.HTTPServer(LISTEN, Proxy)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
