"""Loopback-only HTTP integration: real proxy, memory ledger, fake Ark/license.

No external requests, credentials, files, or paid model calls are used.
"""
import json
import sqlite3
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import product_report_proxy as proxy
from provider_keyring import ProviderKeyring
from provider_config import MANAGED_MODEL


class ArkHttpTests(unittest.TestCase):
    def setUp(self):
        self.balance = 1000.0
        self.debits = {}
        self.requests = []
        self.mode = "success"
        owner = self

        class FakeUpstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send_json(self, value, status=200):
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self.send_json({"ok": True, "binding_status": "active", "app_name": proxy.APP_NAME,
                    "machine_code": "OFFLINE-MACHINE", "code_id": "OFFLINE-LICENSE",
                    "code_role": "primary", "remaining_credits": owner.balance, "unlimited": False})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/license/consume":
                    if body["request_id"] not in owner.debits:
                        owner.debits[body["request_id"]] = body["amount"]
                        owner.balance -= body["amount"]
                    return self.send_json({"ok": True, "remaining_credits": owner.balance, "unlimited": False})
                owner.requests.append((self.path, body, self.headers.get("Authorization")))
                is_responses = self.path.endswith("/responses")
                if is_responses:
                    valid = body.get("reasoning") == {"effort": "high"} and "reasoning_effort" not in body
                else:
                    valid = isinstance(body.get("max_completion_tokens"), int) and "max_tokens" not in body
                if not valid:
                    return self.send_json({"error": {"message": "Ark protocol contract rejected"}}, 400)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                if is_responses:
                    events = [{"type": "response.output_text.delta", "delta": "OK"}]
                    response = {"model": MANAGED_MODEL, "usage": {
                        "input_tokens": 100, "output_tokens": 20, "tool_usage": {"web_search": 2}},
                        "output": [{"type": "web_search_call", "id": "ws-1", "action": {"query": "brand"}},
                            {"type": "message", "content": [{"type": "output_text", "text": "OK",
                                "annotations": [{"type": "url_citation", "url": "https://example.com/brand", "title": "Brand"}]}]}]}
                    events.append({"type": "response.completed" if owner.mode == "success" else "response.in_progress", "response": response})
                else:
                    events = [{"model": MANAGED_MODEL, "choices": [{"delta": {"content": "OK"}}]},
                        {"model": MANAGED_MODEL, "choices": [{"delta": {},
                            "finish_reason": "stop" if owner.mode == "success" else None}],
                            "usage": {"prompt_tokens": 100, "completion_tokens": 20}}]
                for event in events:
                    self.wfile.write(b"data: " + json.dumps(event).encode() + b"\n\n")
                self.wfile.flush()

        class QuietProxy(proxy.Handler):
            def log_message(self, *args):
                pass

        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstream)
        self.service = ThreadingHTTPServer(("127.0.0.1", 0), QuietProxy)
        self.servers = [self.upstream, self.service]
        self.threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in self.servers]
        upstream_url = f"http://127.0.0.1:{self.upstream.server_port}"
        self.proxy_url = f"http://127.0.0.1:{self.service.server_port}"
        memory_uri = f"file:ark-http-{uuid.uuid4().hex}?mode=memory&cache=shared"
        self.anchor = sqlite3.connect(memory_uri, uri=True)
        def connection():
            db = sqlite3.connect(memory_uri, uri=True)
            db.row_factory = sqlite3.Row
            return db
        routes = {MANAGED_MODEL: (upstream_url + "/api/v3", "offline-provider-secret")}
        self.patches = [patch.object(proxy, "connection", connection),
            patch.object(proxy, "LICENSE_STATUS_URL", upstream_url + "/license/status"),
            patch.object(proxy, "LICENSE_CONSUME_URL", upstream_url + "/license/consume"),
            patch.object(proxy, "PROVIDER_KEYRING", ProviderKeyring("", routes, (MANAGED_MODEL,))),
            patch.object(proxy, "SESSIONS", {}), patch.object(proxy, "WEB_SEARCH_USD_PER_CALL", 0.004 / proxy.USD_CNY_RATE)]
        for item in self.patches:
            item.start()
        for thread in self.threads:
            thread.start()
        session = self.post("/session", {"app_name": proxy.APP_NAME, "machine_code": "OFFLINE-MACHINE",
            "license_id": "OFFLINE-LICENSE", "device_credential": "offline-credential", "device_session": "offline-device-session"})
        self.token = json.loads(session)["access_token"]

    def tearDown(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=5)
        for item in reversed(self.patches):
            item.stop()
        self.anchor.close()

    def post(self, path, body, headers=None):
        request = Request(self.proxy_url + path, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", **(headers or {})})
        with urlopen(request, timeout=10) as response:
            return response.read().decode()

    def chat(self, task):
        request_id = str(uuid.uuid4())
        stream = self.post("/chat/completions", {"model": MANAGED_MODEL,
            "messages": [{"role": "user", "content": "OK"}]}, {
                "Authorization": "Bearer " + self.token, "x-request-id": request_id,
                "x-billing-request-id": "offline:" + request_id, "x-report-session-id": "offline-report",
                "x-task-key": task + ":" + request_id, "x-task-type": task, "x-task-attempt": "1"})
        with proxy.database() as db:
            row = dict(db.execute("SELECT * FROM model_requests WHERE request_id=?", (request_id,)).fetchone())
        return stream, row

    def test_all_tasks_cross_real_http_auth_stream_and_ledger(self):
        for task in proxy.ALLOWED_TASK_TYPES:
            with self.subTest(task=task):
                stream, row = self.chat(task)
                self.assertIn("[DONE]", stream)
                self.assertNotIn('"error"', stream)
                self.assertEqual(row["status"], "success")
                self.assertEqual(row["charged_milli"], 1840 if task == "module_benchmark" else 240)
                self.assertEqual(self.requests[-1][2], "Bearer offline-provider-secret")
                self.assertNotIn(self.token, json.dumps(self.requests[-1][1]))
                self.assertNotIn("offline-provider-secret", stream)
                if task == "module_benchmark":
                    self.assertIn('"status":"verified"', stream)
        self.assertEqual(len(self.debits), len(proxy.ALLOWED_TASK_TYPES))
        for path in ("/health", "/wallet"):
            with urlopen(Request(self.proxy_url + path,
                    headers={"Authorization": "Bearer " + self.token}), timeout=10) as response:
                self.assertNotIn("offline-provider-secret", response.read().decode())
        with proxy.database() as db:
            self.assertEqual(db.execute("SELECT locked_milli FROM wallets").fetchone()[0], 0)

    def test_eof_with_usage_is_not_a_success_terminal(self):
        self.mode = "interrupted"
        for task in ("module_product_info", "module_benchmark"):
            with self.subTest(task=task):
                stream, row = self.chat(task)
                self.assertNotIn("[DONE]", stream)
                self.assertNotEqual(row["status"], "success")

    def test_invalid_business_session_never_reaches_provider(self):
        with self.assertRaises(HTTPError) as caught:
            self.post("/chat/completions", {"model": MANAGED_MODEL, "messages": [{"role": "user", "content": "OK"}]},
                {"Authorization": "Bearer invalid-offline-session"})
        self.assertEqual(caught.exception.code, 401)
        caught.exception.close()
        self.assertFalse(self.requests)


if __name__ == "__main__":
    unittest.main()
