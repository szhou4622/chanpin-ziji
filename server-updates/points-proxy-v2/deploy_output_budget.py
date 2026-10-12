"""Change an explicitly verified environment token ceiling safely.

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
    parser.add_argument('--from-tokens', required=True, type=int)
    parser.add_argument('--to-tokens', required=True, type=int)
    options = parser.parse_args()
    if not 1024 <= options.from_tokens <= 32768 or not 1024 <= options.to_tokens <= 32768:
        raise RuntimeError('budget is outside the supported bounded range')
    if os.geteuid() != 0:
        raise RuntimeError('run as root on the production host')
    directory = os.open(deploy.ROOT, os.O_RDONLY)
    fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
    target = Path('/etc/product-operation-report/proxy.env')
    info = deploy.regular(target)
    original = target.read_bytes()
    if len(re.findall(rb'^POR_MAX_OUTPUT_TOKENS=.*$', original, re.M)) != 1:
        raise RuntimeError('unexpected output budget assignments')
    expected = str(options.from_tokens).encode()
    requested = str(options.to_tokens).encode()
    replacement, count = re.subn(rb'^POR_MAX_OUTPUT_TOKENS=' + expected + rb'(\r?)$',
        lambda match: b'POR_MAX_OUTPUT_TOKENS=' + requested + match.group(1), original, flags=re.M)
    if count != 1 or running_budget() != str(options.from_tokens):
        raise RuntimeError('running or persisted budget differs; no writes')
    for suffix in ('precise-proxy.env', 'ark-proxy.env'):
        if re.search(rb'^POR_MAX_OUTPUT_TOKENS=', target.with_name(suffix).read_bytes(), re.M):
            raise RuntimeError('a later environment file overrides the budget')
    nginx_info = deploy.regular(deploy.NGINX)
    nginx = deploy.NGINX.read_bytes()
    gated = deploy.gated_nginx(nginx)
    deploy.health_once()
    if options.check_only:
        print(json.dumps({'check_only': True, 'from': options.from_tokens, 'to': options.to_tokens,
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
        if running_budget() != str(options.to_tokens):
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
    evidence = {'running_max_output_tokens': options.to_tokens, 'backup': str(backup),
                'only_assignment_changed': True, 'nginx_restored': deploy.digest(deploy.NGINX.read_bytes()) == deploy.digest(nginx)}
    deploy.atomic(backup / 'verification.json', json.dumps(evidence).encode())
    print(json.dumps(evidence), flush=True)


if __name__ == '__main__':
    main()
