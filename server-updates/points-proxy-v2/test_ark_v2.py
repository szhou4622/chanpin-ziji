"""Offline HTTP and V2 ledger checks. No external credentials or paid calls."""
import hashlib
import json
import os
import sqlite3
import threading
import unittest
import uuid
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import product_report_proxy as proxy
from provider_keyring import ProviderKeyring
from provider_config import MANAGED_MODEL


class ArkV2Tests(unittest.TestCase):
    def setUp(self):
        self.balance_units = 1_000_000_000
        self.debits = {}
        self.requests = []
        self.mode = 'success'
        self.input_tokens = 1000
        self.chat_output_parts = None
        self.upstream_done = False
        owner = self

        class FakeUpstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send_json(self, value, status=200):
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self.send_json({'ok': True, 'binding_status': 'active', 'app_name': proxy.APP_NAME,
                    'machine_code': 'OFFLINE-MACHINE', 'code_id': 'OFFLINE-LICENSE',
                    'code_role': 'primary', 'remaining_credits': 1000, 'unlimited': False})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/license/consume':
                    return self.send_json({'ok': True, 'remaining_credits': 1000, 'unlimited': False})
                owner.requests.append((self.path, body, self.headers.get('Authorization')))
                if body.get('model') != MANAGED_MODEL:
                    return self.send_json({'error': {'message': 'legacy model leaked upstream'}}, 400)
                is_responses = self.path.endswith('/responses')
                valid = (body.get('reasoning') == {'effort': 'high'} if is_responses
                         else isinstance(body.get('max_completion_tokens'), int) and 'max_tokens' not in body)
                if not valid or 'prompt_cache_key' in body:
                    return self.send_json({'error': {'message': 'Ark contract rejected'}}, 400)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                usage = {'input_tokens': 1000, 'output_tokens': 1000,
                    'input_tokens_details': {'cached_tokens': 0}, 'tool_usage': {'web_search': 2}}
                if is_responses:
                    response = {'model': MANAGED_MODEL, 'usage': usage, 'output': [
                        {'type': 'web_search_call', 'id': 'ws-1', 'status': 'completed', 'action': {'query': 'brand'}},
                        {'type': 'message', 'content': [{'type': 'output_text', 'text': 'OK', 'annotations': [
                            {'type': 'url_citation', 'url': 'https://example.com/brand', 'title': 'Brand'}]}]}]}
                    events = [{'type': 'response.output_text.delta', 'delta': 'OK'},
                        {'type': 'response.completed' if owner.mode == 'success' else 'response.in_progress',
                         'response': response}]
                else:
                    output = 'OK'
                    output_tokens = 1000
                    finish_reason = 'stop' if owner.mode == 'success' else None
                    if owner.chat_output_parts is not None:
                        # Each synthetic part represents one token. Enforce the
                        # real HTTP request's cap instead of assuming a successful
                        # terminal response independently of the proxy's budget.
                        limit = body['max_completion_tokens']
                        output = ''.join(owner.chat_output_parts[:limit])
                        output_tokens = min(limit, len(owner.chat_output_parts))
                        finish_reason = 'length' if len(owner.chat_output_parts) > limit else finish_reason
                    events = [{'model': MANAGED_MODEL, 'choices': [{'delta': {'content': output}}]},
                        {'model': MANAGED_MODEL, 'choices': [{'delta': {},
                            'finish_reason': finish_reason}],
                         'usage': {'prompt_tokens': owner.input_tokens, 'completion_tokens': output_tokens}}]
                for event in events:
                    self.wfile.write(b'data: ' + json.dumps(event).encode() + b'\n\n')
                if owner.upstream_done:
                    self.wfile.write(b'data: [DONE]\n\n')
                self.wfile.flush()

        class QuietProxy(proxy.Handler):
            def log_message(self, *args):
                pass

        self.upstream = ThreadingHTTPServer(('127.0.0.1', 0), FakeUpstream)
        self.service = ThreadingHTTPServer(('127.0.0.1', 0), QuietProxy)
        self.servers = [self.upstream, self.service]
        self.threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in self.servers]
        upstream_url = f'http://127.0.0.1:{self.upstream.server_port}'
        self.proxy_url = f'http://127.0.0.1:{self.service.server_port}'
        uri = f'file:ark-v2-{uuid.uuid4().hex}?mode=memory&cache=shared'
        self.anchor = sqlite3.connect(uri, uri=True)

        def connection():
            db = sqlite3.connect(uri, uri=True, isolation_level=None)
            db.row_factory = sqlite3.Row
            return db

        def balance(_session):
            return {'ok': True, 'remaining_units': owner.balance_units, 'unlimited': False}

        def consume(_session, logical, attempt, units, model, bill_ref, cost):
            if logical not in owner.debits:
                owner.debits[logical] = (attempt, units, model, bill_ref, cost)
                owner.balance_units -= units
            return {'ok': True, 'remaining_units': owner.balance_units,
                'transaction_id': 'offline-' + logical}

        tariff = Path(__file__).with_name('ark-standard-20261012.json')
        routes = {MANAGED_MODEL: (upstream_url + '/api/v3', 'offline-provider-secret')}
        self.patches = [patch.object(proxy, 'connection', connection),
            patch.object(proxy, 'LICENSE_STATUS_URL', upstream_url + '/license/status'),
            patch.object(proxy, 'LICENSE_CONSUME_URL', upstream_url + '/license/consume'),
            patch.object(proxy, 'PROVIDER_KEYRING', ProviderKeyring('', routes, (MANAGED_MODEL,))),
            patch.object(proxy, 'SESSIONS', {}), patch.object(proxy, 'PRECISE_BILLING_ENABLED', True),
            patch.object(proxy, 'PRECISE_INTERNAL_TOKEN', 'offline-internal'),
            patch.object(proxy, 'PRECISE_BILLING_SOURCE', 'versioned_tariff'),
            patch.object(proxy, 'PRECISE_TARIFF_VERSION', 'ARK-STANDARD-2026-10-12'),
            patch.object(proxy, 'PRECISE_TARIFF_FILE', str(tariff)),
            patch.object(proxy, 'PRECISE_TARIFF_SHA256', hashlib.sha256(tariff.read_bytes()).hexdigest()),
            patch.object(proxy, 'precise_license_balance', balance),
            patch.object(proxy, 'precise_license_consume', consume),
            patch.dict(os.environ, {'POR_RESULT_PROOF_SECRET': 'offline-proof-secret-only-long-enough'})]
        for item in self.patches:
            item.start()
        for thread in self.threads:
            thread.start()
        session = self.post('/session', {'app_name': proxy.APP_NAME, 'machine_code': 'OFFLINE-MACHINE',
            'license_id': 'OFFLINE-LICENSE', 'device_credential': 'offline-device',
            'device_session': 'offline-session'})
        self.token = json.loads(session)['access_token']

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
        request = Request(self.proxy_url + path, data=json.dumps(body).encode(), method='POST',
            headers={'Content-Type': 'application/json', **(headers or {})})
        with urlopen(request, timeout=10) as response:
            return response.read().decode()

    def chat(self, task, model=MANAGED_MODEL, precise=True, *, logical_id=None,
             task_key=None, attempt=1, content='OK'):
        request_id = str(uuid.uuid4())
        logical_id = logical_id or 'offline:' + request_id
        headers = {'Authorization': 'Bearer ' + self.token, 'x-request-id': request_id,
            'x-billing-request-id': logical_id, 'x-report-session-id': 'offline-report',
            'x-task-key': task_key or task + ':' + request_id, 'x-task-type': task,
            'x-task-attempt': str(attempt)}
        if precise:
            headers['x-result-confirmation-capable'] = '1'
        stream = self.post('/chat/completions', {'model': model,
            'messages': [{'role': 'user', 'content': content}]}, headers)
        return stream, request_id, logical_id

    def confirm(self, request_id, logical_id, output='OK'):
        return json.loads(self.post('/billing/result/confirm', {'request_id': request_id,
            'logical_task_id': logical_id, 'output_sha256': hashlib.sha256(output.encode()).hexdigest(),
            'receipt_id': 'offline-receipt-' + request_id, 'locally_valid': True},
            {'Authorization': 'Bearer ' + self.token}))

    @staticmethod
    def stream_text(stream):
        events = [json.loads(line[5:].strip()) for line in stream.splitlines()
                  if line.startswith('data:') and line[5:].strip() not in ('', '[DONE]')]
        return ''.join(choice.get('delta', {}).get('content', '')
                       for event in events for choice in event.get('choices', []))

    def expected_reserve(self, content, output_limit):
        _, input_estimate = proxy.validate_messages({'model': MANAGED_MODEL,
            'messages': [{'role': 'user', 'content': content}]})
        reserve_milli = max(proxy.points_for_usage(model, input_estimate, output_limit)[0]
                            for model in proxy.ALLOWED_MODELS)
        return ((reserve_milli + 999) // 1000) * proxy.billing_v2.UNITS_PER_POINT

    def test_source_clean_completes_above_old_cap_and_reserves_full_output_budget(self):
        self.chat_output_parts = ['evidence '] * 6000 + ['\nCOVERAGE:OFFLINE-COMPLETE']
        self.input_tokens = 14089
        self.upstream_done = True
        content = 'synthetic source row\n' * 900
        stream, request_id, logical_id = self.chat('source_clean', content=content)
        output_limit = self.requests[-1][1]['max_completion_tokens']
        self.assertEqual(output_limit, proxy.MAX_OUTPUT_TOKENS)
        self.assertGreater(output_limit, 2500)
        self.assertEqual(self.requests[-1][1]['thinking'], {'type': 'disabled'})
        self.assertEqual(self.stream_text(stream), ''.join(self.chat_output_parts))
        self.assertIn('[DONE]', stream)
        with proxy.database() as db:
            row = db.execute('SELECT * FROM por_v2_attempts WHERE request_id=?', (request_id,)).fetchone()
            self.assertEqual(row['state'], 'awaiting_receipt')
            self.assertEqual(row['reserved_units'], self.expected_reserve(content, output_limit))
            self.assertGreater(row['reserved_units'], self.expected_reserve(content, 2500))
            self.assertEqual(json.loads(row['provider_usage_json'])['output_tokens'], 6001)
        self.assertFalse(self.debits)
        confirmed = self.confirm(request_id, logical_id, ''.join(self.chat_output_parts))
        self.assertEqual(confirmed['state'], 'charged')
        # Charge actual native token usage (6/30 CNY per million, times two),
        # not the larger reserved output budget.
        expected_cost = (Decimal(14089) * 6 + Decimal(6001) * 30) / 1_000_000
        self.assertEqual(Decimal(self.debits[logical_id][4]), expected_cost)
        self.assertLess(confirmed['charged_units'], row['reserved_units'])

    def test_source_clean_length_with_usage_and_done_is_free_then_same_task_retries_once(self):
        self.chat_output_parts = ['evidence '] * 6000 + ['\nCOVERAGE:OFFLINE-COMPLETE']
        self.upstream_done = True
        logical_id = 'offline:source-clean-retry'
        task_key = 'offline:source:batch-v7-planned:1'
        content = 'synthetic source row\n' * 900
        with patch.dict(proxy.TASK_OUTPUT_RESERVES, {'source_clean': 2500}):
            failed_stream, failed_id, _ = self.chat('source_clean', logical_id=logical_id,
                task_key=task_key, content=content)
        self.assertNotIn('[DONE]', failed_stream)
        self.assertEqual(self.stream_text(failed_stream), ''.join(self.chat_output_parts[:2500]))
        self.assertIn('"finish_reason":"length"', failed_stream.replace(' ', ''))
        with proxy.database() as db:
            failed = db.execute('SELECT * FROM por_v2_attempts WHERE request_id=?', (failed_id,)).fetchone()
            self.assertEqual(failed['state'], 'failed_no_charge')
            self.assertEqual(failed['reserved_units'], self.expected_reserve(content, 2500))
            self.assertEqual(json.loads(failed['provider_usage_json'])['output_tokens'], 2500)
            self.assertEqual(db.execute('SELECT state FROM por_v2_tasks WHERE logical_task_id=?',
                                       (logical_id,)).fetchone()[0], 'retryable')
        with self.assertRaises(HTTPError) as caught:
            self.confirm(failed_id, logical_id, self.stream_text(failed_stream))
        self.assertEqual(caught.exception.code, 409)
        caught.exception.close()
        self.assertFalse(self.debits)

        stream, successful_id, retried_logical = self.chat('source_clean', logical_id=logical_id,
            task_key=task_key, attempt=2, content=content)
        self.assertEqual(retried_logical, logical_id)
        self.assertNotEqual(successful_id, failed_id)
        self.assertIn('[DONE]', stream)
        self.assertEqual(self.stream_text(stream), ''.join(self.chat_output_parts))
        first = self.confirm(successful_id, logical_id, self.stream_text(stream))
        second = self.confirm(successful_id, logical_id, self.stream_text(stream))
        self.assertEqual(first['state'], 'charged')
        self.assertEqual(second['charged_units'], first['charged_units'])
        self.assertEqual(len(self.debits), 1)
        self.assertEqual(self.debits[logical_id][0], successful_id)
        with proxy.database() as db:
            rows = db.execute('SELECT request_id,state FROM por_v2_attempts WHERE logical_task_id=?',
                              (logical_id,)).fetchall()
            self.assertEqual({row['request_id']: row['state'] for row in rows},
                             {failed_id: 'failed_no_charge', successful_id: 'charged'})
            self.assertEqual(db.execute('SELECT COUNT(*) FROM por_v2_ledger WHERE logical_task_id=?',
                                       (logical_id,)).fetchone()[0], 1)

    def test_all_tasks_confirm_once_with_real_http_and_v2_ledger(self):
        for task in proxy.ALLOWED_TASK_TYPES:
            with self.subTest(task=task):
                prior = len(self.debits)
                stream, request_id, logical_id = self.chat(task)
                self.assertIn('[DONE]', stream)
                self.assertNotIn('"error"', stream)
                self.assertEqual(len(self.debits), prior)
                self.assertNotIn('offline-provider-secret', stream)
                if task == 'module_benchmark':
                    self.assertIn('"status":"verified"', stream)
                self.assertEqual(self.requests[-1][1]['model'], MANAGED_MODEL)
                confirmed = self.confirm(request_id, logical_id)
                self.assertEqual(confirmed['state'], 'charged')
                self.assertEqual(confirmed['charged_units'], 7_000_000)
                self.assertEqual(self.confirm(request_id, logical_id)['charged_units'], 7_000_000)
                self.assertEqual(len(self.debits), prior + 1)
                with proxy.database() as db:
                    row = db.execute('SELECT * FROM por_v2_attempts WHERE request_id=?', (request_id,)).fetchone()
                    self.assertEqual(row['response_model'], MANAGED_MODEL)
                    self.assertEqual(row['cost_cny'], '0.036')
        self.assertEqual(len(self.debits), len(proxy.ALLOWED_TASK_TYPES))

    def test_legacy_model_names_only_alias_to_doubao_for_all_tasks(self):
        for alias in proxy.LEGACY_MODEL_ALIASES:
            for task in ('source_clean', 'module_benchmark'):
                with self.subTest(alias=alias, task=task):
                    stream, _, _ = self.chat(task, alias, precise=False)
                    self.assertIn('[DONE]', stream)
                    self.assertEqual(self.requests[-1][1]['model'], MANAGED_MODEL)
        self.assertFalse(self.debits)

    def test_incomplete_stream_never_has_completion_proof_or_debit(self):
        self.mode = 'interrupted'
        for task in ('module_product_info', 'module_benchmark'):
            stream, request_id, logical_id = self.chat(task)
            self.assertNotIn('[DONE]', stream)
            with proxy.database() as db:
                state = db.execute('SELECT state FROM por_v2_attempts WHERE request_id=?', (request_id,)).fetchone()[0]
                self.assertEqual(state, 'failed_no_charge')
            with self.assertRaises(HTTPError) as caught:
                self.confirm(request_id, logical_id)
            caught.exception.close()
        self.assertFalse(self.debits)

    def test_cny_tariff_and_cache_pricing_are_independent_of_exchange_rate(self):
        usage = {'input_tokens': 3_000_000, 'output_tokens': 1_000_000, 'cached_input_tokens': 1_000_000}
        for fx in (7.2, 9.0):
            with patch.object(proxy, 'USD_CNY_RATE', fx):
                self.assertEqual(Decimal(proxy.v2_tariff_cost_cny(MANAGED_MODEL, usage)), Decimal('43.2'))
                self.assertEqual(proxy.points_for_usage(MANAGED_MODEL, 3_000_000, 1_000_000, 1_000_000)[1], 43.2)
        for model in proxy.LEGACY_MODEL_ALIASES:
            expected = Decimal(str(proxy.MODEL_PRICES[model][0])) * 7_200_000 / 1_000_000
            self.assertEqual(Decimal(proxy.v2_tariff_cost_cny(model, {'input_tokens': 1_000_000, 'output_tokens': 0})), expected)

    def test_tariff_hash_failure_blocks_debit_and_preserves_pending_result(self):
        _, request_id, logical_id = self.chat('source_clean')
        with patch.object(proxy, 'PRECISE_TARIFF_SHA256', '0' * 64):
            with self.assertRaises(HTTPError) as caught:
                self.confirm(request_id, logical_id)
            self.assertEqual(caught.exception.code, 503)
            caught.exception.close()
        self.assertFalse(self.debits)
        self.assertEqual(self.confirm(request_id, logical_id)['state'], 'charged')


if __name__ == '__main__':
    unittest.main()
