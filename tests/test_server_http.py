import http.client
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from server.http import make_server
from server.service import Service


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = Service(Path(self.tmp.name) / 'db.sqlite3', password_cost=1024)
        self.server = make_server(self.service, '127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        status, data, headers = response.status, json.loads(response.read()), dict(response.getheaders())
        conn.close()
        return status, data, headers

    def test_live_health_auth_and_security_headers(self):
        status, body, headers = self.request('GET', '/v1/health')
        self.assertEqual(status, 200)
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(self.request('GET', '/v1/admin/users')[0], 401)

    def test_malformed_oversize_and_duplicate_json_rejected(self):
        for body in ['{', '[]', '{"key":NaN}', '{"key":"one","key":"two"}']:
            with self.subTest(body=body):
                self.assertEqual(self.request('POST', '/v1/license/validate', body, {'Content-Type': 'application/json'})[0], 400)
        self.assertEqual(self.request('POST', '/v1/auth/login', '{}', {'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('POST', '/v1/auth/login', 'x' * 70000, {'Content-Type': 'application/json'})[0], 413)

    def test_untrusted_forwarded_ip_cannot_evade_rate_limit(self):
        for number in range(31):
            status, _, _ = self.request('POST', '/v1/license/validate', json.dumps({'key': 'invalid-key-123456789'}), {'Content-Type': 'application/json', 'X-Forwarded-For': f'1.2.3.{number}'})
        self.assertEqual(status, 429)

    def test_duplicate_content_length_and_chunked_rejected(self):
        for headers in ['Content-Length: 2\r\nContent-Length: 2', 'Transfer-Encoding: chunked']:
            with socket.create_connection(('127.0.0.1', self.port), timeout=3) as conn:
                conn.sendall(('POST /v1/auth/login HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n' + headers + '\r\n\r\n{}').encode())
                self.assertIn(b'400', conn.recv(4096).split(b'\r\n')[0])


if __name__ == '__main__':
    unittest.main()
