"""Deploy the reviewed V2 code only; run with python3 -B as root.

--check-only is read-only. Keys, environment, tariff and balances are never
edited. The SQLite snapshot is audit evidence and is NEVER restored on rollback.
New requests are gated in the existing Nginx snippet while old requests drain.
"""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid


ROOT = Path("/opt/product-operation-report")
BACKUPS = Path("/etc/product-operation-report/backups")
NGINX = Path("/etc/nginx/snippets/product-operation-report-locations.conf")
SERVICE = "product-report-proxy.service"
MODEL = "doubao-seed-2-1-pro-260915"
PORT = 8794
DRAIN_TIMEOUT = 180
BASELINES = {
    "product_report_proxy.py": "2088ab1946db56604e3112d81b7ae9f6cea0f23e1c14d368521f337d4a6a995c",
    "por_billing_v2.py": "cac94aad505ab2fb9ef693881f22db034d92c2d537b4e8c5a43fb746327d9e97",
}
PREFIX = "/api/product-operation-report/v1/"
EXPECTED_LOCATIONS = {("=", PREFIX + suffix) for suffix in (
    "health", "session", "wallet", "wallet/redeem", "chat/completions",
    "billing/result/confirm", "billing/result/reject",
)} | {("^~", PREFIX)}
LOCATION = re.compile(r"^([ \t]*)location[ \t]+(=|\^~)[ \t]+([^\s{]+)[ \t]*\{[ \t]*(?:#.*)?$")
GATE_MARKER = "temporary POR review deployment gate"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.resolve() != path:
        raise RuntimeError("unexpected file or symlink: " + str(path))
    return info


def run(command, timeout=30):
    result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        # Do not print service configuration or other command output.
        raise RuntimeError("command failed: " + " ".join(command))


def service_active():
    return subprocess.run(["systemctl", "is-active", "--quiet", SERVICE],
                          capture_output=True, timeout=10, check=False).returncode == 0


