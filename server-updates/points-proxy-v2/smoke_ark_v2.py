"""Real proxy smoke with a fresh, bounded test license; secrets stay in memory.

Retains audit rows and disables the exact test code/freezes its wallet in finally.
No existing user authorization, balance, task, or material is edited.
"""
import base64
import hashlib
import json
import os
import secrets
import sqlite3
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zlib

APP = 'ProductOperationReport'
MODEL = 'doubao-seed-2-1-pro-260915'
LICENSE_DB = '/opt/original-video-dedup-tool/server/license_server.sqlite3'
POINTS_DB = '/opt/product-operation-report/points.sqlite3'
BASE = 'https://api.dadaozixun.com/api/product-operation-report/v1'


def vision_content():
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    pixels = b''.join(b'\x00' + b'\xff\x00\x00' * 64 for _ in range(64))
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 64, 64, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))
    return [{'type': 'text', 'text': '只回答这张图片的主色。'},
        {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(png).decode()}}]


def post(path, body, headers=None):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=100) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        error.read()
        raise RuntimeError('HTTP_' + str(error.code)) from None


def test_code(marker):
    code = 'POR-' + '-'.join(''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
        for _ in range(4)) for _ in range(3))
    digest = hashlib.sha256(code.encode()).hexdigest()
    code_id = digest[:16].upper()
    with sqlite3.connect(LICENSE_DB, timeout=15) as db:
        db.execute('INSERT INTO redeem_codes '
            '(app_name,code_id,code_hash,code_plaintext,credits,unlimited,license_type,expires_at,disabled,created_at,note,duration_days) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (APP, code_id, digest, code, 100, 0, 'standard', '', 0,
             time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), marker, 0))
    return code, code_id


def freeze(code_id, marker):
    with sqlite3.connect(LICENSE_DB, timeout=15) as db:
        count = db.execute('UPDATE redeem_codes SET disabled=1 WHERE app_name=? AND code_id=? AND note=? AND credits=100',
            (APP, code_id, marker)).rowcount
    with sqlite3.connect(POINTS_DB, timeout=15) as db:
        db.execute('UPDATE wallets SET frozen=1 WHERE app_name=? AND code_id=?', (APP, code_id))
        frozen = db.execute('SELECT frozen FROM wallets WHERE app_name=? AND code_id=?', (APP, code_id)).fetchone()
    if count != 1 or not frozen or frozen[0] != 1:
        raise RuntimeError('test audit record freeze not verified')
    print('TEST_AUTHORIZATION_DISABLED_AND_WALLET_FROZEN', flush=True)


