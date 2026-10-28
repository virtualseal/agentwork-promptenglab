"""Mocked provider and cloud protocol regressions. No live Slack requests."""
import json
import hashlib
import http.client
import io
import socket
import subprocess
import ssl
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
from admin.slack_adapter import SlackAdapter, SlackHTTPS, ProviderFailure, EVENT, dispatch, create_server
from app.broker_slack import BrokerSlack, CHANNEL
from app.sources import TemporaryFailure, UncertainDelivery, RejectedDelivery

KEY = 'weekly-key'


def message(key=KEY):
    return dict(ts='123.456', user='UBOT', team='TTEAM', metadata=dict(
        event_type=EVENT, event_payload=dict(delivery_key=key)))


def page(messages=None, cursor='', more=False):
    return dict(ok=True, messages=messages or [], has_more=more,
                response_metadata=dict(next_cursor=cursor))


class Provider:
    def __init__(self):
        self.posts = 0
        self.messages = []
        self.pages = None
        self.failure = None
        self.identity = dict(ok=True, team_id='TTEAM', user_id='UBOT')
        self.ack = None
    def __call__(self, method, payload, timeout=10):
        if method == 'auth.test': return self.identity
        if method == 'conversations.history':
            if self.pages is not None: return self.pages.pop(0)
            return page(self.messages)
        self.posts += 1
        if self.failure == 'rate': raise ProviderFailure('retry', 1200)
        if self.failure == 'reject': raise ProviderFailure('rejected')
        if self.failure == 'crash': raise SystemExit()
        self.messages.append(message())
        if self.failure == 'lost': raise TimeoutError('secret must not escape')
        return self.ack or dict(ok=True, channel=CHANNEL, ts='123.456', message=message())


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.state = str(Path(self.tmp.name)/'broker.db')
        self.provider = Provider()
        self.now = 0
        self.adapter = self.restart()
    def restart(self, enabled=True):
        return SlackAdapter(self.state, 'TTEAM', 'UBOT', self.provider, enabled, lambda:self.now)
    def call(self, op='deliver', **changes):
        data = dict(version=1, operation=op, channel=CHANNEL, delivery_key=KEY)
        if op == 'deliver': data['text'] = 'Dinner'
        data.update(changes)
        return self.adapter.handle(data)
    def test_ack_restart_and_concurrent_delivery(self):
        results = []
        def deliver(): results.append(self.call())
        threads = [threading.Thread(target=deliver) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual([r['state'] for r in results], ['present']*4)
        self.adapter = self.restart()
        self.assertEqual(self.call()['state'], 'present')
        self.assertEqual(self.provider.posts, 1)
    def test_lost_ack_reconciles_after_restart(self):
        self.provider.failure = 'lost'
        self.assertEqual(self.call()['state'], 'unknown')
        self.adapter = self.restart()
        self.assertEqual(self.call()['state'], 'present')
        self.assertEqual(self.provider.posts, 1)
    def test_crash_intent_and_empty_history_never_retry(self):
        self.provider.failure = 'crash'
        with self.assertRaises(SystemExit): self.call()
        self.adapter = self.restart()
        self.provider.failure = None; self.now = 10000
        self.assertEqual(self.call()['state'], 'unknown')
        self.assertEqual(self.call('lookup')['state'], 'unknown')
        self.assertEqual(self.provider.posts, 1)
    def test_budget_and_retry_after_persist_across_restart(self):
        self.provider.failure = 'rate'
        for attempt in range(3):
            self.now = attempt*1200
            self.adapter = self.restart()
            self.assertEqual(self.call()['state'], 'retry')
            self.now += 601
            self.assertEqual(self.call()['state'], 'retry' if attempt < 2 else 'rejected')
            self.assertEqual(self.provider.posts, attempt+1)
        self.now = 99999
        self.assertEqual(self.call()['state'], 'rejected')
        self.assertEqual(self.provider.posts, 3)
    def test_scope_identity_text_and_disabled(self):
        with self.assertRaises(ValueError): self.call(channel='COTHER')
        with self.assertRaises(ValueError): self.call(token='forbidden')
        self.provider.identity['team_id'] = 'TOTHER'
        self.assertEqual(self.call()['state'], 'unknown')
        self.provider.identity['team_id'] = 'TTEAM'
        self.adapter = self.restart(False)
        self.assertEqual(self.call()['state'], 'rejected')
        self.assertEqual(self.provider.posts, 0)
    def test_changed_message_rejected(self):
        self.call()
        self.assertEqual(self.call(text='Different')['state'], 'rejected')
        self.assertEqual(self.provider.posts, 1)
    def test_malformed_and_wrong_channel_ack_remain_unknown(self):
        for ack in (dict(ok=False), dict(ok=True, channel='COTHER', ts='123.456', message=message()),
                    dict(ok=True, channel=CHANNEL, ts='bad', message=message()),
                    dict(ok=True, channel=CHANNEL, ts='123.456', message=dict(team='TOTHER', user='UBOT'))):
            with self.subTest(ack=ack):
                with tempfile.TemporaryDirectory() as directory:
                    provider = Provider(); provider.ack = ack
                    adapter = SlackAdapter(Path(directory)/'db', 'TTEAM', 'UBOT', provider, True)
                    request = dict(version=1, operation='deliver', channel=CHANNEL, delivery_key=KEY, text='Dinner')
                    self.assertEqual(adapter.handle(request)['state'], 'unknown')
                    provider.messages = []
                    self.assertEqual(adapter.handle(request)['state'], 'unknown')
                    self.assertEqual(provider.posts, 1)
    def test_complete_pagination_required_even_after_match(self):
        self.provider.pages = [page([message()], 'next', True), page()]
        self.assertEqual(self.call('lookup')['state'], 'present')
        for pages in ([page([message()], 'next', True), dict(ok=False)],
                      [dict(ok=True, messages=[])], [page([], '', True)],
                      [page([message(), message()])],
                      [dict(page(), is_limited=True)],
                      [page([], 'same', True), page([], 'same', True)]):
            self.provider.pages = pages
            self.assertEqual(self.call('lookup')['state'], 'unknown')
        self.assertEqual(self.provider.posts, 0)
    def test_wrong_workspace_history_and_missing_metadata_fields(self):
        bad = message(); bad['team'] = 'TOTHER'
        self.provider.pages = [page([bad])]
        self.assertEqual(self.call('lookup')['state'], 'unknown')
        self.provider.pages = [page()]
        self.assertEqual(self.call('lookup')['state'], 'absent')
    def test_rejection_is_terminal(self):
        self.provider.failure = 'reject'
        self.assertEqual(self.call()['state'], 'rejected')
        self.adapter = self.restart(); self.now = 10000
        self.assertEqual(self.call()['state'], 'rejected')
        self.assertEqual(self.provider.posts, 1)
    def test_app_port_only_returns_results_and_sanitizes(self):
        client = BrokerSlack('https://broker.example/v1/slack', 'a'*43, 'TTEAM', self.adapter.handle)
        self.assertEqual(client.lookup(CHANNEL, KEY).state, 'absent')
        self.assertEqual(client.post(CHANNEL, 'Dinner', KEY), '123.456')
        client.transport = lambda payload: dict(version=1, workspace='TOTHER', channel=CHANNEL, state='absent')
        self.assertEqual(client.lookup(CHANNEL, KEY).state, 'unknown')
        with self.assertRaises(UncertainDelivery): client.post(CHANNEL, 'Dinner', KEY)
        for state, error in [('retry', TemporaryFailure), ('rejected', RejectedDelivery), ('unknown', UncertainDelivery)]:
            client.transport = lambda payload, state=state: dict(version=1, workspace='TTEAM', channel=CHANNEL, state=state)
            with self.assertRaises(error): client.post(CHANNEL, 'Dinner', KEY)
        def fail(payload): raise RuntimeError('private-token')
        client.transport = fail
        with self.assertRaises(UncertainDelivery) as raised: client.post(CHANNEL, 'Dinner', KEY)
        self.assertNotIn('private-token', str(raised.exception))
        with self.assertRaises(ValueError): BrokerSlack('http://broker/v1/slack', 'a'*43, 'TTEAM')


class HTTPSProviderTests(unittest.TestCase):
    def test_premature_eof_valid_json_is_unknown_on_both_transports(self):
        class WireSocket:
            def __init__(self, wire): self.wire = wire
            def makefile(self, *args): return io.BytesIO(self.wire)
            def shutdown(self, *args): pass
        class Connection:
            def __init__(self, wire): self.sock = WireSocket(wire)
            def connect(self): pass
            def request(self, *args): pass
            def getresponse(self):
                response = http.client.HTTPResponse(self.sock)
                response.begin()
                return response
            def close(self): pass

        history = dict(ok=True, messages=[], has_more=False,
                       response_metadata=dict(next_cursor=''))
        broker = dict(version=1, channel=CHANNEL, workspace='TTEAM', state='absent')
        for framing in ('complete', 'short-length', 'missing-chunk-end'):
            def connection_for(body):
                data = json.dumps(body).encode()
                if framing == 'missing-chunk-end':
                    wire = (b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n'
                            + format(len(data), 'x').encode() + b'\r\n' + data + b'\r\n')
                else:
                    length = len(data) + (100 if framing == 'short-length' else 0)
                    wire = (b'HTTP/1.1 200 OK\r\nContent-Length: '
                            + str(length).encode() + b'\r\n\r\n' + data)
                return Connection(wire)
            with self.subTest(framing=framing):
                with patch('admin.slack_adapter.http.client.HTTPSConnection',
                           side_effect=lambda *a, **kw: connection_for(history)):
                    provider = SlackHTTPS('mock-token')
                    if framing == 'complete':
                        self.assertEqual(provider('conversations.history', {}), history)
                    else:
                        with self.assertRaises(ProviderFailure) as raised:
                            provider('conversations.history', {})
                        self.assertEqual(raised.exception.kind, 'unknown')
                        with tempfile.TemporaryDirectory() as directory:
                            calls = []
                            def scoped_provider(method, payload, **kwargs):
                                calls.append(method)
                                if method == 'auth.test':
                                    return dict(ok=True, team_id='TTEAM', user_id='UBOT')
                                return provider(method, payload, **kwargs)
                            adapter = SlackAdapter(Path(directory)/'state.db', 'TTEAM',
                                                   'UBOT', scoped_provider, enabled=True)
                            self.assertEqual(adapter.handle(dict(version=1, operation='deliver',
                                channel=CHANNEL, delivery_key=KEY, text='Dinner'))['state'], 'unknown')
                            self.assertEqual(calls, ['auth.test', 'conversations.history'])
                with patch('app.broker_slack.http.client.HTTPSConnection',
                           side_effect=lambda *a, **kw: connection_for(broker)):
                    client = BrokerSlack('https://broker/v1/slack', 'a'*43, 'TTEAM')
                    self.assertEqual(client.lookup(CHANNEL, KEY).state,
                                     'absent' if framing == 'complete' else 'unknown')
                    if framing != 'complete':
                        with self.assertRaises(UncertainDelivery):
                            client.post(CHANNEL, 'Dinner', KEY)

    def test_provider_ok_false_rate_limits_and_sanitized_errors(self):
        provider = SlackHTTPS('mock-token')
        class Response:
            status = 200
            length = 0
            body = {}
            def read(self, size): return json.dumps(self.body).encode()
            def getheader(self, name, default): return '1800'
        class Connection:
            sock = None
            def connect(self): pass
            def request(self, *args): pass
            def getresponse(self): return response
            def close(self): pass
        response = Response()
        for body, kind in [(dict(ok=False, error='missing_scope'), 'rejected'),
                           (dict(ok=False, error='ratelimited'), 'retry'),
                           (dict(ok=False, error='unknown-secret'), 'unknown'),
                           ({}, 'unknown')]:
            response.body = body
            with patch('admin.slack_adapter.http.client.HTTPSConnection', return_value=Connection()):
                with self.assertRaises(ProviderFailure) as raised: provider('chat.postMessage', {})
                self.assertEqual(raised.exception.kind, kind)
                self.assertNotIn('secret', str(raised.exception))
        response.status = 429
        with patch('admin.slack_adapter.http.client.HTTPSConnection', return_value=Connection()):
            with self.assertRaises(ProviderFailure) as raised: provider('chat.postMessage', {})
            self.assertEqual(raised.exception.wait, 1800)
        with patch.object(Connection, 'connect', side_effect=TimeoutError('private-token')):
            with patch('admin.slack_adapter.http.client.HTTPSConnection', return_value=Connection()):
                with self.assertRaises(ProviderFailure) as raised: provider('chat.postMessage', {})
                self.assertNotIn('private-token', str(raised.exception))

    def test_scoped_cloud_authentication_and_closed_protocol(self):
        capability = 'a'*43
        digest = hashlib.sha256(capability.encode()).hexdigest()
        class Adapter:
            calls = 0
            def handle(self, request):
                self.calls += 1
                return {'state':'unknown'}
        adapter = Adapter()
        self.assertEqual(dispatch(adapter, digest, '/v1/slack', 'Bearer '+capability, b'{}'), {'state':'unknown'})
        for path, auth, raw in [('/v1/slack', 'Bearer wrong', b'{}'),
                                ('/chat.postMessage', 'Bearer '+capability, b'{}'),
                                ('/v1/slack', '', b'{}'),
                                ('/v1/slack', 'Bearer '+capability, b' '*16385)]:
            with self.assertRaises(ValueError): dispatch(adapter, digest, path, auth, raw)
        self.assertEqual(adapter.calls, 1)


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ephemeral synthetic TLS identity; never an installed/provider credential.
        cls.tls_directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tls_directory.cleanup)
        cls.fixtures = Path(cls.tls_directory.name)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
            '-keyout', str(cls.fixtures/'key.pem'), '-out', str(cls.fixtures/'cert.pem'),
            '-days', '1', '-subj', '/CN=localhost'], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)

    def start(self, server):
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        def stop():
            server.shutdown()
            server.server_close()
            thread.join(2)
        self.addCleanup(stop)
        return server.server_address

    def test_stalled_tls_handshake_allows_next_authorized_request(self):
        class Adapter:
            def handle(self, request):
                return dict(version=1, workspace='TTEAM', channel=CHANNEL, state='absent')
        fixtures = self.fixtures
        server = create_server(Adapter(), hashlib.sha256(('a'*43).encode()).hexdigest(),
            ('127.0.0.1', 0), str(fixtures/'cert.pem'), str(fixtures/'key.pem'))
        server.handshake_timeout = 0.15
        address = self.start(server)
        stalled = socket.create_connection(address, timeout=2)
        self.addCleanup(stalled.close)
        context = ssl._create_unverified_context()  # Synthetic test certificate only.
        connection = http.client.HTTPSConnection(*address, timeout=2, context=context)
        self.addCleanup(connection.close)
        connection.request('POST', '/v1/slack', b'{}', {'Authorization': 'Bearer '+'a'*43})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())['state'], 'absent')

    def test_server_total_deadline_closes_trickling_headers(self):
        class Adapter:
            def handle(self, request):
                raise AssertionError('Incomplete request must not reach adapter')
        fixtures = self.fixtures
        server = create_server(Adapter(), 'a'*64, ('127.0.0.1', 0),
            str(fixtures/'cert.pem'), str(fixtures/'key.pem'))
        server.request_timeout = 0.2
        address = self.start(server)
        client = ssl._create_unverified_context().wrap_socket(
            socket.create_connection(address, timeout=2), server_hostname='localhost')
        self.addCleanup(client.close)
        closed = threading.Event()
        def trickle():
            try:
                client.sendall(b'POST /v1/slack HTTP/1.1\r\nX-Test: ')
                for _ in range(100):
                    client.sendall(b'a')
                    time.sleep(0.03)
            except OSError:
                closed.set()
        thread = threading.Thread(target=trickle, daemon=True)
        thread.start()
        self.assertTrue(closed.wait(2), 'Total deadline did not interrupt trickling headers')
        thread.join(1)

    def test_worker_trickling_body_and_headers_are_bounded_and_sanitized(self):
        for phase in ('headers', 'body'):
            with self.subTest(phase=phase):
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *args): pass
                    def do_POST(self):
                        try:
                            if phase == 'body':
                                self.send_response(200)
                                self.send_header('Content-Length', '4000')
                                self.end_headers()
                            else:
                                self.wfile.write(b'HTTP/1.1 200 OK\r\nX-Test: ')
                            for _ in range(100):
                                self.wfile.write(b'a'); self.wfile.flush()
                                time.sleep(0.03)
                        except OSError:
                            pass
                server = HTTPServer(('127.0.0.1', 0), Handler)
                address = self.start(server)
                client = BrokerSlack('https://localhost/v1/slack', 'a'*43, 'TTEAM')
                def connection(*args, **kwargs):
                    return http.client.HTTPConnection(*address, timeout=2)
                with patch('app.broker_slack.http.client.HTTPSConnection', side_effect=connection), \
                     patch('app.broker_slack.REQUEST_TIMEOUT', 0.2):
                    started = time.monotonic()
                    with self.assertRaises(UncertainDelivery) as raised:
                        client.post(CHANNEL, 'Dinner', KEY)
                    self.assertLess(time.monotonic()-started, 1.5)
                    self.assertEqual(str(raised.exception), 'Scoped broker unavailable or invalid response')
                    self.assertEqual(client.lookup(CHANNEL, KEY).state, 'unknown')


if __name__ == '__main__': unittest.main()
