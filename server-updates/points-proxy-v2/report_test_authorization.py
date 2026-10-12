"""Create/freeze one bounded, private authorization for full desktop E2E.

python3 -B report_test_authorization.py create /private/path/auth.json
python3 -B report_test_authorization.py freeze /private/path/auth.json
The activation code is written only to the private file, never stdout.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import uuid

from smoke_ark_v2 import APP, LICENSE_DB, POINTS_DB, test_code

POINTS = 2000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('create', 'freeze'))
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    if args.operation == 'create':
        if args.path.exists():
            raise RuntimeError('authorization file already exists')
        marker = 'por-report-e2e-' + uuid.uuid4().hex
        code, code_id = test_code(marker)
        try:
            with sqlite3.connect(LICENSE_DB, timeout=15) as db:
                count = db.execute('UPDATE redeem_codes SET credits=? WHERE app_name=? AND code_id=? AND note=? AND credits=100 AND disabled=0',
                    (POINTS, APP, code_id, marker)).rowcount
                if count != 1:
                    raise RuntimeError('test authorization scope mismatch')
            fd = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as handle:
                json.dump({'activationCode': code, 'codeId': code_id, 'marker': marker, 'points': POINTS}, handle)
        except BaseException:
            with sqlite3.connect(LICENSE_DB, timeout=15) as db:
                db.execute('UPDATE redeem_codes SET disabled=1 WHERE app_name=? AND code_id=? AND note=?', (APP, code_id, marker))
            raise
        print(json.dumps({'created': True, 'bounded_test_points': POINTS}))
        return
    saved = json.loads(args.path.read_text())
    if not saved.get('marker', '').startswith('por-report-e2e-') or saved.get('points') != POINTS:
        raise RuntimeError('not a bounded report test authorization')
    with sqlite3.connect(LICENSE_DB, timeout=15) as db:
        count = db.execute('UPDATE redeem_codes SET disabled=1 WHERE app_name=? AND code_id=? AND note=? AND credits=?',
            (APP, saved['codeId'], saved['marker'], POINTS)).rowcount
        if count != 1:
            raise RuntimeError('test authorization disable scope mismatch')
    with sqlite3.connect(POINTS_DB, timeout=15) as db:
        db.execute('UPDATE wallets SET frozen=1 WHERE app_name=? AND code_id=?', (APP, saved['codeId']))
        row = db.execute('SELECT frozen FROM wallets WHERE app_name=? AND code_id=?', (APP, saved['codeId'])).fetchone()
        active = db.execute("SELECT count(*) FROM por_v2_attempts WHERE app_name=? AND code_id=? AND state='running'", (APP, saved['codeId'])).fetchone()[0]
    print(json.dumps({'disabled': True, 'wallet_frozen': not row or row[0] == 1, 'active_requests': active}))


if __name__ == '__main__':
    main()
