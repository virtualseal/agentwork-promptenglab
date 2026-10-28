"""Inactive packaging entry point: one guarded worker and process health.

Readiness intentionally stays blocked until the live Maps/Slack milestone wires
and verifies authoritative readiness. Health never asserts message delivery.
"""
import os
if os.getuid() != 502:
    raise SystemExit('Thursday Restaurants requires agentwork UID 502')

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import signal
import socket
import subprocess
import threading


REQUEST_DEADLINE_SECONDS = 2


class HealthServer(HTTPServer):
    """Bound the whole accepted connection, including trickled HTTP headers."""
    def finish_request(self, request, client_address):
        def expire():
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        request.settimeout(REQUEST_DEADLINE_SECONDS)
        deadline = threading.Timer(REQUEST_DEADLINE_SECONDS, expire)
        deadline.daemon = True
        deadline.start()
        try:
            super().finish_request(request, client_address)
        finally:
            deadline.cancel()
            # Do not let a timer still using this socket outlive its handler.
            deadline.join()


def main():
    root = Path(__file__).resolve().parent.parent
    config = os.environ['THURSDAY_CONFIG']
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/healthz':
                status = 200 if worker.poll() is None else 503
                body = b'process alive\n' if status == 200 else b'worker stopped\n'
            elif self.path == '/readyz':
                status, body = 503, b'live Maps/Slack activation and delivery gates incomplete\n'
            else:
                status, body = 404, b'not found\n'
            self.send_response(status)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args): pass
    server = None
    def stopped(signum, frame): raise KeyboardInterrupt
    worker = subprocess.Popen([str(root / 'run'), 'watch', '--config', config], cwd=str(root))
    try:
        signal.signal(signal.SIGTERM, stopped)
        server = HealthServer(('0.0.0.0', int(os.environ.get('PORT', '8080'))), Handler)
        server.timeout = 0.5
        while worker.poll() is None:
            server.handle_request()
        raise SystemExit('Thursday Restaurants worker exited unexpectedly')
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.server_close()
        if worker.poll() is None:
            worker.terminate()
        try: worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()


if __name__ == '__main__': main()
