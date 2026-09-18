import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

TMP = tempfile.TemporaryDirectory()
os.environ['TECTONIC_CONSOLE_DATA'] = TMP.name
spec = importlib.util.spec_from_file_location('console_server', Path(__file__).parents[1] / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.initialize()
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.url = f'http://127.0.0.1:{cls.http.server_port}'
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        TMP.cleanup()

    def post(self, path, payload, headers=None):
        req = urllib.request.Request(self.url+path, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json', **(headers or {})})
        try:
            response = urllib.request.urlopen(req)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def test_consent_required(self):
        self.assertEqual(self.post('/api/leads', {'consent':False})[0], 422)

    def test_valid_enquiry_persisted_without_echoing_pii(self):
        code, result = self.post('/api/leads', {'name':'Test Visitor','email':'visitor@example.com','company':'Test Co','priority':'Support','goal':'Validate a support pilot workflow','consent':True})
        self.assertEqual(code,201)
        self.assertNotIn('email',result)
        with server.sqlite3.connect(server.DATA / 'leads.sqlite3') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM leads WHERE id=?',(result['id'],)).fetchone()[0],1)

    def test_cross_origin_blocked(self):
        self.assertEqual(self.post('/api/leads', {}, {'Origin':'https://evil.example'})[0],403)

    def test_unknown_host_blocked(self):
        self.assertEqual(self.post('/api/leads', {}, {'Host':'evil.example'})[0],403)

    def test_body_limit(self):
        self.assertEqual(self.post('/api/leads', {'goal':'x'*20000})[0],413)

    def test_live_disabled(self):
        self.assertEqual(self.post('/api/runtime/sessions', {})[0],503)

    def test_data_not_public(self):
        for path in ['/api/leads','/.data/leads.sqlite3','/../server.py']:
            with self.assertRaises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(self.url+path)
            self.assertEqual(exc.exception.code,404)

    def test_live_adapter_owns_sessions_and_ignores_arbitrary_paths(self):
        old = server.LIVE
        server.LIVE = True
        try:
            self.assertEqual(self.post('/api/runtime/sessions/not-owned/messages', {'content':'hello'})[0],403)
            self.assertEqual(self.post('/api/runtime/admin/providers', {})[0],403)
        finally:
            server.LIVE = old

    def test_security_headers_and_catalogue(self):
        with urllib.request.urlopen(self.url+'/catalog.json') as response:
            self.assertEqual(response.headers['X-Frame-Options'],'DENY')
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
            catalog=json.loads(response.read())
            self.assertEqual(len(catalog),34)
            self.assertGreater(sum(len(m['routes']) for m in catalog),250)


if __name__ == '__main__':
    unittest.main()
