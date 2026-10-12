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
        self.simulate_reasoning_budget = False
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
                valid = (body.get('reasoning') in ({'effort': 'low'}, {'effort': 'high'}) if is_responses
                         else isinstance(body.get('max_completion_tokens'), int) and 'max_tokens' not in body)
                if not valid or 'prompt_cache_key' in body:
                    return self.send_json({'error': {'message': 'Ark contract rejected'}}, 400)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                output = 'OK'
                output_tokens = 1000
                reasoning_tokens = 0
                finish_reason = 'stop' if owner.mode == 'success' else None
                if owner.chat_output_parts is not None or owner.simulate_reasoning_budget:
                    # Synthetic parts model tokens; both thinking and answer
                    # consume the actual limit received over loopback HTTP.
                    limit = body['max_output_tokens' if is_responses else 'max_completion_tokens']
                    if owner.simulate_reasoning_budget and body.get('thinking', {}).get('type') != 'disabled':
                        effort = (body.get('reasoning', {}).get('effort', 'high') if is_responses
                                  else body.get('reasoning_effort', 'high'))
                        reasoning_tokens = min(512, limit) if effort == 'low' else limit
                    answer_budget = limit - reasoning_tokens
                    parts = owner.chat_output_parts if owner.chat_output_parts is not None else ['OK']
                    output = ''.join(parts[:answer_budget])
                    output_tokens = reasoning_tokens + min(answer_budget, len(parts))
                    finish_reason = 'length' if len(parts) > answer_budget else finish_reason
                usage = {'input_tokens': owner.input_tokens, 'output_tokens': output_tokens,
                    'input_tokens_details': {'cached_tokens': 0}, 'tool_usage': {'web_search': 2}}
                if reasoning_tokens:
                    usage['output_tokens_details'] = {'reasoning_tokens': reasoning_tokens}
                if is_responses:
                    response = {'model': MANAGED_MODEL, 'usage': usage,
                        'status': 'completed' if finish_reason == 'stop' else 'incomplete', 'output': [
                        {'type': 'web_search_call', 'id': 'ws-1', 'status': 'completed', 'action': {'query': 'brand'}},
                        {'type': 'message', 'content': [{'type': 'output_text', 'text': output, 'annotations': [
                            {'type': 'url_citation', 'url': 'https://example.com/brand', 'title': 'Brand'}]}]}]}
                    terminal = ('response.completed' if finish_reason == 'stop' else
                                'response.incomplete' if finish_reason == 'length' else 'response.in_progress')
                    events = [{'type': 'response.output_text.delta', 'delta': output},
                        {'type': terminal,
                         'response': response}]
                else:
                    chat_usage = {'prompt_tokens': owner.input_tokens, 'completion_tokens': output_tokens}
                    if reasoning_tokens:
                        chat_usage['completion_tokens_details'] = {'reasoning_tokens': reasoning_tokens}
                    events = [{'model': MANAGED_MODEL, 'choices': [{'delta': {'content': output}}]},
                        {'model': MANAGED_MODEL, 'choices': [{'delta': {},
                            'finish_reason': finish_reason}],
                         'usage': chat_usage}]
                    if reasoning_tokens:
                        events.insert(0, {'model': MANAGED_MODEL,
                            'choices': [{'delta': {'reasoning_content': 'offline reasoning summary'}}]})
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
             task_key=None, attempt=1, content='OK', options=None):
        request_id = str(uuid.uuid4())
        logical_id = logical_id or 'offline:' + request_id
        headers = {'Authorization': 'Bearer ' + self.token, 'x-request-id': request_id,
            'x-billing-request-id': logical_id, 'x-report-session-id': 'offline-report',
            'x-task-key': task_key or task + ':' + request_id, 'x-task-type': task,
            'x-task-attempt': str(attempt)}
        if precise:
            headers['x-result-confirmation-capable'] = '1'
        stream = self.post('/chat/completions', {'model': model,
            'messages': [{'role': 'user', 'content': content}], **(options or {})}, headers)
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

    def test_server_owned_task_policy_ignores_client_reasoning_and_budget_overrides(self):
        budgets = {'source_clean': 12000, 'summary': 3500, 'analysis_step': 12000,
            'final_part': proxy.MAX_OUTPUT_TOKENS, 'revision_part': proxy.MAX_OUTPUT_TOKENS,
            'module_product_info': 8000, 'module_platform_audience': 16000,
            'module_material_review': 16000, 'module_benchmark': 16000,
            'module_selling_points': 16000, 'module_voc': 16000,
            'module_ranking': 16000, 'module_audience_sp_scene': 16000}
        cases = [(task, None, task in ('source_clean', 'summary', 'module_product_info'), budget)
                 for task, budget in budgets.items()]
        for suffix in ('extract-0001', 'normalize-0-0'):
            cases.append(('module_selling_points',
                ':material-insight:v1:abcdef12-1234-11:' + suffix, True, 16000))
        for suffix in (':material-insight:v2:abcdef12-1234-11:extract-0001',
                       ':material-insight:v1:not-a-fingerprint:extract-0001',
                       ':material-insight:v1:abcdef12-1234-11:extract-0001-extra',
                       ':material-insight:v1:abcdef12-1234-11:normalize-0-0:extra',
                       ':material-insight:v1:abcdef12-1234-11:final'):
            cases.append(('module_selling_points', suffix, False, 16000))
        cases.append(('module_voc', ':material-insight:v1:abcdef12-1234-11:extract-0001', False, 16000))
        for index, (task, suffix, direct, budget) in enumerate(cases):
            for client_effort in ('high', 'minimal'):
                with self.subTest(task=task, suffix=suffix, client_effort=client_effort):
                    task_key = 'policy-' + str(index) + '-' + client_effort + suffix if suffix else None
                    stream, request_id, logical_id = self.chat(task, task_key=task_key, options={
                        'thinking': {'type': 'enabled' if direct else 'disabled'},
                        'reasoning_effort': client_effort,
                        'reasoning': {'effort': client_effort, 'budget_tokens': 1},
                        'max_completion_tokens': 32768, 'max_output_tokens': 1, 'max_tokens': 1,
                        'prompt_cache_key': 'untrusted-client-hint'})
                    self.assertIn('[DONE]', stream)
                    endpoint, body, _ = self.requests[-1]
                    self.assertEqual(body['thinking'], {'type': 'disabled' if direct else 'enabled'})
                    self.assertNotIn('prompt_cache_key', body)
                    self.assertNotIn('max_tokens', body)
                    if task == 'module_benchmark':
                        self.assertTrue(endpoint.endswith('/responses'))
                        self.assertEqual(body['reasoning'], {'effort': 'low'})
                        self.assertNotIn('reasoning_effort', body)
                        self.assertNotIn('max_completion_tokens', body)
                        actual_limit = body['max_output_tokens']
                    else:
                        self.assertTrue(endpoint.endswith('/chat/completions'))
                        self.assertNotIn('reasoning', body)
                        self.assertNotIn('max_output_tokens', body)
                        if direct:
                            self.assertNotIn('reasoning_effort', body)
                        else:
                            self.assertEqual(body['reasoning_effort'], 'low')
                        actual_limit = body['max_completion_tokens']
                    self.assertEqual(actual_limit, min(proxy.MAX_OUTPUT_TOKENS, budget))
                    with proxy.database() as db:
                        reserved = db.execute('SELECT reserved_units FROM por_v2_attempts WHERE request_id=?',
                                              (request_id,)).fetchone()[0]
                    self.assertEqual(reserved, self.expected_reserve('OK', actual_limit))
                    self.assertEqual(self.confirm(request_id, logical_id)['state'], 'charged')

    def test_global_budget_still_clamps_upstream_and_reservation(self):
        with patch.object(proxy, 'MAX_OUTPUT_TOKENS', 9000):
            for task in ('source_clean', 'module_voc', 'module_benchmark', 'final_part'):
                with self.subTest(task=task):
                    _, request_id, logical_id = self.chat(task)
                    body = self.requests[-1][1]
                    actual_limit = body['max_output_tokens' if task == 'module_benchmark' else 'max_completion_tokens']
                    self.assertEqual(actual_limit, 9000)
                    with proxy.database() as db:
                        reserved = db.execute('SELECT reserved_units FROM por_v2_attempts WHERE request_id=?',
                                              (request_id,)).fetchone()[0]
                    self.assertEqual(reserved, self.expected_reserve('OK', actual_limit))
                    self.assertEqual(self.confirm(request_id, logical_id)['state'], 'charged')

    def test_high_thinking_only_failures_retry_with_visible_output_and_one_actual_charge(self):
        self.simulate_reasoning_budget = True
        self.chat_output_parts = ['answer '] * 4000 + ['COMPLETE']
        self.upstream_done = True
        current_options = proxy.apply_server_task_options
        current_responses_body = proxy.responses_request_body

        def legacy_high_options(body, task_type, task_key=''):
            current_options(body, task_type, task_key)
            body['thinking'] = {'type': 'enabled'}
            body.pop('reasoning_effort', None)  # Seed 2.1 defaults to high.

        def legacy_high_responses(body):
            result = current_responses_body(body)
            result['reasoning'] = {'effort': 'high'}
            return result

        scenarios = [('module_product_info', 5000, None, True),
            ('module_platform_audience', 8000, None, False),
            ('module_material_review', 10000, None, False),
            ('module_selling_points', 7000, 'extract-0001', True),
            ('module_selling_points', 7000, 'normalize-0-0', True),
            ('module_voc', 10000, None, False),
            ('module_benchmark', 5000, None, False)]
        for index, (task, old_limit, insight_suffix, direct) in enumerate(scenarios):
            with self.subTest(task=task, insight_suffix=insight_suffix):
                logical_id = 'offline:reasoning-recovery-' + str(index)
                task_key = ('reasoning-' + str(index) + ':material-insight:v1:abcdef12-1234-11:' + insight_suffix
                            if insight_suffix else 'reasoning:' + task + ':' + str(index))
                previous_debits = len(self.debits)
                with patch.dict(proxy.TASK_OUTPUT_RESERVES, {task: old_limit}), \
                        patch.object(proxy, 'apply_server_task_options', legacy_high_options), \
                        patch.object(proxy, 'responses_request_body', legacy_high_responses):
                    old_stream, old_id, _ = self.chat(task, logical_id=logical_id, task_key=task_key)
                self.assertEqual(self.stream_text(old_stream), '')
                self.assertNotIn('[DONE]', old_stream)
                with proxy.database() as db:
                    old = db.execute('SELECT * FROM por_v2_attempts WHERE request_id=?', (old_id,)).fetchone()
                self.assertEqual(old['state'], 'failed_no_charge')
                self.assertEqual(json.loads(old['provider_usage_json'])['output_tokens'], old_limit)
                self.assertEqual(len(self.debits), previous_debits)

                stream, new_id, _ = self.chat(task, logical_id=logical_id, task_key=task_key, attempt=2)
                visible = ''.join(self.chat_output_parts)
                self.assertEqual(self.stream_text(stream), visible)
                self.assertNotIn('offline reasoning summary', visible)
                self.assertIn('[DONE]', stream)
                charged = self.confirm(new_id, logical_id, visible)
                duplicate = self.confirm(new_id, logical_id, visible)
                self.assertEqual(charged['state'], 'charged')
                self.assertEqual(duplicate['charged_units'], charged['charged_units'])
                expected_output_tokens = len(self.chat_output_parts) + (0 if direct else 512)
                expected_cost = (Decimal(self.input_tokens) * 6 + Decimal(expected_output_tokens) * 30) / 1_000_000
                self.assertEqual(Decimal(self.debits[logical_id][4]), expected_cost)
                self.assertEqual(len(self.debits), previous_debits + 1)
                with proxy.database() as db:
                    new = db.execute('SELECT * FROM por_v2_attempts WHERE request_id=?', (new_id,)).fetchone()
                    self.assertEqual(json.loads(new['provider_usage_json'])['output_tokens'], expected_output_tokens)
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM por_v2_ledger WHERE logical_task_id=?',
                                               (logical_id,)).fetchone()[0], 1)

    def test_source_clean_completes_above_old_cap_and_reserves_full_output_budget(self):
        self.chat_output_parts = ['evidence '] * 6000 + ['\nCOVERAGE:OFFLINE-COMPLETE']
        self.input_tokens = 14089
        self.upstream_done = True
        content = 'synthetic source row\n' * 900
        stream, request_id, logical_id = self.chat('source_clean', content=content)
        output_limit = self.requests[-1][1]['max_completion_tokens']
        self.assertEqual(output_limit, min(proxy.MAX_OUTPUT_TOKENS, 12000))
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
