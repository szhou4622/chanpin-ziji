"""Verify stable-credential renewal against the live authorization service.

Run only on the authorization host with --run-live. Creates one bounded test
license, never calls a model, and disables that exact license in finally.
Codes, credentials and sessions are never printed or written to test artifacts.
The service retains its normal, disabled test-license audit row.
Existing customer licenses, bindings and balances are never modified.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

APP = 'ProductOperationReport'
BASE = 'https://license.dadaozixun.com/api/license'
LICENSE_DB = '/opt/original-video-dedup-tool/server/license_server.sqlite3'
POINTS_DB = '/opt/product-operation-report/points.sqlite3'
POINTS = 100


class VerificationError(RuntimeError):
    """Contains only a locally defined, credential-free diagnostic label."""


def request(path, payload=None, headers=None, discard=False):
    request_headers = {'Accept': 'application/json', **(headers or {})}
    if payload is not None:
        request_headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(BASE + path,
        data=None if payload is None else json.dumps(payload).encode(), headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
            if discard:
                return response.status, None
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as error:
        error.read()
        return error.code, None


def require(condition, label):
    if not condition:
        raise VerificationError(label)


def license_payload(body):
    # Match the desktop's explicit activation envelope; status is top-level.
    require(isinstance(body, dict) and body.get('ok') is True, 'invalid authorization response')
    nested = body.get('license', body)
    require(isinstance(nested, dict), 'invalid license envelope')
    for key in ('app_name', 'code_id', 'license_type', 'machine_code', 'binding_status', 'transfer_count',
                'remaining_credits', 'remaining_points', 'unlimited', 'expires_at',
                'device_credential', 'device_session', 'action', 'primary_code_id', 'merged_code_id'):
        require(key not in body or key not in nested or body[key] == nested[key], 'conflicting license envelope: ' + key)
    result = dict(nested)
    for key in ('action', 'grant_score', 'primary_code_id', 'merged_code_id'):
        if key in body:
            result[key] = body[key]
    require(result.get('app_name') == APP, 'wrong authorization application')
    return result


def snapshot(code_id):
    with sqlite3.connect('file:' + LICENSE_DB + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT device_credential_hash, credential_version, binding_status, '
            'bound_machine_code, transfer_count FROM activations WHERE app_name=? AND code_id=?',
            (APP, code_id)).fetchone()
    require(row is not None, 'test binding missing')
    return row


def freeze(code_id, marker):
    with sqlite3.connect(LICENSE_DB, timeout=15) as db:
        count = db.execute('UPDATE redeem_codes SET disabled=1 WHERE app_name=? AND code_id=? '
            'AND note=? AND credits=?', (APP, code_id, marker, POINTS)).rowcount
        disabled = db.execute('SELECT disabled FROM redeem_codes WHERE app_name=? AND code_id=? '
            'AND note=?', (APP, code_id, marker)).fetchone()
    require(count == 1 and disabled and disabled[0] == 1, 'exact test authorization was not disabled')
    if Path(POINTS_DB).exists():
        with sqlite3.connect(POINTS_DB, timeout=15) as db:
            db.execute('UPDATE wallets SET frozen=1 WHERE app_name=? AND code_id=?', (APP, code_id))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live', action='store_true', help='create and freeze one dedicated 100-point test license')
    args = parser.parse_args()
    if not args.run_live:
        parser.error('explicit --run-live is required')
    marker = 'por-stable-renewal-' + uuid.uuid4().hex
    code = 'POR-' + '-'.join(''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
        for _ in range(4)) for _ in range(3))
    digest = hashlib.sha256(code.encode()).hexdigest()
    code_id = digest[:16].upper()
    machine = secrets.token_hex(16)
    created = False
    audit = {'model_calls': 0, 'created_test_points': POINTS}
    try:
        with sqlite3.connect(LICENSE_DB, timeout=15) as db:
            db.execute('INSERT INTO redeem_codes '
                '(app_name,code_id,code_hash,code_plaintext,credits,unlimited,license_type,expires_at,disabled,created_at,note,duration_days) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (APP, code_id, digest, code, POINTS, 0, 'standard', '', 0,
                 time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), marker, 0))
        created = True
        body = {'license_protocol_version': 2, 'app_name': APP, 'activation_code': code,
                'machine_code': machine, 'client_version': '1.2.0'}
        status, initial = request('/activate', body)
        require(status == 200 and initial and initial.get('ok') is True, 'test activation failed HTTP ' + str(status))
        initial = license_payload(initial)
        credential, session = initial.get('device_credential'), initial.get('device_session')
        require(credential and session and initial.get('code_id') == code_id, 'test activation identity mismatch')
        baseline = snapshot(code_id)
        balance = initial.get('remaining_credits')
        headers = {'Authorization': 'Bearer ' + session, 'X-Device-Credential': credential}
        renewal = {**body, 'current_code_id': code_id, 'device_credential': credential}
        status_path = '/device/status?' + urllib.parse.urlencode({
            'license_protocol_version': 2, 'app_name': APP, 'machine_code': machine, 'code_id': code_id})

        def check_status(token=session):
            status, result = request(status_path, headers={**headers, 'Authorization': 'Bearer ' + token})
            require(status == 200 and result and result.get('ok') is True, 'existing device session became invalid')
            require(result.get('remaining_credits') == balance, 'test balance changed')
            return result

        def check_renewal(result):
            status, payload = result
            require(status == 200 and payload and payload.get('ok') is True, 'stable renewal failed')
            payload = license_payload(payload)
            require(payload.get('code_id') == code_id and payload.get('device_credential') == credential,
                    'renewal replaced the credential or primary license')
            require(payload.get('action') == 'already_bound' and payload.get('binding_status') == 'active',
                    'renewal changed device binding')
            require(payload.get('grant_score', 0) == 0 and payload.get('remaining_credits') == balance,
                    'renewal changed entitlement')
            require(snapshot(code_id) == baseline, 'renewal changed binding or credential version')
            return payload

        check_status()
        time.sleep(1.05)  # Device sessions use second-resolution issue times.
        # Discard a successful response, then retry with the original local data.
        status, _ = request('/activate', renewal, headers, discard=True)
        require(status == 200 and snapshot(code_id) == baseline, 'discarded response invalidated original credentials')
        check_status()
        renewed = check_renewal(request('/activate', renewal, headers))
        require(renewed['device_session'] != session, 'server did not issue a new temporary session')
        check_status(renewed['device_session'])
        check_status()
        audit['lost_response_retry_passed'] = True

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: request('/activate', renewal, headers), range(2)))
        for result in responses:
            check_status(check_renewal(result)['device_session'])
        check_status()
        audit['two_client_renewal_passed'] = True

        # This is the exact explicit recovery request used after session expiry:
        # the valid saved credential is supplied, and no expired bearer is sent.
        check_status(check_renewal(request('/activate', renewal))['device_session'])
        audit['explicit_recovery_request_passed'] = True
        audit['credential_and_binding_unchanged'] = snapshot(code_id) == baseline
        audit['balance_unchanged'] = True

        bad = {**renewal, 'device_credential': secrets.token_urlsafe(48)}
        status, _ = request('/activate', bad)
        require(status >= 400 and snapshot(code_id) == baseline, 'invalid credential was accepted')
        audit['invalid_credential_rejected'] = True
    finally:
        if created:
            audit['test_authorization_disabled'] = freeze(code_id, marker)
    audit['checked_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    audit['server_code_sha256'] = hashlib.sha256(Path('/opt/original-video-dedup-tool/server/license_server.py').read_bytes()).hexdigest()
    print(json.dumps(audit, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Never echo provider/server response bodies or request credentials.
        print(json.dumps({'ok': False, 'error_type': type(error).__name__,
            'reason': str(error) if isinstance(error, VerificationError) else 'external operation failed'}))
        raise SystemExit(1) from None
