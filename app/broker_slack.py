"""Scoped result-only Slack port; this module never accepts a Slack token."""
import json
import re
import http.client
import socket
import threading
import time
import urllib.parse
from .sources import Lookup, RejectedDelivery, TemporaryFailure, UncertainDelivery

CHANNEL = 'C0CCRQUR6G1'
KEY = re.compile(r'^[a-zA-Z0-9_-]{1,128}$')


REQUEST_TIMEOUT = 35
CONNECT_TIMEOUT = 5


class BrokerSlack:
    def __init__(self, endpoint, capability, workspace, transport=None):
        from urllib.parse import urlsplit
        url = urlsplit(endpoint)
        if (url.scheme != 'https' or not url.hostname or url.username or
                url.password or url.query or url.fragment or url.path != '/v1/slack'):
            raise ValueError('Invalid scoped broker endpoint')
        if not re.fullmatch(r'T[A-Z0-9]+', workspace):
            raise ValueError('Invalid workspace binding')
        if not isinstance(capability, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', capability):
            raise ValueError('Invalid scoped capability')
        self.endpoint, self.capability, self.workspace = endpoint, capability, workspace
        self.transport = transport or self._https

    def _https(self, payload):
        url = urllib.parse.urlsplit(self.endpoint)
        deadline = time.monotonic() + REQUEST_TIMEOUT
        connection = http.client.HTTPSConnection(url.hostname, url.port,
                                                  timeout=min(CONNECT_TIMEOUT, REQUEST_TIMEOUT))
        timer = None
        try:
            connection.connect()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            sock = connection.sock
            def expire():
                try: sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            timer = threading.Timer(remaining, expire)
            timer.daemon = True
            timer.start()
            connection.request('POST', url.path, json.dumps(payload).encode(),
                {'Authorization': 'Bearer '+self.capability, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError('Invalid broker status')
            data = response.read(4097)
            # Bounded HTTPResponse.read does not reject premature EOF itself.
            if response.length not in (None, 0):
                raise ValueError('Incomplete broker response')
            if time.monotonic() >= deadline:
                raise TimeoutError()
            if len(data) > 4096:
                raise ValueError('Oversized response')
            return json.loads(data)
        finally:
            if timer:
                timer.cancel()
            connection.close()

    def _call(self, operation, channel, key, text=None):
        if channel != CHANNEL or not isinstance(key, str) or not KEY.fullmatch(key):
            raise RejectedDelivery('Invalid Slack scope')
        payload = dict(version=1, operation=operation, channel=channel, delivery_key=key)
        if text is not None:
            payload['text'] = text
        try:
            result = self.transport(payload)
            if (not isinstance(result, dict) or result.get('version') != 1 or
                    result.get('channel') != CHANNEL or result.get('workspace') != self.workspace):
                raise ValueError()
            return result
        except Exception:
            raise UncertainDelivery('Scoped broker unavailable or invalid response') from None

    def lookup(self, channel, key):
        try:
            result = self._call('lookup', channel, key)
            state, message = result.get('state'), result.get('message_id')
            if state == 'present' and isinstance(message, str) and re.fullmatch(r'[0-9]+\.[0-9]+', message):
                return Lookup('present', message)
            if state == 'absent':
                return Lookup('absent')
        except UncertainDelivery:
            pass
        return Lookup('unknown')

    def post(self, channel, text, key):
        if not isinstance(text, str) or not 1 <= len(text.encode()) <= 12000:
            raise RejectedDelivery('Invalid Slack message')
        result = self._call('deliver', channel, key, text)
        if result.get('state') == 'present' and re.fullmatch(r'[0-9]+\.[0-9]+', str(result.get('message_id', ''))):
            return result['message_id']
        if result.get('state') == 'retry':
            raise TemporaryFailure('Slack delivery deferred')
        if result.get('state') == 'rejected':
            raise RejectedDelivery('Slack delivery rejected')
        raise UncertainDelivery('Slack delivery requires reconciliation')
