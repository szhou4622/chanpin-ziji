"""One-time production upgrade. Read the Ark key from stdin, never argv/logs.

Keeps a root-only rollback snapshot. No central-license code or user balances
are changed. Run the offline test suite before invoking this script as root.
"""
import ast
import datetime
import hashlib
import json
import os
import pathlib
import pwd
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

ROOT = pathlib.Path('/opt/product-operation-report')
CONFIG = pathlib.Path('/etc/product-operation-report')
SERVICE = 'product-report-proxy.service'
BASELINE_HASH = '460ce2d6c5c3984a0e339a2451fc0536bc2b0289b53e9683e4d8a2d4aa5039c4'
MODEL = 'doubao-seed-2-1-pro-260915'
BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3'
FILES = ['product_report_proxy.py', 'provider_config.py']


def atomic(path, data, mode, uid, gid):
    fd, name = tempfile.mkstemp(prefix='.ark-upgrade-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        os.fchown(fd, uid, gid)
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        dirfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        pathlib.Path(name).unlink(missing_ok=True)


def active_requests():
    with sqlite3.connect('file:' + str(ROOT / 'points.sqlite3') + '?mode=ro', uri=True) as db:
        legacy = db.execute("SELECT COUNT(*) FROM model_requests WHERE status='running'").fetchone()[0]
        precise = db.execute("SELECT COUNT(*) FROM por_v2_attempts WHERE state='running'").fetchone()[0]
        return legacy + precise


def main():
    if os.geteuid() != 0:
        raise RuntimeError('root required')
    source = pathlib.Path(__file__).resolve().parent
    old_proxy = ROOT / 'product_report_proxy.py'
    if hashlib.sha256(old_proxy.read_bytes()).hexdigest() != BASELINE_HASH:
        raise RuntimeError('production proxy changed since inspection; no writes')
    owner = pwd.getpwnam('product-report-proxy')
    keys_path = CONFIG / 'provider-keys.json'
    old_keys = json.loads(keys_path.read_bytes())
    if old_keys.get('generation') != 2 or set(old_keys.get('profiles', {})) != {'ccg-main'}:
        raise RuntimeError('provider configuration changed since inspection; no writes')
    if keys_path.is_symlink() or stat.S_IMODE(keys_path.stat().st_mode) != 0o600:
        raise RuntimeError('provider file type or permission mismatch; no writes')
    key = sys.stdin.read().strip()
    if not 16 <= len(key) <= 8192 or any(c.isspace() for c in key):
        raise RuntimeError('invalid key input; content suppressed')
    deadline = time.monotonic() + 900
    idle_since = None
    waiting_reported = False
    while True:
        if active_requests():
            idle_since = None
            if not waiting_reported:
                print('WAITING_FOR_RUNNING_TASKS_TO_FINISH', flush=True)
                waiting_reported = True
        else:
            idle_since = idle_since or time.monotonic()
            if time.monotonic() - idle_since >= 3:
                break
        if time.monotonic() >= deadline:
            raise RuntimeError('tasks remained active during wait; no writes')
        time.sleep(1)
    probe_body = {'model': MODEL, 'messages': [{'role': 'user', 'content': '只回复OK'}],
        'max_completion_tokens': 32, 'thinking': {'type': 'disabled'}}
    probe = urllib.request.Request(BASE_URL + '/chat/completions',
        data=json.dumps(probe_body).encode(), headers={'Authorization': 'Bearer ' + key,
            'Content-Type': 'application/json'})
    with urllib.request.urlopen(probe, timeout=45) as response:
        result = json.load(response)
        if (response.status != 200 or result.get('model') != MODEL or
            result.get('choices', [{}])[0].get('message', {}).get('content', '').strip().upper() != 'OK'):
            raise RuntimeError('server-side provider probe failed; no writes')
    print('SERVER_PROVIDER_PROBE_OK', flush=True)
    for name in FILES:
        ast.parse((source / name).read_text())
    tariff_source = source / 'ark-standard-20261012.json'
    tariff_bytes = tariff_source.read_bytes()
    tariff = json.loads(tariff_bytes)
    if tariff['models'][MODEL] != ['6', '30', '1.2', '6']:
        raise RuntimeError('unexpected tariff; no writes')
    if active_requests():
        raise RuntimeError('active model requests found; no writes')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = CONFIG / 'backups' / ('ark-v2-' + stamp + '-' + uuid.uuid4().hex[:8])
    backup.mkdir(mode=0o700, parents=True)
    env_path = CONFIG / 'ark-proxy.env'
    tariff_path = CONFIG / 'pricing' / tariff_source.name
    dropin_dir = pathlib.Path('/etc/systemd/system/product-report-proxy.service.d')
    dropin = dropin_dir / '90-ark-provider.conf'
    targets = [ROOT / name for name in FILES] + [keys_path, tariff_path, env_path, dropin]
    manifest = []
    for i, path in enumerate(targets):
        if path.is_symlink():
            raise RuntimeError('unexpected symlink target; no deployment writes')
        record = {'path': str(path), 'existed': path.exists(), 'backup': 'before-' + str(i)}
        if path.exists():
            st = path.stat()
            record.update({'mode': stat.S_IMODE(st.st_mode), 'uid': st.st_uid, 'gid': st.st_gid})
            data = path.read_bytes()
            atomic(backup / record['backup'], data, 0o600, 0, 0)
            record['sha256'] = hashlib.sha256(data).hexdigest()
        manifest.append(record)
    atomic(backup / 'manifest.json', json.dumps(manifest, indent=2).encode(), 0o600, 0, 0)
    with sqlite3.connect('file:' + str(ROOT / 'points.sqlite3') + '?mode=ro', uri=True) as db:
        with sqlite3.connect(backup / 'points.sqlite3.before') as destination:
            db.backup(destination)
    os.chmod(backup / 'points.sqlite3.before', 0o600)
    restore_source = '''import hashlib,json,pathlib,subprocess\nroot=pathlib.Path(__file__).parent\nrows=json.loads((root/'manifest.json').read_text())\nfor row in rows:\n if row['existed'] and hashlib.sha256((root/row['backup']).read_bytes()).hexdigest()!=row['sha256']: raise SystemExit('backup checksum mismatch')\nsubprocess.run(['systemctl','stop','product-report-proxy.service'],check=True)\nimport os,tempfile\nfor row in rows:\n p=pathlib.Path(row['path'])\n if not row['existed']: p.unlink(missing_ok=True);continue\n fd,n=tempfile.mkstemp(prefix='.ark-rollback-',dir=p.parent)\n os.fchmod(fd,row['mode']);os.fchown(fd,row['uid'],row['gid'])\n with os.fdopen(fd,'wb') as f: f.write((root/row['backup']).read_bytes());f.flush();os.fsync(f.fileno())\n os.replace(n,p)\nsubprocess.run(['systemctl','daemon-reload'],check=True)\nsubprocess.run(['systemctl','start','product-report-proxy.service'],check=True)\nprint('ROLLBACK_OK')\n'''
    atomic(backup / 'restore.py', restore_source.encode(), 0o700, 0, 0)
    print('BACKUP', str(backup), flush=True)
    stopped = False
    try:
        # Check immediately before the short restart window. Never kill known in-flight work.
        if active_requests():
            raise RuntimeError('requests started during preparation; no deployment writes')
        subprocess.run(['systemctl', 'stop', SERVICE], check=True)
        stopped = True
        if active_requests():
            raise RuntimeError('in-flight request detected after stop; restore existing service')
        for name in FILES:
            path = ROOT / name
            if path.exists():
                st = path.stat()
                mode, uid, gid = stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid
            else:
                mode, uid, gid = 0o644, 0, 0
            atomic(path, (source / name).read_bytes(), mode, uid, gid)
        atomic(tariff_path, tariff_bytes, 0o600, owner.pw_uid, owner.pw_gid)
        new_keys = old_keys.copy()
        new_keys['generation'] = int(old_keys['generation']) + 1
        new_keys['profiles']['ark-doubao'] = {'base_url': BASE_URL, 'active_key_id': 'ark-20261012',
            'keys': {'ark-20261012': key}}
        new_keys['models'] = {MODEL: 'ark-doubao'}
        atomic(keys_path, (json.dumps(new_keys, indent=2) + '\n').encode(),
            0o600, owner.pw_uid, owner.pw_gid)
        env = '\n'.join(['POR_PROVIDER_BASE_URL=' + BASE_URL, 'POR_PROVIDER_API_KEY=',
            'POR_PRECISE_TARIFF_VERSION=' + tariff['version'],
            'POR_PRECISE_TARIFF_FILE=' + str(tariff_path),
            'POR_PRECISE_TARIFF_SHA256=' + hashlib.sha256(tariff_bytes).hexdigest(), ''])
        atomic(env_path, env.encode(), 0o600, owner.pw_uid, owner.pw_gid)
        dropin_dir.mkdir(exist_ok=True)
        atomic(dropin, ('[Service]\nEnvironmentFile=' + str(env_path) + '\n').encode(), 0o644, 0, 0)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'start', SERVICE], check=True)
        for _ in range(20):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8794/health', timeout=2) as response:
                    health = json.load(response)
                if (health.get('models') == [MODEL] and health.get('precise_billing_enabled') is True
                    and health['provider_keyring']['reload_status'] == 'loaded'
                    and health['provider_keyring']['generation'] == '3'):
                    print('DEPLOYMENT_HEALTH_OK', json.dumps(health), flush=True)
                    return
            except Exception:
                pass
            time.sleep(0.25)
        raise RuntimeError('upgraded service health did not pass')
    except Exception:
        if stopped:
            subprocess.run(['python3', str(backup / 'restore.py')], check=True)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not emit exceptions with request headers/bodies or provider text.
        print('UPGRADE_FAILED', type(error).__name__, str(error)[:160] if isinstance(error, RuntimeError) else '', flush=True)
        sys.exit(1)