def main():
    pid = subprocess.check_output(['systemctl', 'show', 'ovdt-license.service', '-p', 'MainPID'], text=True).strip().split('=')[1]
    env = dict(v.split(b'=', 1) for v in open('/proc/' + pid + '/environ', 'rb').read().split(b'\0') if b'=' in v)
    for name in ('DEVICE_SESSION_SECRET', 'OVDT_LICENSE_DB'):
        if name.encode() in env:
            os.environ[name] = env[name.encode()].decode()
    sys.path.insert(0, '/opt/original-video-dedup-tool/server')
    import license_server
    marker = 'por-ark-v2-smoke-' + uuid.uuid4().hex
    code_id = ''
    try:
        code, code_id = test_code(marker)
        machine = 'POR-ARK-V2-TEST-' + uuid.uuid4().hex.upper()
        auth = license_server.activate_remote(code, machine, APP)
        if auth.get('code_id') != code_id:
            raise RuntimeError('test activation mismatch')
        _, raw = post('/session', {'app_name': APP, 'machine_code': machine, 'license_id': code_id,
            'device_credential': auth['device_credential'], 'device_session': auth['device_session']})
        token = json.loads(raw)['access_token']
        selected = set(sys.argv[1:] or ['text', 'vision', 'search'])
        if not selected <= {'text', 'vision', 'search'}:
            raise RuntimeError('allowed smoke cases: text vision search')
        for case, task, requested, prompt in [
            ('text', 'source_clean', 'gpt-5.5', '只输出1到100，每行一个数字，不要解释。'),
            ('vision', 'source_clean', MODEL, vision_content()),
            ('search', 'module_benchmark', MODEL, '使用联网搜索查火山引擎官网，只回复官网地址及一个来源链接。')]:
            if case not in selected:
                continue
            request_id = str(uuid.uuid4())
            logical = 'ark-smoke:' + uuid.uuid4().hex
            status, stream = post('/chat/completions', {'model': requested,
                'messages': [{'role': 'user', 'content': prompt}]},
                {'Authorization': 'Bearer ' + token, 'x-request-id': request_id,
                 'x-billing-request-id': logical, 'x-report-session-id': marker,
                 'x-task-key': task + ':' + uuid.uuid4().hex, 'x-task-type': task,
                 'x-task-attempt': '1', 'x-result-confirmation-capable': '1'})
            chunks = []
            stream_models = set()
            verified_search = False
            for line in stream.splitlines():
                if not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    continue
                event = json.loads(data)
                if event.get('error'):
                    raise RuntimeError('provider stream returned error')
                if event.get('model'):
                    stream_models.add(event['model'])
                if event.get('type') == 'por.search_status' and event.get('status') == 'verified':
                    verified_search = True
                for choice in event.get('choices', []):
                    content = (choice.get('delta') or {}).get('content')
                    if content:
                        chunks.append(content)
            if status != 200 or '[DONE]' not in stream or not chunks:
                raise RuntimeError('proxy stream incomplete')
            # Responses output is converted to content-only chat deltas. Its
            # actual model is checked in the server's durable usage record below.
            if (stream_models and stream_models != {MODEL}) or (task != 'module_benchmark' and not stream_models):
                raise RuntimeError('unexpected upstream model')
            if task == 'module_benchmark' and not verified_search:
                raise RuntimeError('search citation verification missing')
            if isinstance(prompt, list) and '红' not in ''.join(chunks):
                raise RuntimeError('vision result did not identify the known red image')
            receipt = {'request_id': request_id, 'logical_task_id': logical,
                'output_sha256': hashlib.sha256(''.join(chunks).encode()).hexdigest(),
                'receipt_id': 'smoke-receipt:' + request_id, 'locally_valid': True}
            with sqlite3.connect('file:' + POINTS_DB + '?mode=ro', uri=True) as db:
                pre_count = db.execute('SELECT COUNT(*) FROM por_v2_ledger WHERE app_name=? AND code_id=? AND logical_task_id=?',
                    (APP, code_id, logical)).fetchone()[0]
            if pre_count != 0:
                raise RuntimeError('charged before result confirmation')
            _, raw = post('/billing/result/confirm', receipt, {'Authorization': 'Bearer ' + token})
            confirmed = json.loads(raw)
            _, raw2 = post('/billing/result/confirm', receipt, {'Authorization': 'Bearer ' + token})
            confirmed2 = json.loads(raw2)
            if confirmed.get('state') != 'charged' or confirmed2.get('charged_units') != confirmed.get('charged_units'):
                raise RuntimeError('confirmation or replay mismatch')
            with sqlite3.connect('file:' + POINTS_DB + '?mode=ro', uri=True) as db:
                row = db.execute('SELECT response_model,cost_cny,amount_units,state FROM por_v2_attempts WHERE request_id=? AND code_id=?',
                    (request_id, code_id)).fetchone()
                count = db.execute('SELECT COUNT(*) FROM por_v2_ledger WHERE app_name=? AND code_id=? AND logical_task_id=?',
                    (APP, code_id, logical)).fetchone()[0]
            if count != 1 or row[0] != MODEL or row[3] != 'charged':
                raise RuntimeError('proxy audit mismatch')
            with sqlite3.connect('file:' + LICENSE_DB + '?mode=ro', uri=True) as db:
                central_count = db.execute('SELECT COUNT(*) FROM por_precise_transactions WHERE app_name=? AND code_id=? AND logical_task_id=?',
                    (APP, code_id, logical)).fetchone()[0]
            if central_count != 1:
                raise RuntimeError('central ledger mismatch')
            print(json.dumps({'task': task, 'requested_model': requested, 'actual_model': row[0],
                'complete': True, 'search_verified': verified_search,
                'vision_verified': isinstance(prompt, list), 'cost_cny': row[1],
                'charged_points': row[2] / 1_000_000, 'proxy_ledger_entries': count,
                'central_ledger_entries': central_count, 'repeat_confirmation_charged_once': True}), flush=True)
    finally:
        if code_id:
            freeze(code_id, marker)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('SMOKE_FAILED', type(error).__name__, str(error)[:160] if isinstance(error, RuntimeError) else '', flush=True)
        sys.exit(1)
