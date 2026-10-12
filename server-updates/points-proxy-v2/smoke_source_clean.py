"""Verify supplied semantic batches with bounded, disposable test authorizations.

Run on the proxy host: python3 -B smoke_source_clean.py --cases private-cases.json
Input/output material stays in the supplied private directory; stdout only has
counts and billing metadata. Each case gets 100 test points and is disabled in
finally. Existing user projects, authorizations and balances are never edited.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import urllib.request
import uuid

from smoke_ark_v2 import APP, BASE, MODEL, POINTS_DB, freeze, test_code


def post(path, body, headers=None):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', **(headers or {})})
    with urllib.request.urlopen(request, timeout=600) as response:
        return response.status, response.read().decode()


def run_case(case, output_dir, license_server):
    marker = 'por-clean-limit-smoke-' + uuid.uuid4().hex
    code_id = ''
    try:
        code, code_id = test_code(marker)
        machine = 'POR-CLEAN-TEST-' + uuid.uuid4().hex.upper()
        auth = license_server.activate_remote(code, machine, APP)
        if auth.get('code_id') != code_id:
            raise RuntimeError('test activation mismatch')
        _, raw = post('/session', {'app_name': APP, 'machine_code': machine,
            'license_id': code_id, 'device_credential': auth['device_credential'],
            'device_session': auth['device_session']})
        headers = {'Authorization': 'Bearer ' + json.loads(raw)['access_token']}
        request_id = str(uuid.uuid4())
        logical = 'clean-smoke:' + uuid.uuid4().hex
        status, stream = post('/chat/completions', {'model': MODEL, 'messages': case['messages']},
            {**headers, 'x-request-id': request_id, 'x-billing-request-id': logical,
             'x-report-session-id': marker, 'x-task-key': logical, 'x-task-type': 'source_clean',
             'x-task-attempt': '1', 'x-result-confirmation-capable': '1'})
        parts, models, finish, done = [], set(), '', False
        for line in stream.splitlines():
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                done = True
                continue
            event = json.loads(data)
            if event.get('error'):
                raise RuntimeError('provider returned a stream error')
            if event.get('model'):
                models.add(event['model'])
            for choice in event.get('choices', []):
                delta = (choice.get('delta') or {}).get('content')
                if delta:
                    parts.append(delta)
                if choice.get('finish_reason'):
                    finish = choice['finish_reason']
        output = ''.join(parts)
        output_file = output_dir / (case['id'] + '.json')
        with output_file.open('x', encoding='utf-8') as handle:
            os.chmod(output_file, 0o600)
            json.dump({'id': case['id'], 'text': output, 'finish_reason': finish}, handle, ensure_ascii=False)
        if status != 200 or not done or finish != 'stop' or not output or models != {MODEL}:
            raise RuntimeError('cleaning stream was incomplete')
        allowed = set(case['evidenceIds'])
        cited = set(re.findall(r'POR-R-[A-Z0-9-]*', output, re.I))
        if ('COVERAGE:' + case['coverageReceipt']) not in output or not cited or not cited <= allowed:
            raise RuntimeError('semantic evidence receipt or references failed')
        receipt = {'request_id': request_id, 'logical_task_id': logical,
            'output_sha256': hashlib.sha256(output.encode()).hexdigest(),
            'receipt_id': 'clean-smoke-receipt:' + request_id, 'locally_valid': True}
        _, first_raw = post('/billing/result/confirm', receipt, headers)
        _, second_raw = post('/billing/result/confirm', receipt, headers)
        first, second = json.loads(first_raw), json.loads(second_raw)
        if first.get('state') != 'charged' or first.get('charged_units') != second.get('charged_units'):
            raise RuntimeError('confirmation was not idempotent')
        with sqlite3.connect('file:' + POINTS_DB + '?mode=ro', uri=True) as db:
            row = db.execute('SELECT state,response_model,provider_usage_json,cost_cny,amount_units '
                'FROM por_v2_attempts WHERE request_id=? AND code_id=?', (request_id, code_id)).fetchone()
            count = db.execute('SELECT count(*) FROM por_v2_ledger WHERE code_id=? AND logical_task_id=?',
                (code_id, logical)).fetchone()[0]
        if not row or row[0] != 'charged' or row[1] != MODEL or count != 1:
            raise RuntimeError('test billing audit failed')
        usage = json.loads(row[2])
        return {'id': case['id'], 'complete': True, 'evidence_receipt_valid': True,
            'input_tokens': usage.get('input_tokens'), 'output_tokens': usage.get('output_tokens'),
            'output_chars': len(output), 'cost_cny': row[3], 'test_points': row[4] / 1_000_000,
            'ledger_entries': count, 'replay_charged_once': True}
    except Exception as error:
        print(json.dumps({'id': case['id'], 'failure': str(error) if isinstance(error, RuntimeError)
                          else type(error).__name__}), flush=True)
        raise
    finally:
        if code_id:
            freeze(code_id, marker)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', required=True, type=Path)
    options = parser.parse_args()
    if options.cases.stat().st_size > 2_000_000:
        raise RuntimeError('case file exceeds the bounded smoke size')
    cases = json.loads(options.cases.read_text(encoding='utf-8'))
    if not isinstance(cases, list) or not 1 <= len(cases) <= 5:
        raise RuntimeError('provide one to five semantic cases')
    ids = set()
    for case in cases:
        case_id = case.get('id', '')
        if not re.fullmatch(r'[a-z0-9-]{1,64}', case_id) or case_id in ids:
            raise RuntimeError('invalid or duplicate case id')
        ids.add(case_id)
        if not case.get('messages') or not case.get('coverageReceipt') or not case.get('evidenceIds'):
            raise RuntimeError('case is missing messages or evidence scope')
    pid = subprocess.check_output(['systemctl', 'show', 'ovdt-license.service', '-p', 'MainPID'], text=True).strip().split('=')[1]
    env = dict(value.split(b'=', 1) for value in Path('/proc/' + pid + '/environ').read_bytes().split(b'\0') if b'=' in value)
    for name in ('DEVICE_SESSION_SECRET', 'OVDT_LICENSE_DB'):
        if name.encode() in env:
            os.environ[name] = env[name.encode()].decode()
    sys.path.insert(0, '/opt/original-video-dedup-tool/server')
    import license_server
    summaries = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_case, case, options.cases.parent, license_server) for case in cases]
        for future in as_completed(futures):
            summary = future.result()
            summaries.append(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
    print(json.dumps({'all_cases_passed': len(summaries)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('CLEAN_SMOKE_FAILED', type(error).__name__, flush=True)
        sys.exit(1)
