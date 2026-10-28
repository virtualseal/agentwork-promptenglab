"""Mock-only deployment regressions; installed non-secret transport dependency."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

# No Broker/Provider is constructed; these imports never load config or keys.
sys.path.insert(0, '/Library/Application Support/CredentialProxy')
import railway_projects
from admin import railway_adapter as adapter

S = '11111111-1111-1111-1111-111111111111'
E = '22222222-2222-2222-2222-222222222222'
D = '33333333-3333-3333-3333-333333333333'
SHA = 'a' * 40
POLICY = {'workspace_id': adapter.WORKSPACE, 'owner': 'virtualseal'}


def connection(values):
    return {'edges': [{'node': value} for value in values], 'pageInfo': {'hasNextPage': False}}


def binding():
    return {'project': adapter.PROJECT, 'repo': adapter.REPO, 'service': S, 'environment': E,
            'writes_enabled': True, 'approval': {'sha': SHA, 'expires': 200,
            'checks': {name: 'passed' for name in adapter.CHECKS},
            'gates': {name: True for name in ('maps_complete', 'slack_installed', 'source_repo_verified',
            'autodeploy_disabled', 'no_staged_changes', 'durable_volume', 'single_worker', 'uid502', 'pacific_schedule')}}}


class API:
    def __init__(self):
        self.values = []
        self.writes = 0
        self.timeout = False
        self.status = 'SUCCESS'
        self.revision = SHA
        self.partial = False

    def call(self, query, variables, write=False):
        if query == adapter.PROJECT_QUERY:
            return {'project': {'id': adapter.PROJECT, 'services': connection([{'id': S}]),
                                'environments': connection([{'id': E}])}}
        if write:
            self.writes += 1
            self.values.append({'id': D, 'status': self.status, 'meta': {'commitHash': self.revision, 'repo': adapter.REPO}})
            if self.timeout: raise TimeoutError('lost acknowledgement')
            return {'serviceInstanceDeployV2': D}
        result = connection(self.values)
        if self.partial: result['pageInfo']['hasNextPage'] = True
        return {'deployments': result}


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'journal.sqlite3'
        self.api = API()
        self.binding = binding()

    def run_operation(self, operation='submit', sha=SHA):
        return adapter.run(self.api, POLICY, 'deployment.' + operation,
            {'project': adapter.PROJECT, 'repo': adapter.REPO, 'sha': sha}, self.binding, self.path, now=100)

    def test_scope_and_generic_query_rejected(self):
        for value in ({'project': S, 'repo': adapter.REPO, 'sha': SHA},
                      {'project': adapter.PROJECT, 'repo': 'other/repo', 'sha': SHA},
                      {'project': adapter.PROJECT, 'repo': adapter.REPO, 'sha': 'main'},
                      {'project': adapter.PROJECT, 'repo': adapter.REPO, 'sha': SHA, 'query': 'variables'}):
            with self.assertRaises(ValueError): adapter.validate_payload(POLICY, 'deployment.submit', value)
        self.assertEqual(self.api.writes, 0)

    def test_disabled_missing_failed_checks_no_write(self):
        for alteration in ('disabled', 'missing', 'failed', 'wrong-sha', 'maps', 'expired'):
            self.binding = binding()
            if alteration == 'disabled': self.binding['writes_enabled'] = False
            elif alteration == 'missing': self.binding['approval']['checks'].pop('unit')
            elif alteration == 'failed': self.binding['approval']['checks']['unit'] = 'failed'
            elif alteration == 'wrong-sha': self.binding['approval']['sha'] = 'b' * 40
            elif alteration == 'maps': self.binding['approval']['gates']['maps_complete'] = False
            else: self.binding['approval']['expires'] = 99
            with self.assertRaises(adapter.Blocked): self.run_operation()
        self.assertEqual(self.api.writes, 0)

    def test_lost_ack_reconciles_after_restart_without_duplicate(self):
        self.api.timeout = True
        self.assertEqual(self.run_operation()['status'], 'unknown')
        self.binding['writes_enabled'] = False
        self.assertEqual(self.run_operation('reconcile')['status'], 'SUCCESS')
        self.assertEqual(self.run_operation()['status'], 'SUCCESS')
        self.assertEqual(self.api.writes, 1)

    def test_no_authoritative_match_never_retries_or_starts_another_sha(self):
        self.api.timeout = True
        self.run_operation()
        self.api.values = []
        for unused in range(3): self.assertEqual(self.run_operation()['status'], 'unknown')
        self.binding['approval']['sha'] = 'b' * 40
        with self.assertRaises(adapter.Blocked): self.run_operation(sha='b' * 40)
        self.assertEqual(self.api.writes, 1)

    def test_wrong_revision_unknown_failed_build_explicit(self):
        self.api.revision = 'b' * 40
        self.assertEqual(self.run_operation()['status'], 'unknown')
        self.api.values[0]['meta']['commitHash'] = SHA
        self.api.values[0]['status'] = 'FAILED'
        self.assertEqual(self.run_operation('reconcile')['status'], 'FAILED')
        self.assertEqual(self.api.writes, 1)

    def test_truncated_history_blocks_before_intent(self):
        self.api.partial = True
        with self.assertRaises(adapter.Blocked): self.run_operation()
        self.assertEqual(self.api.writes, 0)

    def test_transport_rejects_partial_graphql_errors(self):
        class Control:
            def check(self): pass
            def attach(self, sock): pass
        class Response:
            status = 200
            def __init__(self): self.body = b'{"data":{"serviceInstanceDeployV2":"id"},"errors":[{"message":"partial"}]}'
            def getheader(self, key): return {'Content-Type': 'application/json', 'Content-Length': str(len(self.body))}.get(key)
            def read1(self, size):
                value, self.body = self.body, b''
                return value
        response = Response()
        with patch.object(railway_projects.http.client, 'HTTPSConnection') as connection:
            connection.return_value.getresponse.return_value = response
            api = railway_projects.API('synthetic-test-only', {'idle_timeout_seconds': 5, 'max_response_bytes': 2000}, Control())
            with self.assertRaises(Exception): api.call(adapter.DEPLOY, {}, write=True)

    def test_queued_request_reloads_disabled_admin_binding(self):
        disabled = binding()
        disabled['writes_enabled'] = False
        with self.assertRaises(adapter.Blocked):
            adapter.run(self.api, POLICY, 'deployment.submit',
                        {'project': adapter.PROJECT, 'repo': adapter.REPO, 'sha': SHA},
                        self.binding, self.path, now=100, refresh=lambda: disabled)
        self.assertEqual(self.api.writes, 0)

    def test_intent_is_durable_before_mutation(self):
        import sqlite3
        original = self.api.call
        def observed(query, variables, write=False):
            if write:
                with sqlite3.connect(self.path) as other:
                    row = other.execute('SELECT sha,deployment FROM deployments').fetchone()
                self.assertEqual(row, (SHA, None))
            return original(query, variables, write)
        self.api.call = observed
        self.assertEqual(self.run_operation()['status'], 'SUCCESS')

    def test_ambiguous_lost_ack_cannot_authorize_success(self):
        self.api.timeout = True
        self.run_operation()
        second = dict(self.api.values[0], id='44444444-4444-4444-4444-444444444444')
        self.api.values.append(second)
        self.assertEqual(self.run_operation('reconcile')['status'], 'unknown')
        self.assertEqual(self.api.writes, 1)

    def test_wrong_service_binding_and_active_build_block(self):
        self.binding['service'] = D
        with self.assertRaises(adapter.Blocked): self.run_operation()
        self.binding = binding()
        self.api.status = 'BUILDING'
        self.assertEqual(self.run_operation()['status'], 'BUILDING')
        self.binding['approval']['sha'] = 'b' * 40
        with self.assertRaises(adapter.Blocked): self.run_operation(sha='b' * 40)
        self.assertEqual(self.api.writes, 1)

    def test_stage_refuses_baseline_drift_without_output(self):
        from admin.prepare_railway import prepare
        baseline = Path(self.tmp.name) / 'baseline'
        baseline.mkdir()
        (baseline / 'proxy.py').write_text('drift')
        with self.assertRaises((ValueError, FileNotFoundError)):
            prepare(Path(self.tmp.name) / 'output', baseline)
        self.assertFalse((Path(self.tmp.name) / 'output').exists())


class DeploymentCLITests(unittest.TestCase):
    def invoke(self, operation, events):
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        from tools import railway_deploy as cli
        output = StringIO()
        request = unittest.mock.Mock(return_value=events)
        client = SimpleNamespace(request=request)
        spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module: None))
        args = ['railway_deploy', operation]
        if operation != 'inspect': args += ['--sha', SHA]
        with patch.object(cli.os, 'getuid', return_value=502), \
             patch.object(sys, 'argv', args), \
             patch.object(cli.importlib.util, 'spec_from_file_location', return_value=spec), \
             patch.object(cli.importlib.util, 'module_from_spec', return_value=client), \
             redirect_stdout(output):
            try:
                cli.main()
            finally:
                self.output = output.getvalue()
        return request

    def test_all_operations_consume_response_through_receipt(self):
        for operation in ('inspect', 'submit', 'reconcile'):
            with self.subTest(operation=operation):
                consumed = []
                def events():
                    yield {'type': 'start'}
                    yield {'type': 'response', 'body': {'status': 'unknown'}}
                    yield {'type': 'done'}
                    consumed.append(True)
                request = self.invoke(operation, events())
                self.assertEqual(json.loads(self.output), {'status': 'unknown'})
                self.assertEqual(consumed, [True])
                self.assertEqual(request.call_count, 1)
                self.assertEqual(request.call_args[0][1]['operation'], 'deployment.' + operation)

    def test_missing_receipt_or_transfer_failure_never_prints_success(self):
        for fail in (False, True):
            def events():
                yield {'type': 'start'}
                yield {'type': 'response', 'body': {'status': 'SUCCESS'}}
                if fail: raise RuntimeError('incomplete transfer')
            with self.assertRaises(RuntimeError): self.invoke('submit', events())
            self.assertEqual(self.output, '')


class WorkerLifecycleTests(unittest.TestCase):
    def invoke(self, port='8080', bind_error=None, polls=None):
        from deployment import worker
        from unittest.mock import Mock
        child = Mock()
        child.poll.side_effect = polls
        if polls is None: child.poll.return_value = None
        server = Mock()
        self.child, self.server = child, server
        with patch.dict(worker.os.environ, {'THURSDAY_CONFIG': 'synthetic.json', 'PORT': port}), \
             patch.object(worker.subprocess, 'Popen', return_value=child), \
             patch.object(worker, 'HealthServer', side_effect=bind_error, return_value=server), \
             patch.object(worker.signal, 'signal'):
            worker.main()

    def test_invalid_port_and_bind_failure_reap_child(self):
        for port, error, expected in [('invalid', None, ValueError),
                                      ('8080', OSError('occupied'), OSError)]:
            with self.subTest(port=port), self.assertRaises(expected):
                self.invoke(port, error)
            self.child.terminate.assert_called_once()
            self.child.wait.assert_called_once_with(timeout=10)

    def test_later_child_crash_exits_nonzero_and_closes_server(self):
        with self.assertRaises(SystemExit) as error:
            self.invoke(polls=[None, 7, 7])
        self.assertTrue(error.exception.code)
        self.server.handle_request.assert_called_once()
        self.server.server_close.assert_called_once()
        self.child.terminate.assert_not_called()
        self.child.wait.assert_called_once_with(timeout=10)

    def test_stalled_headers_do_not_hide_child_exit(self):
        import socket
        import threading
        from unittest.mock import Mock
        from deployment import worker

        accepted = threading.Event()
        crashed = threading.Event()
        listening = threading.Event()
        servers, outcomes = [], []
        real_server = worker.HealthServer

        class ObservedServer(real_server):
            def finish_request(self, request, address):
                accepted.set()
                super().finish_request(request, address)

        def factory(address, handler):
            server = ObservedServer(('127.0.0.1', 0), handler)
            servers.append(server)
            listening.set()
            return server

        child = Mock()
        child.poll.side_effect = lambda: 7 if crashed.is_set() else None

        def supervise():
            try:
                worker.main()
            except BaseException as error:
                outcomes.append(error)

        with patch.dict(worker.os.environ, {'THURSDAY_CONFIG': 'synthetic.json'}), \
             patch.object(worker.subprocess, 'Popen', return_value=child), \
             patch.object(worker, 'HealthServer', side_effect=factory), \
             patch.object(worker.signal, 'signal'):
            supervisor = threading.Thread(target=supervise, daemon=True)
            supervisor.start()
            client = None
            try:
                self.assertTrue(listening.wait(3))
                client = socket.create_connection(servers[0].server_address, timeout=3)
                client.sendall(b'GET /healthz HTTP/1.1\r\nHost: stalled')
                self.assertTrue(accepted.wait(3))
                crashed.set()
                # Keep the client open: only the server deadline can unblock it.
                supervisor.join(worker.REQUEST_DEADLINE_SECONDS + 3)
                self.assertFalse(supervisor.is_alive(), 'stalled headers hid child failure')
                self.assertEqual(len(outcomes), 1)
                self.assertIsInstance(outcomes[0], SystemExit)
                self.assertTrue(outcomes[0].code)
                child.wait.assert_called_once_with(timeout=10)
                self.assertEqual(servers[0].fileno(), -1)
            finally:
                crashed.set()
                if client is not None:
                    client.close()
                supervisor.join(3)
    def test_startup_cleanup_kills_child_that_ignores_termination(self):
        from deployment import worker
        from unittest.mock import Mock
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [worker.subprocess.TimeoutExpired('run', 10), 0]
        with patch.dict(worker.os.environ, {'THURSDAY_CONFIG': 'synthetic.json', 'PORT': 'invalid'}), \
             patch.object(worker.subprocess, 'Popen', return_value=child), \
             patch.object(worker.signal, 'signal'), self.assertRaises(ValueError):
            worker.main()
        child.kill.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)


if __name__ == '__main__': unittest.main()
