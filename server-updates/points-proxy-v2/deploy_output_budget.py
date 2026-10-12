"""Raise the verified 6,000-token environment ceiling to 12,000 safely.

Run beside deploy_review_fixes.py on the proxy host. Only one environment
assignment changes. Preserve an audit backup, gate/drain requests, restart and
verify the actual running process value; never edit keys, tariffs or balances.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone
import uuid

import deploy_review_fixes as deploy


def running_budget():
    pid = subprocess.check_output(['systemctl', 'show', deploy.SERVICE, '-p', 'MainPID', '--value'], text=True).strip()
    values = dict(item.split(b'=', 1) for item in Path('/proc/' + pid + '/environ').read_bytes().split(b'\0') if b'=' in item)
    return values.get(b'POR_MAX_OUTPUT_TOKENS', b'').decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    options = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('run as root on the production host')
    directory = os.open(deploy.ROOT, os.O_RDONLY)
    fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
    target = Path('/etc/product-operation-report/proxy.env')
    info = deploy.regular(target)
    original = target.read_bytes()
    if len(re.findall(rb'^POR_MAX_OUTPUT_TOKENS=.*$', original, re.M)) != 1:
        raise RuntimeError('unexpected output budget assignments')
    replacement, count = re.subn(rb'^POR_MAX_OUTPUT_TOKENS=6000(\r?)$', rb'POR_MAX_OUTPUT_TOKENS=12000\1', original, flags=re.M)
    if count != 1 or running_budget() != '6000':
        raise RuntimeError('running or persisted budget differs; no writes')
    for suffix in ('precise-proxy.env', 'ark-proxy.env'):
        if re.search(rb'^POR_MAX_OUTPUT_TOKENS=', target.with_name(suffix).read_bytes(), re.M):
            raise RuntimeError('a later environment file overrides the budget')
    nginx_info = deploy.regular(deploy.NGINX)
    nginx = deploy.NGINX.read_bytes()
    gated = deploy.gated_nginx(nginx)
    deploy.health_once()
    if options.check_only:
        print(json.dumps({'check_only': True, 'from': 6000, 'to': 12000,
                          'running_requests': deploy.active_requests()}), flush=True)
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = deploy.BACKUPS / ('output-budget-' + stamp + '-' + uuid.uuid4().hex[:8])
    backup.mkdir(mode=0o700)
    deploy.atomic(backup / 'proxy.env.before', original)
    deploy.atomic(backup / 'nginx.before', nginx)
    try:
        deploy.replace_checked(deploy.NGINX, gated, deploy.digest(nginx), nginx_info)
        deploy.nginx_reload()
        deploy.drain()
        deploy.replace_checked(target, replacement, deploy.digest(original), info)
        deploy.run(['systemctl', 'restart', deploy.SERVICE])
        deploy.wait_healthy()
        if running_budget() != '12000':
            raise RuntimeError('new running budget was not applied')
        deploy.replace_checked(deploy.NGINX, nginx, deploy.digest(gated), nginx_info)
        deploy.nginx_reload()
    except BaseException:
        if deploy.digest(target.read_bytes()) == deploy.digest(replacement):
            deploy.replace_checked(target, original, deploy.digest(replacement), info)
            deploy.run(['systemctl', 'restart', deploy.SERVICE])
            deploy.wait_healthy()
        if deploy.digest(deploy.NGINX.read_bytes()) == deploy.digest(gated):
            deploy.replace_checked(deploy.NGINX, nginx, deploy.digest(gated), nginx_info)
            deploy.nginx_reload()
        raise
    evidence = {'running_max_output_tokens': 12000, 'backup': str(backup),
                'only_assignment_changed': True, 'nginx_restored': deploy.digest(deploy.NGINX.read_bytes()) == deploy.digest(nginx)}
    deploy.atomic(backup / 'verification.json', json.dumps(evidence).encode())
    print(json.dumps(evidence), flush=True)


if __name__ == '__main__':
    main()
