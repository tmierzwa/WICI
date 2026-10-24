# SPDX-License-Identifier: MIT
"""Exercise the real HTTP parser and panel handler with byte streams, without binding a port.

These are handler/security tests, not a replacement for TCP, browser, or START integration tests.
Reuse the existing assertions; only the transport fixture changes.
"""
import http.client
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import test_laptop as base


class MemoryConnection:
    def __init__(self, incoming):
        self.incoming = incoming
        self.outgoing = bytearray()

    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.incoming)

    def sendall(self, data):
        self.outgoing.extend(data)


class PanelMemoryTest(base.PanelTest):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / 'usb').mkdir()
        cls.session = base.session.Session(root / 'usb', root / 'stan', iterations=1000)
        cls.envelopes = cls.session.create(1)['envelopes']
        station = base.FakeStation()
        cls.panel = base.Panel(station, base.Prep(station, cls.session), cls.session, 'tok-123', {'version': 't'})
        cls.port = 18082
        cls.server = SimpleNamespace(server_address=('127.0.0.1', cls.port), shutdown=lambda: None)
        cls.panel.server = cls.server
        cls.handler = base.web.make_handler(cls.panel)

    @classmethod
    def tearDownClass(cls):
        cls.session.close()
        cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None, host=None):
        payload = body.encode('utf-8') if isinstance(body, str) else body or b''
        h = {'Host': host or f'127.0.0.1:{self.port}', 'Connection': 'close'}
        h.update(headers or {})
        h.setdefault('Content-Length', str(len(payload)))
        raw = (f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in h.items()) + '\r\n').encode() + payload
        conn = MemoryConnection(raw)
        self.handler(conn, ('127.0.0.1', 1), self.server)
        response = http.client.HTTPResponse(MemoryConnection(bytes(conn.outgoing)), method=method)
        response.begin()
        return response, response.read()

    @unittest.skip('The real second START uses TCP; covered only by the separate network integration suite.')
    def test_start_link_works_once_and_second_start_gets_a_new_one(self):
        pass

    def test_one_time_ticket_through_http(self):
        ticket = self.panel.ticket()
        response, _ = self.request('GET', f'/start?t={ticket}')
        self.assertEqual(response.status, 303)
        self.assertIn('HttpOnly', response.getheader('Set-Cookie'))
        self.assertEqual(self.request('GET', f'/start?t={ticket}')[0].status, 403)

    def test_usb_state_changes_without_any_write(self):
        usb = self.session.usb
        away = usb.with_name('usb-away')
        before = self.request('GET', '/api/state', headers={'Cookie': self.cookie()})
        self.assertEqual(before[0].status, 200)
        self.assertTrue(json.loads(before[1])['session']['db']['usb_present'])
        try:
            usb.rename(away)
            response, body = self.request('GET', '/api/state', headers={'Cookie': self.cookie()})
            self.assertEqual(response.status, 200)
            status = json.loads(body)['session']['db']
            self.assertFalse(status['usb_present'])
            self.assertFalse(status['usb_saved'])
            self.assertEqual(status['usb_problem'], base.database.NO_USB)
        finally:
            away.rename(usb)
        self.assertTrue(json.loads(self.request('GET', '/api/state', headers={'Cookie': self.cookie()})[1])['session']['db']['usb_present'])

    def test_validation_returns_canonical_text_and_rejects_65_bytes(self):
        doc = base.station_doc(addresses=['Szko\u200bła  Podstawowa'])
        response, body = self.request('POST', '/api/config/check', json.dumps({'doc': doc}), {'Cookie': self.cookie(), 'Content-Type': 'application/json'})
        self.assertEqual(response.status, 200)
        result = json.loads(body)
        self.assertEqual(result['doc']['addresses'], ['Szkoła Podstawowa'])
        self.assertEqual(result['problems'], [])
        doc['addresses'] = ['A' * 65]
        response, body = self.request('POST', '/api/config/check', json.dumps({'doc': doc}), {'Cookie': self.cookie(), 'Content-Type': 'application/json'})
        self.assertEqual(response.status, 200)
        self.assertIn('addresses.0', [p['field'] for p in json.loads(body)['problems']])
