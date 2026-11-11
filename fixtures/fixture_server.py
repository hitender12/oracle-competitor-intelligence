"""Local fixture server for the demo, tests, and benchmark.

Serves fixture pages that intentionally change between versions, plus
test endpoints: redirect chains, a redirect loop, a slow endpoint, a
flaky endpoint (500 twice, then 200), and malformed HTML.

Only ever run on localhost. These fixtures are the only sites the demo
monitors; no real competitor site is fetched.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIXTURES = Path(__file__).parent

# version flag per page: {"acme": 1, "beta": 1}
VERSIONS = {"acme": 1, "beta": 1}

_flaky_hits = {"count": 0}


class FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep test output clean
        pass

    def _send(self, body: bytes, status: int = 200, ctype: str = "text/html"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _fixture(self, name: str) -> bytes:
        version = VERSIONS[name]
        return (FIXTURES / f"{name}_v{version}.html").read_bytes()

    def do_GET(self):
        path = self.path
        if path == "/acme/pricing":
            self._send(self._fixture("acme"))
        elif path == "/beta/products":
            self._send(self._fixture("beta"))
        elif path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/redirect/2")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/redirect/2":
            self.send_response(302)
            self.send_header("Location", "/redirect/3")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/redirect/3":
            self._send(b"<html><head><title>Final</title></head>"
                       b"<body><h1>Arrived</h1></body></html>")
        elif path == "/redirect-loop":
            self.send_response(302)
            self.send_header("Location", "/redirect-loop")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/slow":
            time.sleep(2.0)
            self._send(b"<html><body><h1>Slow page</h1></body></html>")
        elif path == "/flaky":
            _flaky_hits["count"] += 1
            if _flaky_hits["count"] <= 2:
                self._send(b"boom", status=500, ctype="text/plain")
            else:
                self._send(b"<html><body><h1>Recovered</h1></body></html>")
        elif path == "/bad":
            self._send(
                b"<html><head><title>Broken<title><body><h1>Unclosed"
                b"<p>no closing tags <span class=price>$9"
            )
        elif path == "/empty":
            self._send(b"", status=200)
        else:
            self._send(b"not found", status=404, ctype="text/plain")


def start_fixture_server(port: int = 0):
    """Start the fixture server on localhost; returns (server, base_url)."""
    server = ThreadingHTTPServer(("127.0.0.1", port), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def set_version(name: str, version: int) -> None:
    VERSIONS[name] = version


if __name__ == "__main__":
    server, base = start_fixture_server(8901)
    print(f"fixture server on {base} (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()
