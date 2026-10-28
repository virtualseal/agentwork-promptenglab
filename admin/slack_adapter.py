"""Separate protected Slack broker. No generic Slack forwarding; inactive by default."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import http.client
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import time
import urllib.parse
from app.broker_slack import CHANNEL, KEY

EVENT = 'thursday_restaurants_delivery'


class ProviderFailure(Exception):
    def __init__(self, kind='unknown', wait=600):
        self.kind, self.wait = kind, wait
        super().__init__('Slack provider request failed')


class SlackHTTPS:
    """Only administrator process receives the token. Never log requests/errors."""
    def __init__(self, token):
        self.token = token

    def __call__(self, method, payload, timeout=10):
        if method not in ('auth.test', 'chat.postMessage', 'conversations.history'):
            raise ProviderFailure('rejected')
        url = '/api/'+method
        headers = {'Authorization': 'Bearer '+self.token, 'Content-Type': 'application/json'}
        body = None
        if method == 'conversations.history':
            url += '?'+urllib.parse.urlencode(payload)
        else:
            body = json.dumps(payload).encode()
        connection, timer = None, None
        try:
            connection = http.client.HTTPSConnection('slack.com', timeout=timeout/2)
            connection.connect()
            # Socket timeout alone does not bound a slow trickle of response bytes.
            sock = connection.sock
            def expire():
                try: sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            timer = threading.Timer(timeout/2, expire)
            timer.daemon = True
            timer.start()
            connection.request('GET' if method == 'conversations.history' else 'POST', url, body, headers)
            response = connection.getresponse()
            if response.status == 429:
                try: wait = max(600, min(86400, int(response.getheader('Retry-After', '600'))))
                except (ValueError, TypeError): wait = 86400
                raise ProviderFailure('retry', wait)
            if response.status != 200: raise ProviderFailure()
            data = response.read(262145)
            # A bounded read can return valid JSON on premature EOF without
            # raising IncompleteRead. Require all declared bytes before parsing.
            if response.length not in (None, 0): raise ProviderFailure()
            if len(data) > 262144: raise ProviderFailure()
            result = json.loads(data)
        except ProviderFailure:
            raise
        except Exception:
            raise ProviderFailure() from None
        finally:
            if timer: timer.cancel()
            if connection: connection.close()
        if not isinstance(result, dict) or type(result.get('ok')) is not bool:
            raise ProviderFailure()
        if result['ok'] is False:
            code = result.get('error')
            if code == 'ratelimited': raise ProviderFailure('retry')
            if code in ('invalid_auth', 'token_revoked', 'missing_scope', 'not_in_channel', 'channel_not_found', 'is_archived'):
                raise ProviderFailure('rejected')
            raise ProviderFailure()
        return result


class SlackAdapter:
    def __init__(self, state, workspace, bot_user, provider, enabled=False, clock=time.time):
        if not re.fullmatch(r'T[A-Z0-9]+', workspace) or not re.fullmatch(r'U[A-Z0-9]+', bot_user):
            raise ValueError('Workspace and bot identity required')
        self.state = Path(state)
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.workspace, self.bot_user, self.provider = workspace, bot_user, provider
        self.enabled, self.clock = enabled, clock
        with self._locked() as db:
            db.execute('CREATE TABLE IF NOT EXISTS deliveries (key TEXT PRIMARY KEY, digest TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL, next_at REAL NOT NULL, message_id TEXT)')
            db.commit()

    @contextmanager
    def _locked(self):
        with open(str(self.state)+'.lock', 'a') as lock:
            deadline = time.monotonic()+30
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline: raise ProviderFailure()
                    time.sleep(0.05)
            db = sqlite3.connect(self.state)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA synchronous=FULL')
            try: yield db
            finally:
                db.close()
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _history(self, key):
        """Require complete traversal even if a match appears on an early page."""
        deadline = time.monotonic()+25
        cursor, seen, matches = '', set(), []
        total = 0
        for _ in range(100):
            remaining = deadline-time.monotonic()
            if remaining <= 0: return ('unknown', None)
            page = self.provider('conversations.history', dict(channel=CHANNEL, limit=15,
                include_all_metadata='true', cursor=cursor), timeout=min(10, remaining))
            total += len(json.dumps(page).encode())
            if total > 2*1024*1024 or page.get('ok') is not True: return ('unknown', None)
            messages, metadata = page.get('messages'), page.get('response_metadata')
            if (not isinstance(messages, list) or type(page.get('has_more')) is not bool or
                    not isinstance(metadata, dict) or not isinstance(metadata.get('next_cursor'), str)):
                return ('unknown', None)
            if page.get('is_limited') or page.get('warning') or page.get('warnings'):
                return ('unknown', None)
            for message in messages:
                if not isinstance(message, dict): return ('unknown', None)
                if message.get('user') == self.bot_user and 'metadata' not in message:
                    return ('unknown', None)
                info = message.get('metadata', {})
                if not isinstance(info, dict): return ('unknown', None)
                if info.get('event_type') != EVENT: continue
                payload = info.get('event_payload')
                if not isinstance(payload, dict): return ('unknown', None)
                if payload.get('delivery_key') != key: continue
                ts = message.get('ts')
                if (message.get('user') != self.bot_user or message.get('team') != self.workspace or
                        not isinstance(ts, str) or not re.fullmatch(r'[0-9]+\.[0-9]+', ts)):
                    return ('unknown', None)
                matches.append(ts)
            next_cursor = metadata['next_cursor']
            if not next_cursor:
                if page['has_more']: return ('unknown', None)
                return ('present', matches[0]) if len(matches) == 1 else ('unknown' if matches else 'absent', None)
            if not page['has_more'] or next_cursor in seen: return ('unknown', None)
            seen.add(next_cursor)
            cursor = next_cursor
        return ('unknown', None)

    def handle(self, request):
        # Strict closed protocol: never accept URL, token, method, workspace, or arbitrary provider fields.
        if not isinstance(request, dict): raise ValueError('Invalid scoped request')
        operation = request.get('operation')
        fields = {'version', 'operation', 'channel', 'delivery_key'} | ({'text'} if operation == 'deliver' else set())
        key = request.get('delivery_key')
        if (set(request) != fields or request.get('version') != 1 or operation not in ('lookup', 'deliver') or
                request.get('channel') != CHANNEL or not isinstance(key, str) or not KEY.fullmatch(key)):
            raise ValueError('Invalid scoped request')
        text = request.get('text')
        if operation == 'deliver' and (not isinstance(text, str) or not 1 <= len(text.encode()) <= 12000):
            raise ValueError('Invalid scoped message')
        def result(state, message=None):
            return dict(version=1, workspace=self.workspace, channel=CHANNEL, state=state, message_id=message)
        with self._locked() as db:
            row = db.execute('SELECT * FROM deliveries WHERE key=?', (key,)).fetchone()
            digest = hashlib.sha256(text.encode()).hexdigest() if text is not None else None
            if row and digest and digest != row['digest']: return result('rejected')
            try:
                identity = self.provider('auth.test', {}, timeout=10)
                if identity.get('ok') is not True or identity.get('team_id') != self.workspace or identity.get('user_id') != self.bot_user:
                    return result('unknown')
                state, message = self._history(key)
            except Exception:
                return result('unknown')
            if state == 'present':
                if row:
                    db.execute('UPDATE deliveries SET status=?, message_id=? WHERE key=?', ('sent', message, key)); db.commit()
                return result(state, message)
            # A crash/timeout after durable intent can never be turned into permission to post.
            if state != 'absent' or (row and row['status'] in ('sending', 'sent')):
                return result('unknown')
            if operation == 'lookup': return result('absent')
            if not self.enabled: return result('rejected')
            if row and (row['attempts'] >= 3 or row['status'] == 'rejected'): return result('rejected')
            if row and self.clock() < row['next_at']: return result('retry')
            attempts = row['attempts']+1 if row else 1
            db.execute('INSERT OR REPLACE INTO deliveries VALUES (?,?,?,?,?,NULL)',
                (key, digest, 'sending', attempts, self.clock()+600)); db.commit()
            try:
                ack = self.provider('chat.postMessage', dict(channel=CHANNEL, text=text,
                    unfurl_links=False, unfurl_media=False,
                    metadata=dict(event_type=EVENT, event_payload=dict(delivery_key=key))), timeout=10)
                ts, msg = ack.get('ts'), ack.get('message')
                if (ack.get('ok') is not True or ack.get('channel') != CHANNEL or not isinstance(ts, str) or
                        not re.fullmatch(r'[0-9]+\.[0-9]+', ts) or not isinstance(msg, dict) or
                        msg.get('team') != self.workspace or msg.get('user') != self.bot_user or
                        msg.get('ts') != ts or msg.get('metadata') != dict(
                            event_type=EVENT, event_payload=dict(delivery_key=key))):
                    return result('unknown')
            except ProviderFailure as error:
                # Only explicit rejection or rate-limit responses establish no write occurred.
                if error.kind in ('retry', 'rejected'):
                    db.execute('UPDATE deliveries SET status=?, next_at=? WHERE key=?',
                        (error.kind, self.clock()+error.wait, key)); db.commit()
                    return result(error.kind)
                return result('unknown')
            except Exception:
                return result('unknown')
            db.execute('UPDATE deliveries SET status=?, message_id=? WHERE key=?', ('sent', ts, key)); db.commit()
            return result('present', ts)


def dispatch(adapter, capability_sha256, path, authorization, raw):
    if (not isinstance(capability_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', capability_sha256) or
            path != '/v1/slack' or not authorization.startswith('Bearer ') or
            not hmac.compare_digest(hashlib.sha256(authorization[7:].encode()).hexdigest(), capability_sha256)):
        raise ValueError('Scoped authentication required')
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 16384:
        raise ValueError('Invalid request size')
    return adapter.handle(json.loads(raw))


class DeadlineHTTPServer(HTTPServer):
    """Accept plain sockets, then bound TLS and the complete HTTP exchange."""
    handshake_timeout = 5
    request_timeout = 80

    def __init__(self, address, handler, context):
        self.context = context
        self.deadline_timer = None
        super().__init__(address, handler)

    def get_request(self):
        raw, address = super().get_request()
        connection = raw
        try:
            raw.settimeout(self.handshake_timeout)
            connection = self.context.wrap_socket(raw, server_side=True,
                                                   do_handshake_on_connect=False)
            def expire():
                try: connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            self.deadline_timer = threading.Timer(self.request_timeout, expire)
            self.deadline_timer.daemon = True
            self.deadline_timer.start()
            connection.do_handshake()
            return connection, address
        except Exception:
            if self.deadline_timer:
                self.deadline_timer.cancel()
            connection.close()
            raise

    def shutdown_request(self, request):
        if self.deadline_timer:
            self.deadline_timer.cancel()
        super().shutdown_request(request)

    def handle_error(self, request, client_address):
        # Transport errors must not emit request details or authentication headers.
        pass


def create_server(adapter, capability_sha256, address, certificate, private_key):
    if not re.fullmatch(r'[a-f0-9]{64}', capability_sha256): raise ValueError('Capability digest required')
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)
            self.input_deadline = time.monotonic() + 5
            def expire_input():
                try: self.connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            self.input_timer = threading.Timer(5, expire_input)
            self.input_timer.daemon = True
            self.input_timer.start()
        def finish(self):
            try:
                super().finish()
            finally:
                self.input_timer.cancel()
        def log_message(self, *args): pass
        def do_POST(self):
            try:
                auth = self.headers.get('Authorization', '')
                valid = auth.startswith('Bearer ') and hmac.compare_digest(
                    hashlib.sha256(auth[7:].encode()).hexdigest(), capability_sha256)
                if not valid or self.path != '/v1/slack':
                    self.send_error(403); return
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384 or self.headers.get('Transfer-Encoding'):
                    self.send_error(400); return
                raw = self.rfile.read(length)
                if len(raw) != length or time.monotonic() >= self.input_deadline:
                    raise ValueError()
                self.input_timer.cancel()
                body = json.dumps(dispatch(adapter, capability_sha256, self.path, auth, raw)).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
            except Exception:
                self.send_error(400, 'Scoped request failed')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, private_key)
    return DeadlineHTTPServer(address, Handler, context)


def serve(adapter, capability_sha256, address, certificate, private_key):
    with create_server(adapter, capability_sha256, address, certificate, private_key) as server:
        server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-writes', action='store_true')
    args = parser.parse_args()
    adapter = SlackAdapter(os.environ['SLACK_BROKER_STATE'], os.environ['SLACK_WORKSPACE_ID'],
        os.environ['SLACK_BOT_USER_ID'], SlackHTTPS(os.environ['SLACK_BOT_TOKEN']), args.enable_writes)
    serve(adapter, os.environ['SLACK_CAPABILITY_SHA256'], ('0.0.0.0', int(os.environ.get('SLACK_BROKER_PORT', '8443'))),
        os.environ['SLACK_TLS_CERT'], os.environ['SLACK_TLS_KEY'])


if __name__ == '__main__': main()
