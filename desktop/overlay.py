"""Copyright (c) 2026 Sacred LLC. Paired, loopback-only Game Bar transport.

This is NOT an authentication bypass: every command goes through Api.local.
No cloud token, password, device identifier or admin route is exposed.
"""
import hmac
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ACTIONS = {'macro_status','macro_configure','macro_enable','emergency_stop'}

class OverlayServer:
    def __init__(self, api, authorization_lock=None):
        self.api = api
        self.lock = authorization_lock or threading.RLock()
        self.token = secrets.token_urlsafe(32)
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def setup(self):
                super().setup()
                self.connection.settimeout(3)
            def respond(self, status, value):
                raw=json.dumps(value, allow_nan=False).encode()
                self.send_response(status)
                self.send_header('Content-Type','application/json')
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def do_POST(self):
                expected='Bearer '+owner.token
                if (self.headers.get('Origin') or self.headers.get('Host') != '127.0.0.1:'+str(owner.server.server_port)
                        or not hmac.compare_digest(self.headers.get('Authorization',''), expected)):
                    self.respond(403,{'ok':False,'error':'Pairing required.'});return
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if self.path!='/command' or not 0<length<=8192 or self.headers.get('Transfer-Encoding'):
                        raise ValueError()
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict) or body.get('action') not in ACTIONS or not isinstance(body.get('payload',{}),dict):
                        raise ValueError()
                except (ValueError,TypeError):
                    self.respond(400,{'ok':False,'error':'Invalid widget command.'});return
                # Same RLock as Api._clear: no stale admitted request can act
                # after pairing rotation, and lock order remains account -> native.
                with owner.lock:
                    if not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+owner.token):
                        self.respond(403,{'ok':False,'error':'Pairing expired.'});return
                    result=owner.api.local(body['action'],body.get('payload',{}))
                self.respond(200,result)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True,name='Sacred-GameBar')
        self.thread.start()
    def pair(self):
        with self.lock:
            self.token=secrets.token_urlsafe(32)
            return {'port':self.server.server_port,'token':self.token}
    def revoke(self):
        with self.lock:
            self.token=secrets.token_urlsafe(32)
    def close(self):
        self.revoke();self.server.shutdown();self.server.server_close()
