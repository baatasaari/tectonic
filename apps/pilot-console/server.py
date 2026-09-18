#!/usr/bin/env python3
"""Local console host, durable enquiry capture and opt-in support-slice adapter.

Live mode deliberately requires loopback binding: this is not the authenticated
public pilot gateway specified in the ten-ticket production backlog.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC = Path(__file__).parent / 'static'
DATA = Path(os.environ.get('TECTONIC_CONSOLE_DATA', Path(__file__).parent / '.data'))
LIMIT = 16_384
WINDOW = defaultdict(deque)
LOCK = threading.Lock()
SESSIONS = set()
LIVE = os.environ.get('TECTONIC_CONSOLE_LIVE') == '1'
TENANT = os.environ.get('TECTONIC_CONSOLE_TENANT_ID', '')
SECRET = os.environ.get('TECTONIC_JWT_SHARED_SECRET', '')
CE_URL = os.environ.get('TECTONIC_CONVERSATION_URL', 'http://127.0.0.1:8081').rstrip('/')
ALLOWED_HOSTS = {'127.0.0.1', 'localhost', '[::1]'}


def initialize():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(DATA / 'leads.sqlite3') as db:
        db.execute('CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, created INTEGER, payload TEXT)')
    (DATA / 'leads.sqlite3').chmod(0o600)


def validate_lead(data):
    limits = {'name': 100, 'email': 254, 'company': 160, 'priority': 100, 'goal': 2000}
    if not isinstance(data, dict) or data.get('consent') is not True:
        raise ValueError('Consent is required.')
    clean = {}
    for field, length in limits.items():
        value = data.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > length or '\x00' in value:
            raise ValueError(f'Invalid {field}.')
        clean[field] = value.strip()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', clean['email']):
        raise ValueError('Enter a valid email address.')
    if len(clean['goal']) < 15:
        raise ValueError('Describe the goal in at least 15 characters.')
    return {**clean, 'consent': True, 'consent_version': 'pilot-enquiry-v1'}


def token():
    def encode(value):
        return base64.urlsafe_b64encode(value).decode().rstrip('=')
    now = int(time.time())
    head = encode(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
    body = encode(json.dumps({'iss': 'pilot-console', 'aud': 'conversational-engine', 'iat': now, 'exp': now + 60}).encode())
    unsigned = head + '.' + body
    return unsigned + '.' + encode(hmac.new(SECRET.encode(), unsigned.encode(), hashlib.sha256).digest())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the service credential through a redirect.


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, format, *args):
        pass  # No request bodies, credentials or enquiry PII in access logs.

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        super().end_headers()

    def respond(self, code, value):
        body = json.dumps(value).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        parsed = urllib.parse.urlsplit('http://' + self.headers.get('Host', ''))
        return parsed.hostname in {'localhost', '127.0.0.1', '::1'}

    def do_GET(self):
        if not self.valid_host():
            return self.respond(403, {'error': 'Unsupported Host header.'})
        path = urllib.parse.urlsplit(self.path).path
        if path == '/api/config':
            return self.respond(200, {'mode': 'demo', 'live_available': LIVE})
        if path == '/healthz':
            return self.respond(200, {'status': 'ok', 'catalogue': (STATIC / 'catalog.json').exists()})
        if path not in {'/', '/index.html', '/app.js', '/styles.css', '/catalog.json', '/favicon.ico'}:
            return self.respond(404, {'error': 'Not found.'})
        return super().do_GET()

    def do_POST(self):
        if not self.valid_host():
            return self.respond(403, {'error': 'Unsupported Host header.'})
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            return self.respond(403, {'error': 'Cross-origin requests are not allowed.'})
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return self.respond(403, {'error': 'Cross-site requests are not allowed.'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.respond(415, {'error': 'Use application/json.'})
        if self.headers.get('Transfer-Encoding'):
            return self.respond(400, {'error': 'Chunked bodies are not supported.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.respond(400, {'error': 'Invalid content length.'})
        if size < 0 or size > LIMIT:
            return self.respond(413, {'error': 'Request body exceeds 16 KB.'})
        with LOCK:
            bucket = WINDOW[self.client_address[0]]
            now = time.monotonic()
            while bucket and now - bucket[0] > 60:
                bucket.popleft()
            if len(bucket) >= 30:
                return self.respond(429, {'error': 'Rate limit reached. Try again in one minute.'})
            bucket.append(now)
        try:
            data = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            return self.respond(400, {'error': 'Invalid JSON.'})
        path = urllib.parse.urlsplit(self.path).path
        if path == '/api/leads':
            try:
                clean = validate_lead(data)
            except ValueError as exc:
                return self.respond(422, {'error': str(exc)})
            lead_id = 'pilot-' + secrets.token_hex(6)
            try:
                with sqlite3.connect(DATA / 'leads.sqlite3') as db:
                    db.execute('INSERT INTO leads VALUES (?, ?, ?)', (lead_id, int(time.time()), json.dumps(clean)))
            except sqlite3.Error:
                return self.respond(503, {'error': 'Enquiry storage is unavailable. Please try again.'})
            return self.respond(201, {'id': lead_id, 'stored': True})
        if not path.startswith('/api/runtime/'):
            return self.respond(404, {'error': 'Not found.'})
        if not LIVE:
            return self.respond(503, {'error': 'Live backend mode is disabled.'})
        if not isinstance(data, dict):
            return self.respond(422, {'error': 'Expected a JSON object.'})
        if path == '/api/runtime/sessions':
            target = '/v1/conversational-engine/sessions'
            payload = {'channel': 'web', 'persona_config_ref': 'default'}
        else:
            match = re.fullmatch(r'/api/runtime/sessions/([a-zA-Z0-9-]+)/messages', path)
            if not match or match[1] not in SESSIONS:
                return self.respond(403, {'error': 'Session is not owned by this local adapter.'})
            message = data.get('content')
            if not isinstance(message, str) or not message.strip() or len(message) > 4000:
                return self.respond(422, {'error': 'Message must contain 1–4000 characters.'})
            target = '/v1/conversational-engine/sessions/' + match[1] + '/messages'
            payload = {'content': message}
        request = urllib.request.Request(CE_URL + target, data=json.dumps(payload).encode(), method='POST', headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+token(), 'X-Tenant-Id': TENANT})
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=40) as response:
                result = json.loads(response.read(2_000_000))
            if path == '/api/runtime/sessions':
                SESSIONS.add(result['id'])
            return self.respond(200, result)
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
            return self.respond(502, {'error': 'The support backend did not return a usable response. Check server configuration and module health.'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=3000)
    parser.add_argument('--export-leads', action='store_true')
    args = parser.parse_args()
    initialize()
    if args.export_leads:
        with sqlite3.connect(DATA / 'leads.sqlite3') as db:
            print(json.dumps([{'id': i, 'created': c, **json.loads(p)} for i,c,p in db.execute('SELECT * FROM leads ORDER BY created')], indent=2))
        return
    if LIVE and (not TENANT or not SECRET or SECRET == 'dev-insecure-shared-secret-change-me'):
        parser.error('Live mode requires a server-configured tenant and non-default shared secret.')
    if urllib.parse.urlsplit(CE_URL).hostname not in {'localhost', '127.0.0.1', '::1'}:
        parser.error('The local adapter only connects to a loopback Conversational Engine.')
    print(f'Tectonic console: http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
