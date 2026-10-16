"""Bounded Flask adapter for Vercel. No public owner-creation endpoint."""
import ipaddress
import json
import os
import threading

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from .http import BODY_LIMIT, _reject_constant, _unique_object


def create_app(service_factory=None):
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = BODY_LIMIT
    service = None
    init_lock = threading.Lock()

    def get_service():
        nonlocal service
        if service_factory is not None:
            return service_factory()
        with init_lock:
            if service is None:
                from .postgres import PostgresService
                service = PostgresService(os.environ['DATABASE_URL'])
        return service

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.name, code='invalid_request'), error.code

    @app.route('/v1/<path:subpath>', methods=['GET', 'POST', 'DELETE'])
    def api(subpath):
        try:
            path = request.path + ('?' + request.query_string.decode('ascii') if request.query_string else '')
            if len(path) > 2048:
                return jsonify(error='Invalid request path.',code='invalid_request'),400
            raw = request.get_data(cache=False)
            data = {}
            if raw:
                if request.mimetype != 'application/json':
                    return jsonify(error='Use application/json.',code='content_type'),415
                data = json.loads(raw.decode('utf-8'),parse_constant=_reject_constant,object_pairs_hook=_unique_object)
                if not isinstance(data,dict):
                    raise ValueError('Object required')
            auth = request.headers.get('Authorization','')
            token = auth[7:] if auth.startswith('Bearer ') else None
            peer = request.remote_addr or 'unknown'
            # This header is overwritten by Vercel; do not trust generic XFF.
            if os.environ.get('VERCEL') == '1':
                forwarded = request.headers.get('X-Vercel-Forwarded-For','')
                try:
                    peer = str(ipaddress.ip_address(forwarded.strip()))
                except ValueError:
                    peer = 'vercel-unknown'
            status, body = get_service().handle(request.method,path,data,token,peer)
            return jsonify(body),status
        except HTTPException:
            raise
        except (ValueError,UnicodeError,RecursionError):
            return jsonify(error='Invalid request value.',code='invalid_input'),400
        except Exception:
            # Never leak credentials, connection strings or request bodies in errors.
            return jsonify(error='Service temporarily unavailable.',code='unavailable'),503

    return app
