"""Bounded stdlib HTTP adapter. Deploy behind Caddy; this is not a TLS server."""
import ipaddress
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BODY_LIMIT = 65536


def _reject_constant(_):
    raise ValueError('Non-finite number')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = True
    allow_reuse_address = True
    request_queue_size = 32

    def __init__(self, address, handler, service, trusted_proxies):
        self.service = service
        self.trusted_proxies = tuple(ipaddress.ip_network(cidr, strict=False) for cidr in trusted_proxies)
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # No request paths, headers, bodies, tokens, or traceback locals in logs.
        pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'SacredTweaks'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(8)

    def log_message(self, format, *args):
        pass

    def _send(self, status, body):
        raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Pragma', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        self.wfile.write(raw)

    def send_error(self, code, message=None, explain=None):
        self._send(code, {'error': 'Invalid HTTP request.', 'code': 'invalid_request'})

    def _client_ip(self):
        peer = ipaddress.ip_address(self.client_address[0])
        if not any(peer in network for network in self.server.trusted_proxies):
            return str(peer)
        header = self.headers.get('X-Forwarded-For', '')
        if not header or len(header) > 1024:
            return str(peer)
        try:
            chain = [ipaddress.ip_address(item.strip()) for item in header.split(',')]
        except ValueError:
            return str(peer)
        # Start at the closest proxy; never use an arbitrary leftmost address.
        for address in reversed(chain):
            if not any(address in network for network in self.server.trusted_proxies):
                return str(address)
        return str(peer)

    def _handle(self):
        try:
            if len(self.path) > 2048 or self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) > 1 or len(self.headers.get_all('Authorization', [])) > 1:
                self._send(400, {'error': 'Invalid HTTP framing.', 'code': 'invalid_request'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 0:
                    raise ValueError()
            except ValueError:
                self._send(400, {'error': 'Invalid content length.', 'code': 'invalid_request'})
                return
            if length > BODY_LIMIT:
                self._send(413, {'error': 'Request body is too large.', 'code': 'body_too_large'})
                return
            data = {}
            if length:
                if self.headers.get_content_type() != 'application/json':
                    self._send(415, {'error': 'Use application/json.', 'code': 'content_type'})
                    return
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('Incomplete body')
                data = json.loads(raw.decode('utf-8'), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
                if not isinstance(data, dict):
                    raise ValueError('Object required')
            auth = self.headers.get('Authorization', '')
            token = auth[7:] if auth.startswith('Bearer ') else None
            status, body = self.server.service.handle(self.command, self.path, data, token, self._client_ip())
            self._send(status, body)
        except (ValueError, UnicodeError, RecursionError):
            self._send(400, {'error': 'Invalid JSON request.', 'code': 'invalid_input'})
        except (socket.timeout, TimeoutError):
            self.close_connection = True
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            # Keep the HTTP process available without disclosing implementation data.
            self._send(500, {'error': 'Unexpected service error.', 'code': 'server_error'})

    do_GET = do_POST = do_DELETE = _handle


def make_server(service, host='127.0.0.1', port=8765, trusted_proxies=()):
    return BoundedHTTPServer((host, port), Handler, service, trusted_proxies)