def atomic(path, data, info=None):
    fd, name = tempfile.mkstemp(prefix=".por-review-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode) if info else 0o600)
            os.fchown(stream.fileno(), info.st_uid if info else 0, info.st_gid if info else 0)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def replace_checked(path, data, expected, info):
    regular(path)
    if digest(path.read_bytes()) != expected:
        raise RuntimeError("file changed concurrently; preserved: " + str(path))
    atomic(path, data, info)


def gated_nginx(original):
    if GATE_MARKER.encode() in original:
        raise RuntimeError("an earlier deployment gate is still present; no writes")
    lines = original.decode("utf-8").splitlines(keepends=True)
    found = []
    output = []
    for line in lines:
        output.append(line)
        if not re.match(r"^[ \t]*location\b", line):
            continue
        match = LOCATION.fullmatch(line.rstrip("\r\n"))
        if match is None:
            raise RuntimeError("unrecognized Nginx location; no writes")
        indent, modifier, route = match.groups()
        found.append((modifier, route))
        if route != PREFIX + "health":
            ending = "\r\n" if line.endswith("\r\n") else "\n"
            if not line.endswith(("\n", "\r")):
                output.append(ending)
            output.append(indent + "    return 503; # " + GATE_MARKER + ending)
    if len(found) != len(EXPECTED_LOCATIONS) or set(found) != EXPECTED_LOCATIONS:
        raise RuntimeError("Nginx business routes changed since inspection; no writes")
    return "".join(output).encode("utf-8")


def active_requests():
    path = ROOT / "points.sqlite3"
    regular(path)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as db:
        legacy = db.execute("SELECT COUNT(*) FROM model_requests WHERE status='running'").fetchone()[0]
        precise = db.execute("SELECT COUNT(*) FROM por_v2_attempts WHERE state='running'").fetchone()[0]
    return legacy + precise


def established_connections():
    count = 0
    for name in ("tcp", "tcp6"):
        path = Path("/proc/net") / name
        if name == "tcp6" and not path.exists():
            continue
        for line in path.read_text(encoding="ascii").splitlines()[1:]:
            fields = line.split()
            if len(fields) < 4:
                raise RuntimeError("unexpected TCP connection table")
            if int(fields[1].rsplit(":", 1)[1], 16) == PORT and fields[3] == "01":
                count += 1
    return count


def drain():
    deadline, idle_since = time.monotonic() + DRAIN_TIMEOUT, None
    print("DRAINING_EXISTING_REQUESTS", flush=True)
    while True:
        now = time.monotonic()
        if active_requests() == 0 and established_connections() == 0:
            idle_since = now if idle_since is None else idle_since
            if now - idle_since >= 3:
                return
        else:
            idle_since = None
        if now >= deadline:
            raise RuntimeError("existing requests did not drain within 180 seconds")
        time.sleep(0.25)


def health_once():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as response:
        health = json.loads(response.read(64 * 1024))
        if (response.status != 200 or health.get("models") != [MODEL]
                or health.get("precise_billing_enabled") is not True
                or health.get("precise_admission_enabled") is not True
                or health.get("provider_keyring", {}).get("reload_status") != "loaded"):
            raise RuntimeError("service health contract did not pass")
    return {"models": health["models"], "precise_billing_enabled": True,
            "precise_admission_enabled": True, "provider_status": "loaded"}


def wait_healthy():
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if service_active():
                return health_once()
        except (OSError, ValueError, RuntimeError):
            pass
        time.sleep(0.25)
    raise RuntimeError("service health did not pass within 30 seconds")


def nginx_reload():
    run(["nginx", "-t"])
    run(["systemctl", "reload", "nginx"])


def snapshot_database(destination):
    deadline = time.monotonic() + 60

    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise RuntimeError("audit database snapshot timed out")

    with sqlite3.connect((ROOT / "points.sqlite3").as_uri() + "?mode=ro", uri=True, timeout=5) as source:
        with sqlite3.connect(destination) as target:
            source.backup(target, pages=256, progress=progress, sleep=0.05)
    os.chmod(destination, 0o600)


def deploy(check_only=False):
    source = Path(__file__).resolve().parent
    originals, replacements, metadata = {}, {}, {}
    for name, expected in BASELINES.items():
        target = ROOT / name
        metadata[name] = regular(target)
        originals[name] = target.read_bytes()
        if digest(originals[name]) != expected:
            raise RuntimeError("production baseline changed; no writes: " + name)
        local = source / name
        regular(local)
        replacements[name] = local.read_bytes()
        ast.parse(replacements[name], filename=name)
    nginx_info = regular(NGINX)
    original_nginx = NGINX.read_bytes()
    gated = gated_nginx(original_nginx)
    before_hash, gated_hash = digest(original_nginx), digest(gated)
    if not service_active():
        raise RuntimeError("production service is not active; no writes")
    health = health_once()
    running, connections = active_requests(), established_connections()
    report = {"service": SERVICE, "source_sha256": {name: digest(data) for name, data in replacements.items()},
              "baseline_sha256": BASELINES, "nginx_before_sha256": before_hash,
              "nginx_gated_sha256": gated_hash, "health": health,
              "running_requests": running, "established_connections": connections}
    if check_only:
        print("CHECK_ONLY_OK " + json.dumps(report, sort_keys=True), flush=True)
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUPS / ("review-fixes-" + stamp + "-" + uuid.uuid4().hex[:8])
    if BACKUPS.resolve() != BACKUPS:
        raise RuntimeError("unexpected backup parent symlink; no writes")
    backup.mkdir(mode=0o700, parents=True)
    for name, data in originals.items():
        atomic(backup / ("before-" + name), data)
    atomic(backup / "nginx-before.conf", original_nginx)
    atomic(backup / "nginx-gated.conf", gated)
    report.update({"created_at": stamp, "rollback_database": False,
                   "file_metadata": {name: {"mode": stat.S_IMODE(info.st_mode),
                                            "uid": info.st_uid, "gid": info.st_gid}
                                     for name, info in {**metadata, "nginx": nginx_info}.items()}})
    atomic(backup / "manifest.json", json.dumps(report, indent=2, sort_keys=True).encode())
    snapshot_database(backup / "points.sqlite3.before")
    print("BACKUP " + str(backup), flush=True)

    gate_attempted = service_touched = False
    attempted_files = []

    def ensure_gate():
        regular(NGINX)
        current = digest(NGINX.read_bytes())
        if current == before_hash:
            replace_checked(NGINX, gated, before_hash, nginx_info)
        elif current != gated_hash:
            raise RuntimeError("Nginx changed concurrently; administrator changes preserved")
        nginx_reload()

    def restore_nginx():
        regular(NGINX)
        current = digest(NGINX.read_bytes())
        if current == gated_hash:
            replace_checked(NGINX, original_nginx, gated_hash, nginx_info)
        elif current != before_hash:
            raise RuntimeError("Nginx changed concurrently; administrator changes preserved")
        nginx_reload()

    try:
        # Recheck both code baselines before beginning the maintenance window.
        for name, expected in BASELINES.items():
            regular(ROOT / name)
            if digest((ROOT / name).read_bytes()) != expected:
                raise RuntimeError("production code changed during backup; no deployment writes")
        gate_attempted = True
        ensure_gate()
        drain()
        service_touched = True
        run(["systemctl", "stop", SERVICE])
        if service_active() or active_requests() or established_connections():
            raise RuntimeError("service did not stop cleanly after draining")
        for name, data in replacements.items():
            attempted_files.append(name)
            replace_checked(ROOT / name, data, BASELINES[name], metadata[name])
        run(["systemctl", "start", SERVICE])
        health = wait_healthy()
        for name, data in replacements.items():
            regular(ROOT / name)
            if digest((ROOT / name).read_bytes()) != digest(data):
                raise RuntimeError("deployed code changed during health verification")
        atomic(backup / "validated.json", json.dumps({"health": health,
            "source_sha256": report["source_sha256"], "database_restored": False}, sort_keys=True).encode())
        restore_nginx()
    except BaseException:
        try:
            if service_touched:
                # The original snippet may already have been written if its
                # reload failed. Gate again before stopping a live process.
                ensure_gate()
                drain()
                run(["systemctl", "stop", SERVICE])
                for name in attempted_files:
                    path = ROOT / name
                    regular(path)
                    current = digest(path.read_bytes())
                    if current == digest(replacements[name]):
                        replace_checked(path, originals[name], current, metadata[name])
                    elif current != BASELINES[name]:
                        raise RuntimeError("code changed concurrently; administrator changes preserved: " + name)
                run(["systemctl", "start", SERVICE])
                wait_healthy()
            if gate_attempted:
                restore_nginx()
            print("ROLLBACK_OK database_restored=false", flush=True)
        except BaseException as rollback_error:
            print("ROLLBACK_INCOMPLETE " + type(rollback_error).__name__ + " " +
                  (str(rollback_error) if isinstance(rollback_error, RuntimeError) else "details suppressed") +
                  " backup=" + str(backup), flush=True)
        raise
    print("DEPLOYMENT_OK " + json.dumps({"backup": str(backup), "health": health,
          "sha256": report["source_sha256"], "database_restored": False}, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    options = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("run on the production Linux host as root")
    import fcntl

    def interrupted(signum, frame):
        # Let the first interruption unwind through rollback, and protect that
        # rollback from a second ordinary signal. SIGKILL cannot be recovered.
        for item in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(item, signal.SIG_IGN)
        raise RuntimeError("deployment interrupted by signal " + str(signum))

    for item in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(item, interrupted)
    # A directory lock coordinates this script without creating a lock file.
    directory = os.open(ROOT, os.O_RDONLY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old_umask = os.umask(0o077)
        try:
            deploy(options.check_only)
        finally:
            os.umask(old_umask)
    finally:
        os.close(directory)


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        if isinstance(error, SystemExit):
            raise
        print("DEPLOYMENT_FAILED " + type(error).__name__ + " " +
              (str(error) if isinstance(error, RuntimeError) else "details suppressed"), flush=True)
        sys.exit(1)
