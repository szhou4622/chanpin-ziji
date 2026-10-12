#!/usr/bin/env python3
"""ProductOperationReport business proxy.

Provider credentials and the authoritative points ledger live here. The desktop
client receives only short-lived random session tokens. This service stores no
prompts, source files, images, or model output.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import math
import os
import queue
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from provider_keyring import ProviderKeyring, ProviderRouteSnapshot
import por_billing_v2 as billing_v2
from provider_config import MANAGED_MODEL, ARK_BASE_URL, ARK_MODEL_PRICES_CNY, ALLOWED_MODELS


APP_NAME = "ProductOperationReport"
HOST = os.environ.get("POR_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("POR_PROXY_PORT", "8794"))
DB_PATH = os.environ.get("POR_POINTS_DB", "/opt/product-operation-report/points.sqlite3")
LICENSE_DB_PATH = os.environ.get(
    "POR_LICENSE_DB", "/opt/original-video-dedup-tool/server/license_server.sqlite3"
)
LICENSE_STATUS_URL = os.environ.get(
    "POR_LICENSE_STATUS_URL", "http://127.0.0.1:8791/api/license/device/status"
)
LICENSE_ACTIVATE_URL = os.environ.get(
    "POR_LICENSE_ACTIVATE_URL", "http://127.0.0.1:8791/api/license/activate"
)
LICENSE_CONSUME_URL = os.environ.get(
    "POR_LICENSE_CONSUME_URL", "http://127.0.0.1:8791/api/license/credits/consume"
)
PRECISE_BILLING_ENABLED = os.environ.get("POR_PRECISE_BILLING_V2", "0").strip() == "1"
PRECISE_ADMISSION_ENABLED = os.environ.get("POR_PRECISE_ADMISSION", "1").strip() == "1"
PRECISE_BALANCE_URL = os.environ.get(
    "POR_PRECISE_BALANCE_URL", "http://127.0.0.1:8791/api/license/credits/precise/balance"
)
PRECISE_CONSUME_URL = os.environ.get(
    "POR_PRECISE_CONSUME_URL", "http://127.0.0.1:8791/api/license/credits/precise/consume"
)
PRECISE_INTERNAL_TOKEN = os.environ.get("POR_PRECISE_INTERNAL_TOKEN", "").strip()
PRECISE_BILLING_SOURCE = os.environ.get("POR_PRECISE_BILLING_SOURCE", "pending").strip()
PRECISE_TARIFF_VERSION = os.environ.get("POR_PRECISE_TARIFF_VERSION", "").strip()
PRECISE_TARIFF_FILE = os.environ.get(
    "POR_PRECISE_TARIFF_FILE", "/etc/product-operation-report/pricing/ccg-vip-2026-08-03.json"
).strip()
PRECISE_TARIFF_SHA256 = os.environ.get("POR_PRECISE_TARIFF_SHA256", "").strip().lower()
PROVIDER_BASE_URL = os.environ.get("POR_PROVIDER_BASE_URL", ARK_BASE_URL).rstrip("/")
PROVIDER_API_KEY = os.environ.get("POR_PROVIDER_API_KEY", "").strip()
PROVIDER_KEYS_FILE = os.environ.get(
    "POR_PROVIDER_KEYS_FILE", "/etc/product-operation-report/provider-keys.json"
).strip()
SESSION_TTL_SECONDS = max(120, min(3600, int(os.environ.get("POR_SESSION_TTL_SECONDS", "900"))))
DAILY_COST_LIMIT_CNY = max(1.0, float(os.environ.get("POR_DAILY_COST_LIMIT_CNY", "100")))
USD_CNY_RATE = max(1.0, float(os.environ.get("POR_USD_CNY_RATE", "7.2")))
POINTS_PER_CNY = max(1.0, float(os.environ.get("POR_POINTS_PER_CNY", "100")))
COST_RATE = max(0.01, min(1.0, float(os.environ.get("POR_COST_RATE", "0.5"))))
CHARGE_MULTIPLIER = 1.0 / COST_RATE
WEB_SEARCH_USD_PER_CALL = max(0.0, float(os.environ.get("POR_WEB_SEARCH_USD_PER_CALL", str(0.004 / USD_CNY_RATE))))
WEB_SEARCH_REPORT_LIMIT = max(1, min(50, int(os.environ.get("POR_WEB_SEARCH_REPORT_LIMIT", "14"))))
MAX_BODY_BYTES = 96 * 1024 * 1024
MAX_MESSAGES = 64
MAX_TEXT_CHARS = 2_000_000
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_ACTIVE_PER_LICENSE = 4
MAX_OUTPUT_TOKENS = max(1024, min(32768, int(os.environ.get("POR_MAX_OUTPUT_TOKENS", "12000"))))
TASK_OUTPUT_RESERVES = {
    "source_clean": 2_500,
    "summary": 3_500,
    "analysis_step": 4_000,
    "final_part": MAX_OUTPUT_TOKENS,
    "revision_part": MAX_OUTPUT_TOKENS,
    "module_product_info": 5000,
    "module_platform_audience": 8000,
    "module_material_review": 10000,
    "module_benchmark": 5000,
    "module_selling_points": 7000,
    "module_voc": 10000,
    "module_ranking": 10000,
    "module_audience_sp_scene": 10000,
}
STREAM_HEARTBEAT_SECONDS = 20.0
REQUEST_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?::fallback:[1-3])?$", re.I)
SAFE_TEXT_RE = re.compile(r"^[\w.:-]{1,200}$", re.UNICODE)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LEGACY_MODEL_ALIASES = ("gpt-5.5", "gpt-5.6-sol", "claude-sonnet-4-6", "gemini-3-flash", "kimi-k2.6")
ALLOWED_TASK_TYPES = (
    "source_clean", "summary", "analysis_step", "final_part", "revision_part",
    "module_product_info", "module_platform_audience", "module_material_review",
    "module_benchmark", "module_selling_points", "module_voc", "module_ranking",
    "module_audience_sp_scene",
)
MODEL_PRICES = {
    MANAGED_MODEL: tuple(rate / USD_CNY_RATE for rate in ARK_MODEL_PRICES_CNY),
    "gpt-5.5": (1.25, 7.5, 0.125, 0.8),
    "gpt-5.6-sol": (1.25, 10.0, 0.125, 1.0),
    "claude-sonnet-4-6": (0.4, 2.0, 0.04, 0.2),
    "gemini-3-flash": (1.2, 6.0, 0.12, 0.6),
    "kimi-k2.6": (0.8, 4.0, 0.08, 0.4),
}
MODEL_ENV_PREFIXES = {MANAGED_MODEL: "DOUBAO_SEED_21_PRO"}
TASK_MODEL_ROUTES = {"module_benchmark": (MANAGED_MODEL,)}
PROVIDER_ROUTES = {
    model: (
        os.environ.get(f"POR_PROVIDER_{prefix}_BASE_URL", PROVIDER_BASE_URL).rstrip("/"),
        os.environ.get(f"POR_PROVIDER_{prefix}_API_KEY", PROVIDER_API_KEY).strip(),
    )
    for model, prefix in MODEL_ENV_PREFIXES.items()
}
PROVIDER_KEYRING = ProviderKeyring(PROVIDER_KEYS_FILE, PROVIDER_ROUTES, ALLOWED_MODELS)
LEGACY_NAMESPACE = "product-operation-report:activation:v1:"


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Session:
    token_hash: str
    code_id: str
    machine_code: str
    license_id: str
    device_credential: str
    device_session: str
    expires_at: float
    unlimited: bool = False
    client_version: str = ""


SESSIONS: dict[str, Session] = {}
SESSION_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), mode=0o700, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=20000")
    return db


@contextmanager
def database():
    db = connection()
    try:
        yield db
    finally:
        db.close()


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS wallets (
          app_name TEXT NOT NULL,
          code_id TEXT NOT NULL,
          machine_code TEXT NOT NULL,
          balance_milli INTEGER NOT NULL,
          locked_milli INTEGER NOT NULL DEFAULT 0,
          total_topup_milli INTEGER NOT NULL DEFAULT 0,
          total_cost_milli INTEGER NOT NULL DEFAULT 0,
          total_charged_milli INTEGER NOT NULL DEFAULT 0,
          frozen INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(app_name, code_id)
        );
        CREATE TABLE IF NOT EXISTS ledger (
          event_id TEXT PRIMARY KEY,
          app_name TEXT NOT NULL,
          code_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          description TEXT NOT NULL,
          points_delta_milli INTEGER NOT NULL,
          balance_after_milli INTEGER NOT NULL,
          report_session_id TEXT,
          task_type TEXT,
          request_id TEXT,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ledger_wallet ON ledger(app_name, code_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS topup_redemptions (
          app_name TEXT NOT NULL,
          topup_code_id TEXT NOT NULL,
          wallet_code_id TEXT NOT NULL,
          points_milli INTEGER NOT NULL,
          machine_code TEXT NOT NULL,
          redeemed_at TEXT NOT NULL,
          PRIMARY KEY(app_name, topup_code_id)
        );
        CREATE TABLE IF NOT EXISTS model_requests (
          request_id TEXT PRIMARY KEY,
          app_name TEXT NOT NULL,
          code_id TEXT NOT NULL,
          machine_code TEXT NOT NULL,
          report_session_id TEXT NOT NULL,
          task_key TEXT NOT NULL,
          task_type TEXT NOT NULL,
          model TEXT NOT NULL,
          attempt INTEGER NOT NULL,
          status TEXT NOT NULL,
          reserved_milli INTEGER NOT NULL,
          input_estimate INTEGER NOT NULL DEFAULT 0,
          upstream_submitted INTEGER NOT NULL DEFAULT 0,
          input_tokens INTEGER NOT NULL DEFAULT 0,
          output_tokens INTEGER NOT NULL DEFAULT 0,
          cached_input_tokens INTEGER NOT NULL DEFAULT 0,
          cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0,
          usage_source TEXT NOT NULL DEFAULT 'missing',
          response_model TEXT NOT NULL DEFAULT '',
          cost_cny REAL NOT NULL DEFAULT 0,
          charged_milli INTEGER NOT NULL DEFAULT 0,
          started_at TEXT NOT NULL,
          ended_at TEXT
          ,billing_request_id TEXT NOT NULL DEFAULT ''
          ,billing_result_status TEXT NOT NULL DEFAULT ''
          ,billing_error TEXT NOT NULL DEFAULT ''
          ,search_calls INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_requests_wallet_status
          ON model_requests(app_name, code_id, status, started_at);
        CREATE INDEX IF NOT EXISTS idx_requests_day
          ON model_requests(status, started_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_task_attempt
          ON model_requests(app_name, code_id, task_key, attempt, model);
        """
    )
    request_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(model_requests)")}
    if "input_estimate" not in request_columns:
        db.execute("ALTER TABLE model_requests ADD COLUMN input_estimate INTEGER NOT NULL DEFAULT 0")
    if "upstream_submitted" not in request_columns:
        db.execute("ALTER TABLE model_requests ADD COLUMN upstream_submitted INTEGER NOT NULL DEFAULT 0")
    if "response_model" not in request_columns:
        db.execute("ALTER TABLE model_requests ADD COLUMN response_model TEXT NOT NULL DEFAULT ''")
    if "billing_request_id" not in request_columns:
        db.execute("ALTER TABLE model_requests ADD COLUMN billing_request_id TEXT NOT NULL DEFAULT ''")
    if "billing_result_status" not in request_columns:
        db.execute("ALTER TABLE model_requests ADD COLUMN billing_result_status TEXT NOT NULL DEFAULT ''")
    if "billing_error" not in request_columns:
        db.execute("ALTER TABLE model_requests ADD COLUMN billing_error TEXT NOT NULL DEFAULT ''")
    if "search_calls" not in request_columns:
        db.execute("ALTER TABLE model_requests ADD COLUMN search_calls INTEGER NOT NULL DEFAULT 0")


def as_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError(400, "请求格式不正确。")
    return value


def text(value: Any, maximum: int = 512) -> str:
    return value.strip()[:maximum] if isinstance(value, str) and value.strip() else ""


def parse_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 10_000_000 else None


LICENSE_CONTRACT_FIELDS = {
    "ok", "success", "valid", "activated", "app_name", "code_id", "license_id",
    "activation_id", "code_role", "machine_code", "bound_machine_code", "device_id",
    "binding_status", "remaining_points", "remaining_credits", "credits_remaining",
    "wallet_balance", "points_balance", "credits", "points", "initial_credits", "granted_credits",
}


def has_nested_contract_field(value: Any, depth: int = 0) -> bool:
    if depth > 6:
        return True
    if isinstance(value, dict):
        if any(key in LICENSE_CONTRACT_FIELDS for key in value):
            return True
        return any(has_nested_contract_field(child, depth + 1) for child in value.values())
    if isinstance(value, list):
        return any(has_nested_contract_field(child, depth + 1) for child in value)
    return False


def parse_license_response(
    result: dict[str, Any],
    status: int,
    expected_machine: str,
    allowed_roles: set[str],
    default_role: str = "",
) -> tuple[str, int, str]:
    forbidden_top_level_aliases = {
        "success", "valid", "activated", "license_id", "activation_id",
        "bound_machine_code", "device_id", "credits_remaining",
        "wallet_balance", "points_balance", "credits", "points", "initial_credits", "granted_credits",
    }
    if forbidden_top_level_aliases.intersection(result):
        raise ApiError(503, "授权服务器返回了非标准或冲突字段。")
    message = text(result.get("message") or result.get("error"), 240)
    if status < 200 or status >= 300:
        raise ApiError(403 if status < 500 else 503, message or "当前设备授权已失效。")
    if any(has_nested_contract_field(child) for child in result.values() if isinstance(child, (dict, list))):
        raise ApiError(503, "授权服务器返回了有歧义的嵌套字段。")
    if result.get("ok") is not True:
        raise ApiError(403, message or "授权服务器未确认本次授权。")

    binding = text(result.get("binding_status"), 32).lower()
    if binding not in {"active", "bound"}:
        raise ApiError(403, message or "当前设备授权不是可用状态。")

    response_app = text(result.get("app_name"), 80)
    if response_app != APP_NAME:
        raise ApiError(403, "授权不属于当前软件。")

    response_machine = text(result.get("machine_code"), 200)
    normalized_response_machine = response_machine.strip().lower()
    normalized_expected_machine = expected_machine.strip().lower()
    if not normalized_response_machine or not hmac.compare_digest(
        normalized_response_machine, normalized_expected_machine
    ):
        raise ApiError(403, "授权绑定的电脑不一致。")

    code_id = text(result.get("code_id"), 200)
    if not code_id:
        raise ApiError(503, "授权服务器没有返回稳定的授权标识。")

    role = text(result.get("code_role"), 40).lower() or text(default_role, 40).lower()
    if role not in allowed_roles:
        raise ApiError(403, "该激活码用途不匹配，不能在这里使用。")

    has_credits = "remaining_credits" in result
    has_legacy_points = "remaining_points" in result
    if not has_credits and not has_legacy_points:
        raise ApiError(503, "授权服务器没有返回当前剩余积分。")
    credits = parse_nonnegative(result.get("remaining_credits")) if has_credits else None
    legacy_points = parse_nonnegative(result.get("remaining_points")) if has_legacy_points else None
    if (has_credits and credits is None) or (has_legacy_points and legacy_points is None):
        raise ApiError(503, "授权服务器返回的剩余积分无效。")
    if has_credits and has_legacy_points and credits != legacy_points:
        raise ApiError(503, "授权服务器返回了相互冲突的积分余额。")
    points = credits if has_credits else legacy_points
    if points is None:
        raise ApiError(503, "授权服务器没有返回当前剩余积分。")
    return code_id, round(points * 1000), role


def verify_license(identity: dict[str, Any]) -> tuple[str, int, str, bool]:
    app_name = text(identity.get("app_name"), 80)
    machine = text(identity.get("machine_code"), 200)
    license_id = text(identity.get("license_id"), 200)
    credential = text(identity.get("device_credential"), 8192)
    device_session = text(identity.get("device_session"), 8192)
    if app_name != APP_NAME or not machine or not credential or not device_session:
        raise ApiError(401, "当前设备授权信息不完整，请重新激活。")
    status_query = urlencode({
        'app_name': APP_NAME,
        'machine_code': machine,
        'license_id': license_id,
        'software_version': 'proxy',
        'platform': 'server-proxy',
    })
    status_url = f"{LICENSE_STATUS_URL}?{status_query}"
    request = Request(
        status_url, method="GET",
        headers={"Accept": "application/json",
                 "Authorization": f"Bearer {device_session}", "X-Device-Credential": credential},
    )
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read(64 * 1024)
            status = int(response.status)
    except HTTPError as error:
        raw = error.read(64 * 1024)
        status = int(error.code)
    except (URLError, TimeoutError, OSError) as error:
        raise ApiError(503, "授权服务器暂时不可用，请稍后重试。") from error
    try:
        result = as_object(json.loads(raw.decode("utf-8", "replace")))
    except Exception as error:
        raise ApiError(503, "授权服务器返回异常，请联系管理员。") from error
    # /device/status is authenticated by the device session and credential. The
    # current license service only returns primary device records from this
    # endpoint, so use primary as the compatibility default when code_role is
    # absent. Activation/redeem responses still have to provide an explicit role.
    code_id, remaining_milli, role = parse_license_response(
        result, status, machine, {"primary", "legacy_manual"}, default_role="primary"
    )
    unlimited = result.get("unlimited", False)
    if not isinstance(unlimited, bool):
        raise ApiError(503, "授权服务器返回的无限授权状态无效。")
    return code_id, remaining_milli, role, unlimited


def sync_authoritative_wallet(session: Session, balance_milli: int) -> None:
    """Mirror the license balance without treating a refresh as a top-up."""
    with database() as db:
        ensure_schema(db)
        now = utc_now()
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT machine_code FROM wallets WHERE app_name=? AND code_id=?", (APP_NAME, session.code_id)
        ).fetchone()
        if row is None:
            db.execute(
                "INSERT INTO wallets(app_name,code_id,machine_code,balance_milli,total_topup_milli,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (APP_NAME, session.code_id, session.machine_code, balance_milli, balance_milli, now, now),
            )
        else:
            db.execute(
                "UPDATE wallets SET machine_code=?,balance_milli=?,updated_at=? WHERE app_name=? AND code_id=?",
                (session.machine_code, balance_milli, now, APP_NAME, session.code_id),
            )
        db.execute("COMMIT")


def create_session(payload: dict[str, Any]) -> tuple[str, Session]:
    code_id, authoritative_milli, _, unlimited = verify_license(payload)
    machine = text(payload.get("machine_code"), 200)
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
    session = Session(
        token_hash=token_hash, code_id=code_id, machine_code=machine,
        license_id=text(payload.get("license_id"), 200),
        device_credential=text(payload.get("device_credential"), 8192),
        device_session=text(payload.get("device_session"), 8192),
        expires_at=time.time() + SESSION_TTL_SECONDS,
        unlimited=unlimited,
        client_version=text(payload.get("client_version"), 80),
    )
    with database() as db:
        ensure_schema(db)
        now = utc_now()
        db.execute("BEGIN IMMEDIATE")
        topup = db.execute(
            "SELECT wallet_code_id FROM topup_redemptions WHERE app_name=? AND topup_code_id=?",
            (APP_NAME, code_id),
        ).fetchone()
        if topup:
            db.execute("ROLLBACK")
            raise ApiError(403, "这个积分码已经作为充值码使用，不能再激活软件。")
        row = db.execute(
            "SELECT machine_code FROM wallets WHERE app_name=? AND code_id=?", (APP_NAME, code_id)
        ).fetchone()
        if row is None:
            db.execute(
                "INSERT INTO wallets(app_name,code_id,machine_code,balance_milli,total_topup_milli,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (APP_NAME, code_id, machine, authoritative_milli, authoritative_milli, now, now),
            )
            if authoritative_milli:
                db.execute(
                    "INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), APP_NAME, code_id, "topup", "激活码初始积分", authoritative_milli,
                     authoritative_milli, None, None, None, now),
                )
        else:
            # The license service owns both rebind state and the current balance.
            # A refresh is a mirror update, never a new grant or ledger top-up.
            db.execute(
                "UPDATE wallets SET machine_code=?,balance_milli=?,updated_at=? WHERE app_name=? AND code_id=?",
                (machine, authoritative_milli, now, APP_NAME, code_id),
            )
        db.execute("COMMIT")
    with SESSION_LOCK:
        now_ts = time.time()
        for key in [key for key, value in SESSIONS.items() if value.expires_at <= now_ts]:
            SESSIONS.pop(key, None)
        SESSIONS[token_hash] = session
    return raw_token, session


def require_session(headers: Any, verify: bool = False) -> Session:
    authorization = headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise ApiError(401, "缺少业务会话，请重新打开软件。")
    raw_token = authorization[7:].strip()
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    with SESSION_LOCK:
        session = SESSIONS.get(token_hash)
    if not session or session.expires_at <= time.time():
        raise ApiError(401, "业务会话已过期，软件将自动重新连接。")
    with database() as db:
        ensure_schema(db)
        if db.execute(
            "SELECT 1 FROM topup_redemptions WHERE app_name=? AND topup_code_id=?",
            (APP_NAME, session.code_id),
        ).fetchone():
            raise ApiError(403, "这个积分码已经作为充值码使用，不能作为软件授权。")
        wallet = db.execute(
            "SELECT machine_code,frozen FROM wallets WHERE app_name=? AND code_id=?",
            (APP_NAME, session.code_id),
        ).fetchone()
        if not wallet or wallet["frozen"] or not hmac.compare_digest(str(wallet["machine_code"]), session.machine_code):
            raise ApiError(403, "当前电脑已不再持有这份授权，请重新激活。")
    if verify:
        code_id, authoritative_milli, _, unlimited = verify_license({
            "app_name": APP_NAME, "machine_code": session.machine_code,
            "license_id": session.license_id, "device_credential": session.device_credential,
            "device_session": session.device_session,
        })
        if not hmac.compare_digest(code_id, session.code_id):
            raise ApiError(403, "授权标识已变化，请重新激活。")
        session.unlimited = unlimited
        sync_authoritative_wallet(session, authoritative_milli)
        if not PRECISE_BILLING_ENABLED:
            retry_pending_billing(session)
    return session


def milli_to_points(value: int) -> float | int:
    return value // 1000 if value % 1000 == 0 else round(value / 1000, 3)


def billing_consume_request_id(billing_request_id: str) -> str:
    value = text(billing_request_id, 240)
    if not value or not SAFE_TEXT_RE.fullmatch(value):
        raise ApiError(400, "模型计费任务标识无效。")
    return "por-" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def consume_authoritative_credits(
    session: Session, amount_milli: int, billing_request_id: str, reason: str
) -> tuple[int, bool]:
    if amount_milli <= 0:
        _, remaining_milli, _, unlimited = verify_license({
            "app_name": APP_NAME,
            "machine_code": session.machine_code,
            "license_id": session.license_id,
            "device_credential": session.device_credential,
            "device_session": session.device_session,
        })
        return remaining_milli, unlimited
    if amount_milli % 1000:
        raise ApiError(503, "结算积分不是整数，已阻止不一致扣费。")
    payload = json.dumps({
        "license_protocol_version": 2,
        "app_name": APP_NAME,
        "amount": milli_to_points(amount_milli),
        "reason": text(reason, 120) or "product_operation_report",
        "request_id": billing_consume_request_id(billing_request_id),
        "client_version": "proxy",
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        LICENSE_CONSUME_URL,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {session.device_session}",
            "X-Device-Credential": session.device_credential,
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(64 * 1024)
            status = int(response.status)
    except HTTPError as error:
        raw = error.read(64 * 1024)
        status = int(error.code)
    except (URLError, TimeoutError, OSError) as error:
        raise ApiError(503, "积分结算服务器暂时不可用，本次任务已进入待结算状态。") from error
    try:
        result = as_object(json.loads(raw.decode("utf-8", "replace")))
    except Exception as error:
        raise ApiError(503, "积分结算服务器返回异常，本次任务已进入待结算状态。") from error
    if status < 200 or status >= 300 or result.get("ok") is not True:
        message = text(result.get("message") or result.get("error"), 300)
        raise ApiError(status if status >= 400 else 503, message or "积分结算失败，本次任务已进入待结算状态。")
    response_app = text(result.get("app_name"), 80)
    if response_app and response_app != APP_NAME:
        raise ApiError(503, "积分结算响应的软件标识不匹配。")
    response_code_id = text(result.get("code_id"), 200)
    if response_code_id and not hmac.compare_digest(response_code_id, session.code_id):
        raise ApiError(503, "积分结算响应的授权标识不匹配。")
    if "remaining_credits" not in result:
        raise ApiError(503, "积分结算响应缺少当前剩余积分。")
    remaining = parse_nonnegative(result.get("remaining_credits"))
    unlimited = result.get("unlimited", False)
    if remaining is None or not isinstance(unlimited, bool):
        raise ApiError(503, "积分结算响应格式无效。")
    return round(remaining * 1000), unlimited


def precise_license_request(session: Session, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not PRECISE_INTERNAL_TOKEN:
        raise ApiError(503, "精确积分服务未配置，已停止本次结算。")
    request = Request(
        url,
        data=(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
              if payload is not None else None),
        method="POST" if payload is not None else "GET",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {session.device_session}",
            "X-Device-Credential": session.device_credential,
            "X-POR-Internal-Token": PRECISE_INTERNAL_TOKEN,
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw, status = response.read(64 * 1024), int(response.status)
    except HTTPError as error:
        raw, status = error.read(64 * 1024), int(error.code)
    except (URLError, TimeoutError, OSError) as error:
        raise ApiError(503, "精确积分服务暂时不可用，未产生新的扣费。") from error
    try:
        result = as_object(json.loads(raw.decode("utf-8", "replace")))
    except Exception as error:
        raise ApiError(503, "精确积分服务响应无效，未产生新的扣费。") from error
    if not 200 <= status < 300 or result.get("ok") is not True:
        raise ApiError(status if status >= 400 else 503,
                       text(result.get("message"), 300) or "精确积分服务拒绝结算。")
    if result.get("units_per_point") != billing_v2.UNITS_PER_POINT:
        raise ApiError(503, "精确积分单位不一致，已阻止结算。")
    if type(result.get("remaining_units")) is not int or result["remaining_units"] < 0:
        raise ApiError(503, "精确积分余额无效，已阻止结算。")
    return result


def precise_license_balance(session: Session) -> dict[str, Any]:
    return precise_license_request(session, PRECISE_BALANCE_URL)


def precise_license_consume(
    session: Session, logical_task_id: str, attempt_id: str, amount_units: int,
    billed_model: str, bill_ref: str, cost_cny: str,
) -> dict[str, Any]:
    return precise_license_request(session, PRECISE_CONSUME_URL, {
        "logical_task_id": logical_task_id,
        "attempt_id": attempt_id,
        "amount_units": amount_units,
        "billed_model": billed_model,
        "bill_ref": bill_ref,
        "cost_cny": cost_cny,
    })


def pricing(model: str = MANAGED_MODEL) -> dict[str, Any]:
    values = MODEL_PRICES.get(model, MODEL_PRICES[MANAGED_MODEL])
    return {
        "model": model, "currency": "USD", "inputUsdPerMillion": values[0],
        "outputUsdPerMillion": values[1], "cachedInputUsdPerMillion": values[2],
        "cacheCreationUsdPerMillion": values[3], "usdCnyRate": USD_CNY_RATE,
        "pointsPerCny": POINTS_PER_CNY, "cnyPerCostPoint": 1 / POINTS_PER_CNY,
        "costRate": COST_RATE, "chargeMultiplier": CHARGE_MULTIPLIER,
        "webSearchUsdPerCall": WEB_SEARCH_USD_PER_CALL,
        "webSearchReportLimit": WEB_SEARCH_REPORT_LIMIT,
    }


def wallet_json(session: Session, db: sqlite3.Connection) -> dict[str, Any]:
    row = db.execute(
        "SELECT * FROM wallets WHERE app_name=? AND code_id=?", (APP_NAME, session.code_id)
    ).fetchone()
    if row is None:
        raise ApiError(404, "积分账户尚未建立，请重新激活。")
    ledger_rows = db.execute(
        "SELECT * FROM ledger WHERE app_name=? AND code_id=? ORDER BY created_at DESC LIMIT 100",
        (APP_NAME, session.code_id),
    ).fetchall()
    return {
        "balancePoints": milli_to_points(row["balance_milli"]),
        "unlimited": session.unlimited,
        "totalTopupPoints": milli_to_points(row["total_topup_milli"]),
        "totalCostPoints": milli_to_points(row["total_cost_milli"]),
        "totalChargedPoints": milli_to_points(row["total_charged_milli"]),
        "unbilledUsageCount": db.execute(
            "SELECT COUNT(*) FROM model_requests WHERE app_name=? AND code_id=? AND status='billing_pending'",
            (APP_NAME, session.code_id),
        ).fetchone()[0],
        "pricing": pricing(),
        "ledger": [{
            "id": item["event_id"], "createdAt": item["created_at"], "kind": item["kind"],
            "description": item["description"], "pointsDelta": milli_to_points(item["points_delta_milli"]),
            "balanceAfter": milli_to_points(item["balance_after_milli"]),
            "reportSessionId": item["report_session_id"], "taskType": item["task_type"],
        } for item in ledger_rows],
    }


def wallet_json_v2(session: Session, db: sqlite3.Connection) -> dict[str, Any]:
    billing_v2.ensure_schema(db)
    authoritative = precise_license_balance(session)
    wallet = wallet_json(session, db)
    units = authoritative["remaining_units"]
    wallet["balancePoints"] = units / billing_v2.UNITS_PER_POINT
    wallet["balanceUnits"] = units
    wallet["unitsPerPoint"] = billing_v2.UNITS_PER_POINT
    rows = db.execute(
        """SELECT l.*,t.task_type FROM por_v2_ledger l
           JOIN por_v2_tasks t ON t.app_name=l.app_name AND t.code_id=l.code_id
             AND t.logical_task_id=l.logical_task_id
           WHERE l.app_name=? AND l.code_id=? ORDER BY l.created_at DESC LIMIT 100""",
        (APP_NAME, session.code_id),
    ).fetchall()
    precise_entries = [{
        "id": row["central_transaction_id"], "createdAt": row["created_at"],
        "kind": "usage", "description": "模型任务",
        "pointsDelta": -row["amount_units"] / billing_v2.UNITS_PER_POINT,
        "balanceAfter": row["balance_after_units"] / billing_v2.UNITS_PER_POINT,
        "taskType": row["task_type"],
    } for row in rows]
    wallet["ledger"] = sorted(wallet["ledger"] + precise_entries,
                              key=lambda item: item["createdAt"], reverse=True)[:100]
    precise_total = db.execute(
        "SELECT COALESCE(SUM(amount_units),0) FROM por_v2_ledger WHERE app_name=? AND code_id=?",
        (APP_NAME, session.code_id),
    ).fetchone()[0]
    wallet["totalChargedPoints"] += precise_total / billing_v2.UNITS_PER_POINT
    wallet["unbilledUsageCount"] += db.execute(
        """SELECT COUNT(*) FROM por_v2_attempts WHERE app_name=? AND code_id=?
           AND state IN ('awaiting_receipt','awaiting_bill','billing_pending')""",
        (APP_NAME, session.code_id),
    ).fetchone()[0]
    wallet["billingBasis"] = PRECISE_BILLING_SOURCE
    wallet["pricingVersion"] = PRECISE_TARIFF_VERSION
    return wallet


def normalize_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def code_hash_candidates(code: str) -> set[str]:
    normalized = normalize_code(code)
    values = {code, code.strip(), code.upper(), normalized}
    hashes = {hashlib.sha256(value.encode()).hexdigest() for value in values if value}
    if normalized:
        hashes.add(hashlib.sha256((LEGACY_NAMESPACE + normalized).encode()).hexdigest())
    return hashes


def table_columns(db: sqlite3.Connection, table: str) -> set[str]:
    if not IDENTIFIER_RE.fullmatch(table):
        raise ApiError(500, "授权数据表配置无效。")
    return {str(row[1]) for row in db.execute(f'PRAGMA table_info("{table}")')}


def resolve_topup_code(code: str, machine_code: str) -> tuple[str, int]:
    body = json.dumps({
        "app_name": APP_NAME,
        "activation_code": code,
        "code": code,
        "machine_code": machine_code,
        "machine_id": machine_code,
        "software_version": "points-topup-v1",
        "platform": "server-proxy",
    }, ensure_ascii=False).encode("utf-8")
    request = Request(
        LICENSE_ACTIVATE_URL, data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read(64 * 1024)
            status = int(response.status)
    except HTTPError as error:
        raw = error.read(64 * 1024)
        status = int(error.code)
    except (URLError, TimeoutError, OSError) as error:
        raise ApiError(503, "授权服务器暂时不可用，积分没有入账。") from error
    try:
        result = as_object(json.loads(raw.decode("utf-8", "replace")))
    except Exception as error:
        raise ApiError(503, "授权服务器返回异常，积分没有入账。") from error
    code_id, points_milli, _ = parse_license_response(
        result, status, machine_code, {"auto_topup"}
    )
    if points_milli <= 0:
        raise ApiError(400, "这个码没有可充值的积分。")
    return code_id, points_milli


def redeem_points(session: Session, code: str) -> tuple[int, dict[str, Any]]:
    code_id, points_milli = resolve_topup_code(code, session.machine_code)
    if hmac.compare_digest(code_id, session.code_id):
        raise ApiError(400, "当前主激活码不能作为积分码重复充值。")
    with database() as db:
        ensure_schema(db)
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT wallet_code_id FROM topup_redemptions WHERE app_name=? AND topup_code_id=?",
            (APP_NAME, code_id),
        ).fetchone()
        if existing:
            db.execute("ROLLBACK")
            raise ApiError(409, "这个积分码已经充值过，积分没有重复增加。")
        wallet = db.execute(
            "SELECT * FROM wallets WHERE app_name=? AND code_id=?", (APP_NAME, session.code_id)
        ).fetchone()
        if not wallet or wallet["machine_code"] != session.machine_code:
            db.execute("ROLLBACK")
            raise ApiError(403, "积分账户与当前电脑不匹配。")
        if db.execute(
            "SELECT 1 FROM wallets WHERE app_name=? AND code_id=?",
            (APP_NAME, code_id),
        ).fetchone():
            db.execute("ROLLBACK")
            raise ApiError(409, "这个码已经作为软件主激活码使用，不能再作为充值码。")
        balance = wallet["balance_milli"] + points_milli
        now = utc_now()
        db.execute(
            "INSERT INTO topup_redemptions VALUES(?,?,?,?,?,?)",
            (APP_NAME, code_id, session.code_id, points_milli, session.machine_code, now),
        )
        db.execute(
            "UPDATE wallets SET balance_milli=?,total_topup_milli=total_topup_milli+?,updated_at=? WHERE app_name=? AND code_id=?",
            (balance, points_milli, now, APP_NAME, session.code_id),
        )
        db.execute(
            "INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), APP_NAME, session.code_id, "topup", "积分码充值", points_milli,
             balance, None, None, None, now),
        )
        db.execute("COMMIT")
        return points_milli, wallet_json(session, db)


def validate_messages(body: dict[str, Any]) -> tuple[str, int]:
    model = text(body.get("model"), 200)
    # Installed clients retain their old model identifiers; never forward them upstream.
    if model in LEGACY_MODEL_ALIASES:
        model = MANAGED_MODEL
    if model not in ALLOWED_MODELS:
        raise ApiError(400, "模型不在服务器允许列表中。")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages or len(messages) > MAX_MESSAGES:
        raise ApiError(400, "模型消息数量异常。")
    approximate_tokens = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in ("system", "user", "assistant"):
            raise ApiError(400, "模型消息格式无效。")
        content = message.get("content")
        parts = [{"type": "text", "text": content}] if isinstance(content, str) else content
        if not isinstance(parts, list) or len(parts) > 128:
            raise ApiError(400, "模型消息内容格式无效。")
        for part in parts:
            if not isinstance(part, dict):
                raise ApiError(400, "模型消息内容格式无效。")
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                value = part["text"]
                if len(value) > MAX_TEXT_CHARS:
                    raise ApiError(413, "模型输入内容过大。")
                approximate_tokens += math.ceil(len(value.encode("utf-8")) / 3)
            elif part.get("type") in ("image_url", "image"):
                image_value = part.get("image_url")
                if isinstance(image_value, dict):
                    image_value = image_value.get("url")
                if not isinstance(image_value, str) or not image_value.startswith("data:image/"):
                    raise ApiError(400, "只允许软件上传的内嵌图片。")
                try:
                    encoded = image_value.split(",", 1)[1]
                    image_size = len(base64.b64decode(encoded, validate=True))
                except Exception as error:
                    raise ApiError(400, "图片内容损坏。") from error
                if image_size <= 0 or image_size > MAX_IMAGE_BYTES:
                    raise ApiError(413, "单张图片过大。")
                approximate_tokens += math.ceil(image_size / 64)
            else:
                raise ApiError(400, "模型消息内容格式无效。")
    return model, approximate_tokens


def model_for_task(task_type: str, requested_model: str) -> str:
    allowed = TASK_MODEL_ROUTES.get(task_type)
    if allowed is None:
        return requested_model
    if requested_model not in allowed:
        raise ApiError(400, "当前任务的模型路由无效。")
    return requested_model


def safe_public_search_url(value: Any) -> str:
    candidate = text(value, 4096).strip()
    if not candidate:
        return ""
    try:
        parsed = urlparse(candidate)
    except Exception:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return ""
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        return ""
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (
        address.is_private or address.is_loopback or address.is_link_local
        or address.is_multicast or address.is_reserved or address.is_unspecified
    ):
        return ""
    return candidate


def search_platform(url: str, title: str = "") -> str:
    value = f"{url} {title}".lower()
    if any(token in value for token in ("tmall.", "taobao.", "天猫", "淘宝")):
        return "天猫"
    if any(token in value for token in ("douyin.", "iesdouyin.", "抖音")):
        return "抖音"
    if any(token in value for token in ("channels.weixin.", "weixin.qq.", "视频号")):
        return "视频号"
    if any(token in value for token in ("xiaohongshu.", "xhslink.", "小红书")):
        return "小红书"
    return "其他"


def search_event_details(event: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Extract only bounded, structured search calls and public URL citations."""
    calls: list[dict[str, str]] = []
    evidence: list[dict[str, str]] = []
    event_type = text(event.get("type"), 120)
    action = event.get("action") if isinstance(event.get("action"), dict) else {}
    response = event.get("response") if isinstance(event.get("response"), dict) else {}
    response_output = response.get("output") if isinstance(response.get("output"), list) else []
    item = event.get("item") if isinstance(event.get("item"), dict) else {}
    items = [item, *[candidate for candidate in response_output[:32] if isinstance(candidate, dict)]]
    event_call_id = text(event.get("item_id") or event.get("id"), 200)
    if event_call_id and ("web_search" in event_type or "search_call" in event_type):
        calls.append({
            "callId": event_call_id,
            "query": text(event.get("query") or action.get("query"), 500),
            "status": event_type.rsplit(".", 1)[-1],
        })
    for output_item in items:
        item_type = text(output_item.get("type"), 120)
        if "web_search" not in item_type and "search_call" not in item_type:
            continue
        item_action = output_item.get("action") if isinstance(output_item.get("action"), dict) else {}
        call_id = text(output_item.get("id"), 200)
        if not call_id:
            continue
        calls.append({
            "callId": call_id,
            "query": text(output_item.get("query") or item_action.get("query"), 500),
            "status": text(output_item.get("status"), 80),
        })

    choices = event.get("choices") if isinstance(event.get("choices"), list) else []
    containers: list[dict[str, Any]] = [event, action, response, item]
    for output_item in items:
        containers.append(output_item)
        item_action = output_item.get("action") if isinstance(output_item.get("action"), dict) else None
        if item_action:
            containers.append(item_action)
        content = output_item.get("content") if isinstance(output_item.get("content"), list) else []
        containers.extend(candidate for candidate in content[:32] if isinstance(candidate, dict))
    for choice in choices[:8]:
        if not isinstance(choice, dict):
            continue
        for key in ("delta", "message"):
            value = choice.get(key)
            if isinstance(value, dict):
                containers.append(value)
        delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
        tool_calls = delta.get("tool_calls") if isinstance(delta.get("tool_calls"), list) else []
        for tool_call in tool_calls[:16]:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
            call_type = text(tool_call.get("type"), 80)
            call_name = text(function.get("name"), 120)
            if "web_search" not in f"{call_type} {call_name}":
                continue
            query = ""
            arguments = function.get("arguments")
            if isinstance(arguments, str) and len(arguments) <= 4096:
                try:
                    parsed_arguments = json.loads(arguments)
                    if isinstance(parsed_arguments, dict):
                        query = text(parsed_arguments.get("query") or parsed_arguments.get("q"), 500)
                except Exception:
                    pass
            calls.append({
                "callId": text(tool_call.get("id"), 200) or f"tool-{len(calls) + 1}",
                "query": query,
                "status": "in_progress",
            })

    for container in containers[:24]:
        candidates: list[Any] = []
        for key in ("sources", "results", "citations", "annotations"):
            value = container.get(key)
            if isinstance(value, list):
                candidates.extend(value[:50])
        for candidate in candidates[:100]:
            if isinstance(candidate, str):
                url = safe_public_search_url(candidate)
                title = ""
            elif isinstance(candidate, dict):
                citation = candidate.get("url_citation") if isinstance(candidate.get("url_citation"), dict) else candidate
                url = safe_public_search_url(citation.get("url") or citation.get("link"))
                title = text(citation.get("title") or citation.get("name"), 300)
            else:
                continue
            if not url:
                continue
            evidence.append({
                "title": title,
                "url": url,
                "platform": search_platform(url, title),
            })
    return calls, evidence


def responses_request_body(chat_body: dict[str, Any]) -> dict[str, Any]:
    instructions: list[str] = []
    input_items: list[dict[str, Any]] = []
    for message in chat_body.get("messages", []):
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role == "system" and isinstance(content, str):
            instructions.append(content)
            continue
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        input_items.append({"role": role, "content": content})
    if not input_items:
        raise ApiError(400, "对标搜索输入为空。")
    return {
        "model": chat_body["model"],
        "instructions": "\n\n".join(instructions),
        "input": input_items,
        "stream": True,
        "max_output_tokens": chat_body.get("max_completion_tokens", 5000),
        "thinking": {"type": "enabled"},
        "reasoning": {"effort": "high"},
        "store": False,
        "tools": [{
            "type": "web_search",
            "max_keyword": 2,
            "limit": 10,
        }],
        "tool_choice": "required",
        "max_tool_calls": 1,
    }


def responses_output_text(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    chunks: list[str] = []
    output = response.get("output") if isinstance(response.get("output"), list) else []
    for item in output[:64]:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content") if isinstance(item.get("content"), list) else []
        for part in content[:64]:
            if isinstance(part, dict) and part.get("type") in ("output_text", "text") and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "".join(chunks)


def points_for_usage(model: str, input_tokens: int, output_tokens: int, cached: int = 0, created: int = 0) -> tuple[int, float]:
    input_rate, output_rate, cached_rate, created_rate = MODEL_PRICES[model]
    regular = max(0, input_tokens - cached - created)
    usd = (regular * input_rate + cached * cached_rate + created * created_rate + output_tokens * output_rate) / 1_000_000
    if model == MANAGED_MODEL:
        # Ark prices are denominated in CNY; exchange-rate settings must not
        # change the cost of the same Ark request. No explicit stored cache is used.
        rates = ARK_MODEL_PRICES_CNY
        native_cost = sum(Decimal(tokens) * Decimal(str(rate)) for tokens, rate in zip(
            (regular, output_tokens, cached, created), rates
        )) / Decimal(1_000_000)
        charged = native_cost * Decimal(str(POINTS_PER_CNY)) * Decimal(str(CHARGE_MULTIPLIER)) * 1000
        return max(0, int(charged.to_integral_value(rounding=ROUND_CEILING))), max(0.0, float(native_cost))
    else:
        cost_cny = usd * USD_CNY_RATE
    charged_milli = math.ceil(cost_cny * POINTS_PER_CNY * CHARGE_MULTIPLIER * 1000)
    return max(0, charged_milli), max(0.0, cost_cny)


def rounded_charge_milli(cost_cny: float) -> int:
    """Round final cost to whole points, with exact decimal half-up semantics."""
    points = (
        Decimal(str(max(0.0, cost_cny)))
        * Decimal(str(POINTS_PER_CNY))
        * Decimal(str(CHARGE_MULTIPLIER))
    )
    return int(points.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * 1000


def provider_route(model: str) -> tuple[str, str]:
    if model not in ALLOWED_MODELS:
        raise ApiError(400, "模型不在服务器允许列表中。")
    route = PROVIDER_KEYRING.active(model)
    return (route.base_url, route.api_key) if route else ("", "")


def provider_route_candidates(model: str) -> tuple[ProviderRouteSnapshot, ...]:
    if model not in ALLOWED_MODELS:
        raise ApiError(400, "模型不在服务器允许列表中。")
    return PROVIDER_KEYRING.candidates(model)


def open_provider_stream(
    candidates: tuple[ProviderRouteSnapshot, ...], upstream_data: bytes, request_id: str,
    endpoint_path: str = "chat/completions",
) -> Any:
    """Open one upstream stream, using standby keys only for pre-stream auth failures."""
    last_auth_error: HTTPError | None = None
    for candidate_index, candidate in enumerate(candidates):
        request = Request(
            f"{candidate.base_url}/{endpoint_path}",
            data=upstream_data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {candidate.api_key}",
                "X-Request-Id": request_id,
            },
        )
        try:
            return urlopen(request, timeout=300)
        except HTTPError as error:
            # Authentication rejection occurs before any successful response body
            # is streamed. Other errors are never retried with a second secret.
            if error.code in (401, 403) and candidate_index + 1 < len(candidates):
                error.read(16 * 1024)
                last_auth_error = error
                continue
            raise
    raise last_auth_error or OSError("no provider route available")


def points_for_verified_usage(requested_model: str, response_model: str | None, input_tokens: int,
                              output_tokens: int, cached: int = 0, created: int = 0) -> tuple[int, float]:
    requested = points_for_usage(requested_model, input_tokens, output_tokens, cached, created)
    actual_name = (response_model or "").strip()
    if not actual_name or actual_name == requested_model:
        return requested
    if actual_name not in MODEL_PRICES:
        return max(
            (points_for_usage(candidate, input_tokens, output_tokens, cached, created) for candidate in MODEL_PRICES),
            key=lambda item: item[0],
        )
    actual = points_for_usage(actual_name, input_tokens, output_tokens, cached, created)
    return actual if actual[0] > requested[0] else requested


def reserve_request(session: Session, request_id: str, report_id: str, task_key: str, task_type: str,
                    model: str, attempt: int, input_estimate: int, billing_request_id: str = "") -> int:
    output_reserve = min(MAX_OUTPUT_TOKENS, TASK_OUTPUT_RESERVES.get(task_type, MAX_OUTPUT_TOKENS))
    reserve_candidates = [points_for_usage(candidate, input_estimate, output_reserve) for candidate in ALLOWED_MODELS]
    reserve, reserve_cost_cny = max(reserve_candidates, key=lambda item: item[0])
    if task_type == "module_benchmark" and WEB_SEARCH_USD_PER_CALL > 0:
        search_cost_cny = 2 * WEB_SEARCH_USD_PER_CALL * USD_CNY_RATE
        reserve += math.ceil(search_cost_cny * POINTS_PER_CNY * CHARGE_MULTIPLIER * 1000)
        reserve_cost_cny += search_cost_cny
    # Final billing is in whole points; lock enough for a possible half-up step,
    # including any search component in benchmark tasks.
    reserve = math.ceil(reserve / 1000) * 1000
    with database() as db:
        ensure_schema(db)
        ensure_v2_report_schema(db)
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM model_requests WHERE request_id=?", (request_id,)).fetchone():
            db.execute("ROLLBACK")
            raise ApiError(409, "检测到重复模型请求，已阻止重复扣费。")
        if task_type == "module_benchmark":
            search_attempts = report_search_attempts(db, session.code_id, report_id)
            if int(search_attempts) >= WEB_SEARCH_REPORT_LIMIT:
                db.execute("ROLLBACK")
                raise ApiError(429, "search_budget_exhausted：本报告的联网搜索预算已用完。")
        same_task_running = db.execute(
            "SELECT 1 FROM model_requests WHERE app_name=? AND code_id=? AND task_key=? AND model=? "
            "AND status='running' LIMIT 1",
            (APP_NAME, session.code_id, task_key, model),
        ).fetchone()
        if same_task_running:
            db.execute("ROLLBACK")
            raise ApiError(409, "同一批资料仍在服务器处理中，请稍等后再继续，不会重复扣费。")
        previous_attempt = db.execute(
            "SELECT COALESCE(MAX(attempt),0) FROM model_requests "
            "WHERE app_name=? AND code_id=? AND task_key=? AND model=?",
            (APP_NAME, session.code_id, task_key, model),
        ).fetchone()[0]
        # A user may retry the same saved task after an app restart. The client
        # attempt counter is process-local, so make the persisted audit attempt
        # monotonic on the server instead of leaking a SQLite uniqueness error.
        stored_attempt = max(int(attempt), int(previous_attempt) + 1)
        active = db.execute(
            "SELECT report_session_id FROM model_requests WHERE app_name=? AND code_id=? AND status='running'",
            (APP_NAME, session.code_id),
        ).fetchall()
        if len(active) >= MAX_ACTIVE_PER_LICENSE or any(row[0] != report_id for row in active):
            db.execute("ROLLBACK")
            raise ApiError(429, "当前已有报告正在生成，请等待完成后再试。")
        day_cost = db.execute(
            "SELECT COALESCE(SUM(cost_cny),0) FROM model_requests "
            "WHERE status IN ('success','partial','aborted','billing_pending','billing_conflict_released') "
            "AND started_at>=?",
            (f"{utc_day()}T00:00:00Z",),
        ).fetchone()[0]
        running_reserved_milli = db.execute(
            "SELECT COALESCE(SUM(reserved_milli),0) FROM model_requests WHERE status='running'"
        ).fetchone()[0]
        running_reserved_cost = float(running_reserved_milli) / (POINTS_PER_CNY * CHARGE_MULTIPLIER * 1000)
        if float(day_cost) + running_reserved_cost + reserve_cost_cny > DAILY_COST_LIMIT_CNY:
            db.execute("ROLLBACK")
            raise ApiError(503, "今日模型费用已达到安全上限，请联系管理员。")
        wallet = db.execute(
            "SELECT * FROM wallets WHERE app_name=? AND code_id=?", (APP_NAME, session.code_id)
        ).fetchone()
        if not wallet or wallet["frozen"] or wallet["machine_code"] != session.machine_code:
            db.execute("ROLLBACK")
            raise ApiError(403, "积分账户不可用，请重新登录或联系管理员。")
        available = wallet["balance_milli"] - wallet["locked_milli"]
        if reserve <= 0 or (not session.unlimited and available < reserve):
            db.execute("ROLLBACK")
            raise ApiError(
                402,
                "积分不足：当前可用 "
                f"{milli_to_points(max(0, available))} 积分，本批最多需要暂时预留 "
                f"{milli_to_points(reserve)} 积分。系统尚未扣费。",
            )
        now = utc_now()
        db.execute(
            "UPDATE wallets SET locked_milli=locked_milli+?,updated_at=? WHERE app_name=? AND code_id=?",
            (reserve, now, APP_NAME, session.code_id),
        )
        db.execute(
            "INSERT INTO model_requests(request_id,app_name,code_id,machine_code,report_session_id,task_key,task_type,model,attempt,status,reserved_milli,input_estimate,started_at,billing_request_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (request_id, APP_NAME, session.code_id, session.machine_code, report_id, task_key, task_type,
             model, stored_attempt, "running", reserve, input_estimate, now, billing_request_id or request_id),
        )
        db.execute("COMMIT")
    return reserve


def finalize_billing_request(
    session: Session, request_id: str, remaining_milli: int, unlimited: bool
) -> None:
    with database() as db:
        ensure_schema(db)
        db.execute("BEGIN IMMEDIATE")
        request_row = db.execute("SELECT * FROM model_requests WHERE request_id=?", (request_id,)).fetchone()
        if not request_row or request_row["status"] != "billing_pending":
            db.execute("ROLLBACK")
            return
        wallet = db.execute(
            "SELECT * FROM wallets WHERE app_name=? AND code_id=?", (APP_NAME, session.code_id)
        ).fetchone()
        if not wallet:
            db.execute("ROLLBACK")
            raise ApiError(403, "积分账户不可用，请重新登录或联系管理员。")
        actual_charge = 0 if unlimited else max(0, int(request_row["charged_milli"]))
        locked = max(0, int(wallet["locked_milli"]) - int(request_row["reserved_milli"]))
        now = utc_now()
        db.execute(
            "UPDATE wallets SET balance_milli=?,locked_milli=?,total_cost_milli=total_cost_milli+?,total_charged_milli=total_charged_milli+?,updated_at=? WHERE app_name=? AND code_id=?",
            (remaining_milli, locked, math.ceil(float(request_row["cost_cny"]) * POINTS_PER_CNY * 1000),
             actual_charge, now, APP_NAME, session.code_id),
        )
        if actual_charge:
            task_descriptions = {
                "source_clean": "资料清洗",
                "summary": "资料汇总",
                "analysis_step": "分析步骤",
                "final_part": "最终成稿",
                "revision_part": "报告修订",
                "module_product_info": "M1 产品信息",
                "module_platform_audience": "M2 平台人群数据",
                "module_material_review": "M3 内容素材判断",
                "module_benchmark": "M4 对标推荐",
                "module_selling_points": "M5 产品卖点",
                "module_voc": "M6 用户真实需求VOC",
                "module_ranking": "M7 总结卖点排序",
                "module_audience_sp_scene": "M8 人群卖点场景匹配",
            }
            description = task_descriptions.get(request_row["task_type"], "报告分析")
            if int(request_row["search_calls"] or 0) > 0:
                description += f"（联网搜索 {int(request_row['search_calls'])} 次）"
            db.execute(
                "INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), APP_NAME, session.code_id, "usage",
                 description, -actual_charge,
                 remaining_milli, request_row["report_session_id"], request_row["task_type"], request_id, now),
            )
        db.execute(
            "UPDATE model_requests SET status=?,charged_milli=?,billing_error='',ended_at=? WHERE request_id=?",
            (request_row["billing_result_status"] or "success", actual_charge, now, request_id),
        )
        db.execute("COMMIT")
    session.unlimited = unlimited


def record_billing_error(request_id: str, message: str) -> None:
    with database() as db:
        ensure_schema(db)
        db.execute(
            "UPDATE model_requests SET billing_error=? WHERE request_id=? AND status='billing_pending'",
            (text(message, 300), request_id),
        )


def fail_billing_and_release(request_id: str, message: str) -> bool:
    """Fail closed without leaving a permanent ghost reservation."""
    with database() as db:
        ensure_schema(db)
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM model_requests WHERE request_id=?", (request_id,)).fetchone()
        if not row or row["status"] != "billing_pending":
            db.execute("ROLLBACK")
            return False
        wallet = db.execute(
            "SELECT * FROM wallets WHERE app_name=? AND code_id=?", (row["app_name"], row["code_id"])
        ).fetchone()
        if wallet:
            locked = max(0, int(wallet["locked_milli"]) - int(row["reserved_milli"]))
            db.execute(
                "UPDATE wallets SET locked_milli=?,updated_at=? WHERE app_name=? AND code_id=?",
                (locked, utc_now(), row["app_name"], row["code_id"]),
            )
        db.execute(
            "UPDATE model_requests SET status='billing_failed',charged_milli=0,billing_result_status='billing_failed',billing_error=?,ended_at=? WHERE request_id=?",
            (text(message, 300), utc_now(), request_id),
        )
        db.execute("COMMIT")
        return True


def release_legacy_billing_conflict(request_id: str) -> bool:
    """Release pre-fix logical-ID conflicts without charging a second attempt."""
    with database() as db:
        ensure_schema(db)
        db.execute("BEGIN IMMEDIATE")
        request_row = db.execute(
            "SELECT * FROM model_requests WHERE request_id=? AND status='billing_pending'",
            (request_id,),
        ).fetchone()
        if not request_row or "request_id 已用于不同的消费请求" not in str(request_row["billing_error"] or ""):
            db.execute("ROLLBACK")
            return False
        wallet = db.execute(
            "SELECT * FROM wallets WHERE app_name=? AND code_id=?",
            (APP_NAME, request_row["code_id"]),
        ).fetchone()
        if not wallet:
            db.execute("ROLLBACK")
            raise ApiError(403, "积分账户不可用，请重新登录或联系管理员。")
        locked = max(0, int(wallet["locked_milli"]) - int(request_row["reserved_milli"]))
        now = utc_now()
        db.execute(
            "UPDATE wallets SET locked_milli=?,updated_at=? WHERE app_name=? AND code_id=?",
            (locked, now, APP_NAME, request_row["code_id"]),
        )
        db.execute(
            "UPDATE model_requests SET status='billing_conflict_released',charged_milli=0,"
            "billing_result_status='billing_conflict_released',ended_at=? WHERE request_id=?",
            (now, request_id),
        )
        db.execute("COMMIT")
        return True


def retry_pending_billing(session: Session) -> None:
    with database() as db:
        ensure_schema(db)
        pending = db.execute(
            "SELECT request_id,charged_milli,billing_request_id,task_type FROM model_requests "
            "WHERE app_name=? AND code_id=? AND status='billing_pending' ORDER BY started_at",
            (APP_NAME, session.code_id),
        ).fetchall()
    for row in pending:
        if release_legacy_billing_conflict(row["request_id"]):
            continue
        try:
            # request_id identifies one actual upstream attempt and therefore one
            # exact amount. billing_request_id is only the stable logical task
            # grouping supplied by the client; reusing it for different attempts
            # would violate /credits/consume idempotency when Token usage differs.
            remaining, unlimited = consume_authoritative_credits(
                session,
                int(row["charged_milli"]),
                row["request_id"],
                f"product_operation_report:{row['task_type']}",
            )
        except ApiError as error:
            fail_billing_and_release(row["request_id"], error.message)
            raise
        finalize_billing_request(session, row["request_id"], remaining, unlimited)


def release_stale_pending_billing(session: Session, maximum_age_seconds: int = 1800) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=maximum_age_seconds)).isoformat().replace("+00:00", "Z")
    with database() as db:
        ensure_schema(db)
        rows = db.execute(
            "SELECT request_id FROM model_requests WHERE app_name=? AND code_id=? "
            "AND status='billing_pending' AND COALESCE(ended_at,started_at)<?",
            (APP_NAME, session.code_id, cutoff),
        ).fetchall()
    released = 0
    for row in rows:
        released += 1 if fail_billing_and_release(row["request_id"], "结算等待超过30分钟，已自动释放预留积分。") else 0
    return released


def settle_request(session: Session, request_id: str, status: str, model: str, usage: dict[str, Any] | None,
                   input_estimate: int, output_chars: int, sent_content: bool, search_calls: int = 0) -> None:
    if usage:
        input_tokens = max(0, int(usage.get("input_tokens", 0)))
        output_tokens = max(0, int(usage.get("output_tokens", 0)))
        cached = max(0, min(input_tokens, int(usage.get("cached_input_tokens", 0))))
        created = max(0, min(input_tokens - cached, int(usage.get("cache_creation_input_tokens", 0))))
        usage_source = "provider"
    elif sent_content:
        input_tokens, output_tokens, cached, created = input_estimate, math.ceil(output_chars / 3), 0, 0
        usage_source = "estimated"
    else:
        input_tokens = output_tokens = cached = created = 0
        usage_source = "missing"
    response_model = text(usage.get("response_model"), 200) if usage else ""
    charged, cost_cny = points_for_verified_usage(
        model, response_model, input_tokens, output_tokens, cached, created
    )
    search_calls = max(0, min(WEB_SEARCH_REPORT_LIMIT, int(search_calls)))
    if search_calls:
        search_cost_cny = search_calls * WEB_SEARCH_USD_PER_CALL * USD_CNY_RATE
        cost_cny += search_cost_cny
        charged += math.ceil(search_cost_cny * POINTS_PER_CNY * CHARGE_MULTIPLIER * 1000)
    if not sent_content:
        charged = 0
        cost_cny = 0
    else:
        charged = rounded_charge_milli(cost_cny)
    task_type = "model"
    with database() as db:
        ensure_schema(db)
        db.execute("BEGIN IMMEDIATE")
        request_row = db.execute("SELECT * FROM model_requests WHERE request_id=?", (request_id,)).fetchone()
        if not request_row or request_row["status"] != "running":
            db.execute("ROLLBACK")
            return
        wallet = db.execute(
            "SELECT * FROM wallets WHERE app_name=? AND code_id=?", (APP_NAME, session.code_id)
        ).fetchone()
        if not wallet:
            db.execute("ROLLBACK")
            raise ApiError(403, "积分账户不可用，请重新登录或联系管理员。")
        # The reserve uses the most expensive allowed model and the enforced output cap.
        charged = min(charged, request_row["reserved_milli"])
        now = utc_now()
        task_type = request_row["task_type"]
        if charged <= 0:
            locked = max(0, wallet["locked_milli"] - request_row["reserved_milli"])
            db.execute(
                "UPDATE wallets SET locked_milli=?,updated_at=? WHERE app_name=? AND code_id=?",
                (locked, now, APP_NAME, session.code_id),
            )
            db.execute(
                "UPDATE model_requests SET status=?,input_tokens=?,output_tokens=?,cached_input_tokens=?,cache_creation_input_tokens=?,usage_source=?,response_model=?,cost_cny=0,charged_milli=0,billing_result_status=?,billing_error='',search_calls=?,ended_at=? WHERE request_id=?",
                (status, input_tokens, output_tokens, cached, created, usage_source, response_model,
                 status, search_calls, now, request_id),
            )
            db.execute("COMMIT")
            return
        db.execute(
            "UPDATE model_requests SET status='billing_pending',input_tokens=?,output_tokens=?,cached_input_tokens=?,cache_creation_input_tokens=?,usage_source=?,response_model=?,cost_cny=?,charged_milli=?,billing_result_status=?,billing_error='',search_calls=?,ended_at=? WHERE request_id=?",
            (input_tokens, output_tokens, cached, created, usage_source, response_model, cost_cny,
             charged, status, search_calls, now, request_id),
        )
        db.execute("COMMIT")
    try:
        # Bill the concrete upstream attempt. Network retries of this settlement
        # reuse request_id via retry_pending_billing, while a new model/fallback
        # attempt receives a new request_id and may legitimately have a new cost.
        remaining, unlimited = consume_authoritative_credits(
            session,
            charged,
            request_id,
            f"product_operation_report:{task_type}",
        )
    except ApiError as error:
        fail_billing_and_release(request_id, error.message)
        return
    finalize_billing_request(session, request_id, remaining, unlimited)


def provider_usage(payload: dict[str, Any]) -> dict[str, Any] | None:
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else response.get("usage")
    if not isinstance(usage, dict):
        return None
    details = (
        usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict)
        else usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict)
        else {}
    )
    def usage_integer(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    input_tokens = usage_integer(usage.get("prompt_tokens", usage.get("input_tokens")))
    output_tokens = usage_integer(usage.get("completion_tokens", usage.get("output_tokens")))
    for chat_name, responses_name in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
        if chat_name in usage and responses_name in usage and usage[chat_name] != usage[responses_name]:
            return None
    cached_tokens = usage_integer(details.get("cached_tokens", usage.get("cached_input_tokens", 0)))
    created_tokens = usage_integer(usage.get("cache_creation_input_tokens", 0))
    if None in (input_tokens, output_tokens, cached_tokens, created_tokens):
        return None
    result = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_tokens,
        "cache_creation_input_tokens": created_tokens,
        "response_model": text(payload.get("model") or response.get("model"), 200),
    }
    tool_usage = usage.get("tool_usage") if isinstance(usage.get("tool_usage"), dict) else {}
    search_calls = usage_integer(tool_usage.get("web_search", 0))
    if "web_search" in tool_usage:
        if search_calls is None or not 0 <= search_calls <= 1000:
            return None
        result["web_search_calls"] = search_calls
    if any(result[name] < 0 or result[name] > 2_000_000_000 for name in (
        "input_tokens", "output_tokens", "cached_input_tokens", "cache_creation_input_tokens"
    )):
        return None
    if result["input_tokens"] + result["output_tokens"] <= 0:
        return None
    if result["cached_input_tokens"] + result["cache_creation_input_tokens"] > result["input_tokens"]:
        return None
    if "total_tokens" in usage:
        total_tokens = usage_integer(usage.get("total_tokens"))
        if total_tokens != result["input_tokens"] + result["output_tokens"]:
            return None
    return result


def merge_provider_usage(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any] | None:
    # Complete provider snapshots are authoritative; never invent a synthetic
    # bill by combining maxima from unrelated/intermediate frames.
    return current if current is not None else previous


def provider_stream_items(upstream: Any, heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS):
    """Read a blocking provider stream on a worker and emit privacy-safe heartbeats.

    Only raw bytes and transient exceptions pass through this in-memory queue;
    no prompt or model output is persisted by the proxy.
    """
    events: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=256)

    def read_upstream() -> None:
        try:
            for raw_line in upstream:
                events.put(("line", raw_line))
        except BaseException as error:  # transferred back to the request thread
            events.put(("error", error))
        finally:
            events.put(("done", None))

    threading.Thread(target=read_upstream, name="por-provider-stream", daemon=True).start()
    while True:
        try:
            kind, value = events.get(timeout=max(0.01, heartbeat_seconds))
        except queue.Empty:
            yield "heartbeat", b": heartbeat\n\n"
            continue
        if kind == "done":
            return
        if kind == "error":
            raise value
        yield kind, value


def provider_request_items(
    candidates: tuple[ProviderRouteSnapshot, ...],
    upstream_data: bytes,
    request_id: str,
    endpoint_path: str = "chat/completions",
    heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS,
):
    """Open and read an upstream request while heartbeats are already flowing.

    Some providers do not return HTTP response headers until prompt preparation
    has finished. Opening the provider before responding to the desktop leaves
    the client completely silent during that interval. This queue starts the
    blocking connection on a worker so the public SSE response can remain alive
    from the first second without persisting prompts or model output.
    """
    events: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=256)

    def open_and_read() -> None:
        try:
            upstream = open_provider_stream(candidates, upstream_data, request_id, endpoint_path)
            with upstream:
                for raw_line in upstream:
                    events.put(("line", raw_line))
        except BaseException as error:  # transferred back to the request thread
            events.put(("error", error))
        finally:
            events.put(("done", None))

    threading.Thread(target=open_and_read, name="por-provider-request", daemon=True).start()
    while True:
        try:
            kind, value = events.get(timeout=max(0.01, heartbeat_seconds))
        except queue.Empty:
            yield "heartbeat", b": heartbeat\n\n"
            continue
        if kind == "done":
            return
        if kind == "error":
            raise value
        yield kind, value


def provider_stream_completed(saw_done: bool, finish_reason: str, usage: dict[str, Any] | None,
                              sent_content: bool) -> bool:
    # Usage is metering data, not proof that generation finished successfully.
    return bool(sent_content and finish_reason in ("", "stop") and (saw_done or finish_reason == "stop"))


def apply_server_task_options(upstream_body: dict[str, Any], task_type: str) -> None:
    # Only forward Ark-supported options. Client cache hints remain local.
    upstream_body.pop("prompt_cache_key", None)
    upstream_body.pop("reasoning_effort", None)
    # Ark max_completion_tokens caps answer AND thinking tokens. max_tokens
    # caps only the answer and therefore cannot enforce the reserved budget.
    upstream_body["thinking"] = {"type": "disabled" if task_type in ("source_clean", "summary") else "enabled"}
    if task_type == "module_benchmark":
        upstream_body["tools"] = [{"type": "web_search", "max_keyword": 2, "limit": 10}]
        upstream_body["tool_choice"] = "required"


def mark_upstream_submitted(request_id: str) -> None:
    with database() as db:
        ensure_schema(db)
        db.execute(
            "UPDATE model_requests SET upstream_submitted=1 WHERE request_id=? AND status='running'",
            (request_id,),
        )


def recover_interrupted_requests() -> None:
    with database() as db:
        ensure_schema(db)
        stale = db.execute("SELECT * FROM model_requests WHERE status='running'").fetchall()
        for row in stale:
            db.execute("BEGIN IMMEDIATE")
            wallet = db.execute(
                "SELECT * FROM wallets WHERE app_name=? AND code_id=?", (row["app_name"], row["code_id"])
            ).fetchone()
            if not wallet:
                db.execute(
                    "UPDATE model_requests SET status='interrupted_orphaned',ended_at=? WHERE request_id=?",
                    (utc_now(), row["request_id"]),
                )
                db.execute("COMMIT")
                continue
            charged = 0
            cost_cny = 0.0
            usage_source = "missing"
            if row["upstream_submitted"]:
                charged, cost_cny = points_for_usage(row["model"], max(0, row["input_estimate"]), 0)
                charged = rounded_charge_milli(cost_cny)
                charged = min(charged, row["reserved_milli"])
                usage_source = "estimated"
            now = utc_now()
            if charged:
                db.execute(
                    "UPDATE model_requests SET status='billing_pending',input_tokens=?,usage_source=?,cost_cny=?,charged_milli=?,billing_result_status='interrupted_estimated',billing_error=?,ended_at=? WHERE request_id=?",
                    (max(0, row["input_estimate"]), usage_source, cost_cny, charged,
                     "等待设备重新连接后完成保守结算。", now, row["request_id"]),
                )
            else:
                locked = max(0, wallet["locked_milli"] - row["reserved_milli"])
                db.execute(
                    "UPDATE wallets SET locked_milli=?,updated_at=? WHERE app_name=? AND code_id=?",
                    (locked, now, row["app_name"], row["code_id"]),
                )
                db.execute(
                    "UPDATE model_requests SET status='interrupted',usage_source='missing',charged_milli=0,billing_result_status='interrupted',billing_error='',ended_at=? WHERE request_id=?",
                    (now, row["request_id"]),
                )
            db.execute("COMMIT")


def ensure_v2_report_schema(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS por_v2_report_attempts (
        request_id TEXT PRIMARY KEY, app_name TEXT NOT NULL, code_id TEXT NOT NULL,
        report_session_id TEXT NOT NULL, task_type TEXT NOT NULL,
        started_at TEXT NOT NULL)""")
    db.execute("""CREATE INDEX IF NOT EXISTS por_v2_report_search_idx
        ON por_v2_report_attempts(app_name, code_id, report_session_id, task_type)""")


def report_search_attempts(db: sqlite3.Connection, code_id: str, report_id: str) -> int:
    legacy = db.execute(
        """SELECT COUNT(*) FROM model_requests WHERE app_name=? AND code_id=?
           AND report_session_id=? AND task_type='module_benchmark'
           AND (upstream_submitted=1 OR status='running')""",
        (APP_NAME, code_id, report_id),
    ).fetchone()[0]
    precise = db.execute(
        """SELECT COUNT(*) FROM por_v2_report_attempts WHERE app_name=? AND code_id=?
           AND report_session_id=? AND task_type='module_benchmark'""",
        (APP_NAME, code_id, report_id),
    ).fetchone()[0]
    return int(legacy) + int(precise)


def v2_required_units(row: sqlite3.Row) -> int:
    required = max(row["reserved_units"], row["amount_units"])
    if row["state"] in ("awaiting_receipt", "awaiting_bill", "receipt_expired_no_charge") and PRECISE_BILLING_SOURCE == "versioned_tariff":
        try:
            usage = json.loads(row["provider_usage_json"])
        except (TypeError, ValueError) as error:
            raise ApiError(409, "已有结果的实际用量不可核对，请先恢复或拒绝该结果。") from error
        cost = v2_tariff_cost_cny(row["response_model"], usage)
        required = max(required, billing_v2.amount_units(cost, str(POINTS_PER_CNY), str(COST_RATE)))
    return required


def v2_locked_units(db: sqlite3.Connection, code_id: str) -> int:
    rows = db.execute(
        """SELECT state,reserved_units,amount_units,response_model,provider_usage_json FROM por_v2_attempts
           WHERE app_name=? AND code_id=?
           AND state IN ('running','awaiting_receipt','awaiting_bill','billing_pending')""",
        (APP_NAME, code_id),
    ).fetchall()
    return sum(v2_required_units(row) for row in rows)


def v2_start_attempt(session: Session, logical_id: str, request_id: str,
                     task_key: str, task_type: str, model: str,
                     input_estimate: int, redo_of: str = "", report_id: str = "") -> None:
    if not PRECISE_INTERNAL_TOKEN or len(os.environ.get("POR_RESULT_PROOF_SECRET", "")) < 32:
        raise ApiError(503, "精确积分服务尚未完成安全配置。")
    # The central balance is authoritative; old wallet.milli fields are only a
    # compatibility display and must never decide the exact debit.
    output_reserve = min(MAX_OUTPUT_TOKENS, TASK_OUTPUT_RESERVES.get(task_type, MAX_OUTPUT_TOKENS))
    reserve_milli, reserve_cost_cny = max(
        (points_for_usage(candidate, input_estimate, output_reserve) for candidate in ALLOWED_MODELS),
        key=lambda item: item[0],
    )
    reserve_units = ((reserve_milli + 999) // 1000) * billing_v2.UNITS_PER_POINT
    with database() as db:
        billing_v2.ensure_schema(db)
        ensure_v2_report_schema(db)
        db.execute("BEGIN IMMEDIATE")
        try:
            # Read while holding the local admission/settlement lock so another
            # settlement cannot clear its reservation after this balance snapshot.
            current = precise_license_balance(session)
            if not session.unlimited and current["remaining_units"] <= 0:
                raise ApiError(402, "积分不足，本次任务没有提交上游。")
            billing_v2.expire_unconfirmed(db)
            if task_type == "module_benchmark":
                if not report_id:
                    raise ApiError(400, "联网搜索缺少报告标识。")
                if report_search_attempts(db, session.code_id, report_id) >= WEB_SEARCH_REPORT_LIMIT:
                    raise ApiError(429, "search_budget_exhausted：本报告的联网搜索预算已用完。")
            running = db.execute(
                "SELECT COUNT(*) FROM por_v2_attempts WHERE app_name=? AND code_id=? AND state='running'",
                (APP_NAME, session.code_id),
            ).fetchone()[0]
            if running >= MAX_ACTIVE_PER_LICENSE:
                raise ApiError(429, "当前并行任务已达上限，请稍后重试。")
            unconfirmed = db.execute(
                """SELECT COUNT(*) FROM por_v2_attempts WHERE app_name=? AND code_id=?
                   AND state IN ('awaiting_receipt','awaiting_bill','billing_pending')""",
                (APP_NAME, session.code_id),
            ).fetchone()[0]
            if unconfirmed >= MAX_ACTIVE_PER_LICENSE:
                raise ApiError(429, "已有结果等待保存确认或积分对账，请先恢复这些任务。")
            locked_units = v2_locked_units(db, session.code_id)
            if not session.unlimited and current["remaining_units"] - locked_units < reserve_units:
                raise ApiError(402, "积分不足以暂时预留本批次上限；尚未提交模型。")
            today_cost = db.execute(
                """SELECT COALESCE(SUM(CAST(a.cost_cny AS REAL)),0)
                   FROM por_v2_ledger l JOIN por_v2_attempts a ON a.request_id=l.request_id
                   WHERE l.created_at>=?""",
                (f"{utc_day()}T00:00:00Z",),
            ).fetchone()[0]
            legacy_today_cost = db.execute(
                """SELECT COALESCE(SUM(cost_cny),0) FROM model_requests
                   WHERE started_at>=? AND status IN ('success','partial','aborted')""",
                (f"{utc_day()}T00:00:00Z",),
            ).fetchone()[0]
            if today_cost + legacy_today_cost + reserve_cost_cny > DAILY_COST_LIMIT_CNY:
                raise ApiError(503, "今日模型费用已达到安全上限。")
            billing_v2.start_attempt(db, APP_NAME, session.code_id,
                                      logical_id, task_key, task_type, request_id, model,
                                      redo_of=redo_of, reserved_units=reserve_units)
            db.execute("INSERT INTO por_v2_report_attempts VALUES(?,?,?,?,?,?)",
                       (request_id, APP_NAME, session.code_id, report_id, task_type, utc_now()))
            db.execute("COMMIT")
        except billing_v2.BillingStateError as error:
            db.execute("ROLLBACK")
            raise ApiError(error.status, str(error)) from error
        except Exception:
            db.execute("ROLLBACK")
            raise


def v2_finish_attempt(request_id: str, success: bool, content: str,
                      response_model: str, usage: dict[str, Any] | None) -> str:
    with database() as db:
        billing_v2.ensure_schema(db)
        db.execute("BEGIN IMMEDIATE")
        try:
            safe_usage = None if not usage else {
                name: int(usage.get(name, 0)) for name in
                ("input_tokens", "output_tokens", "cached_input_tokens", "cache_creation_input_tokens")
            }
            state = billing_v2.finish_attempt(db, request_id, success, content,
                                              response_model, safe_usage)
            db.execute("COMMIT")
            return state
        except Exception:
            db.execute("ROLLBACK")
            raise


def v2_tariff_cost_cny(model: str, usage: dict[str, Any]) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", PRECISE_TARIFF_SHA256):
        raise ApiError(503, "价目表校验值未配置，本次进入待对账。")
    try:
        source = Path(PRECISE_TARIFF_FILE).read_bytes()
        tariff = as_object(json.loads(source.decode("utf-8")))
    except Exception as error:
        raise ApiError(503, "版本化价目表不可读取，本次进入待对账。") from error
    if hashlib.sha256(source).hexdigest() != PRECISE_TARIFF_SHA256:
        raise ApiError(503, "价目表校验失败，本次进入待对账。")
    currency = tariff.get("currency", "USD")
    expected_group = "standard" if currency == "CNY" else "vip"
    if currency not in ("USD", "CNY") or tariff.get("version") != PRECISE_TARIFF_VERSION or tariff.get("group") != expected_group:
        raise ApiError(503, "价目表版本或分组不一致，本次进入待对账。")
    conversion_parameters = [("points_per_cny", POINTS_PER_CNY), ("cost_rate", COST_RATE)]
    if currency == "USD":
        conversion_parameters.append(("usd_cny_rate", USD_CNY_RATE))
    if any(Decimal(str(tariff.get(key))) != Decimal(str(value))
           for key, value in conversion_parameters):
        raise ApiError(503, "价目表换算参数与运行配置不一致，本次进入待对账。")
    models = as_object(tariff.get("models"))
    if model not in models or not isinstance(models[model], list) or len(models[model]) != 4:
        raise ApiError(409, "实际计费模型不在已批准价目表中，本次进入待对账。")
    if not isinstance(usage, dict) or any(type(usage.get(key)) is not int or usage[key] < 0
            for key in ("input_tokens", "output_tokens")):
        raise ApiError(409, "上游缺少完整的实际 Token 用量，本次进入待对账。")
    input_tokens = usage["input_tokens"]
    output_tokens = usage["output_tokens"]
    cached = usage.get("cached_input_tokens", 0)
    created = usage.get("cache_creation_input_tokens", 0)
    if any(type(value) is not int or value < 0 for value in (cached, created)):
        raise ApiError(409, "上游 Token 明细无效，本次进入待对账。")
    if cached + created > input_tokens:
        raise ApiError(409, "上游 Token 明细不一致，本次进入待对账。")
    prices = tuple(Decimal(str(value)) for value in models[model])
    if any(not value.is_finite() or value < 0 for value in prices):
        raise ApiError(503, "价目表存在无效价格，本次进入待对账。")
    usd = ((input_tokens - cached - created) * prices[0] +
           output_tokens * prices[1] + cached * prices[2] + created * prices[3]) / Decimal(1_000_000)
    cny = usd if currency == "CNY" else usd * Decimal(str(USD_CNY_RATE))
    return format(cny, "f")


def v2_confirm_saved(session: Session, request_id: str, logical_id: str,
                     result_sha256: str, receipt_id: str, locally_valid: bool) -> dict[str, Any]:
    with database() as db:
        billing_v2.ensure_schema(db)
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute(
                """SELECT a.code_id,a.requested_model,a.response_model,a.provider_usage_json,
                          a.state,a.reserved_units,a.amount_units,t.task_type
                   FROM por_v2_attempts a JOIN por_v2_tasks t
                   ON t.app_name=a.app_name AND t.code_id=a.code_id
                     AND t.logical_task_id=a.logical_task_id WHERE a.request_id=?""",
                (request_id,),
            ).fetchone()
            if row is None or row["code_id"] != session.code_id:
                raise ApiError(404, "模型尝试记录不存在。")
            if row["state"] == "receipt_expired_no_charge" and locally_valid and not session.unlimited:
                current = precise_license_balance(session)
                required = v2_required_units(row)
                if current["remaining_units"] - v2_locked_units(db, session.code_id) < required:
                    raise ApiError(402, "余额已被其他任务预留，请先完成这些任务后再确认此结果。")
            state = billing_v2.confirm_saved(db, request_id, logical_id,
                                             result_sha256, receipt_id, locally_valid)
            db.execute("COMMIT")
        except billing_v2.BillingStateError as error:
            db.execute("ROLLBACK")
            raise ApiError(error.status, str(error)) from error
        except Exception:
            db.execute("ROLLBACK")
            raise
    if state == "charged":
        with database() as db:
            ledger = db.execute(
                "SELECT amount_units,balance_after_units FROM por_v2_ledger WHERE app_name=? AND code_id=? AND logical_task_id=?",
                (APP_NAME, session.code_id, logical_id),
            ).fetchone()
        if ledger is None:
            raise ApiError(503, "已结算任务缺少代理流水，已停止后续扣费。")
        return {"ok": True, "state": "charged", "charged_units": ledger["amount_units"],
                "remaining_units": ledger["balance_after_units"]}
    if state == "billing_pending":
        return v2_settle_existing(session, request_id)
    if state != "awaiting_bill":
        return {"ok": True, "state": state, "charged_units": 0}
    if PRECISE_BILLING_SOURCE != "versioned_tariff":
        return {"ok": True, "state": "awaiting_bill", "charged_units": 0}
    # The agreed customer tariff charges only the model's actual Token usage.
    # Any separately billed search/tool calls are a platform expense.
    if not PRECISE_TARIFF_VERSION:
        raise ApiError(503, "价目表版本缺失，本次进入待对账。")
    if not row["response_model"]:
        return {"ok": True, "state": "awaiting_bill", "charged_units": 0}
    usage = json.loads(row["provider_usage_json"])
    cost_cny = v2_tariff_cost_cny(row["response_model"], usage)
    if not billing_v2.SAFE_ID.fullmatch(PRECISE_TARIFF_VERSION):
        raise ApiError(503, "价目表版本格式无效，本次进入待对账。")
    bill_ref = "tariff:" + PRECISE_TARIFF_VERSION + ":" + hashlib.sha256(
        request_id.encode("utf-8")
    ).hexdigest()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            billing_v2.attach_trusted_bill(
                db, request_id, row["response_model"], cost_cny,
                bill_ref, "versioned_tariff", str(POINTS_PER_CNY), str(COST_RATE),
            )
            db.execute("COMMIT")
        except billing_v2.BillingStateError as error:
            db.execute("ROLLBACK")
            raise ApiError(error.status, str(error)) from error
        except Exception:
            db.execute("ROLLBACK")
            raise
    return v2_settle_existing(session, request_id)


def v2_settle_existing(session: Session, request_id: str) -> dict[str, Any]:
    with database() as db:
        try:
            result = billing_v2.settle(
                db, request_id,
                lambda logical, attempt, units, model, bill, cost: precise_license_consume(
                    session, logical, attempt, units, model, bill, cost
                ),
            )
        except (billing_v2.BillingStateError, ApiError) as error:
            # The complete result is retained on the device; do not convert a
            # pending exact settlement into a rounded or reserve-capped debit.
            return {"ok": True, "state": "billing_pending", "charged_units": 0,
                    "warning": str(error)}
    sync_authoritative_wallet(session, result["remaining_units"] // 1000)
    return {"ok": True, "state": "charged", "charged_units": result["amount_units"],
            "remaining_units": result["remaining_units"]}


def v2_retry_pending(session: Session, limit: int = 4) -> None:
    with database() as db:
        rows = db.execute(
            """SELECT request_id FROM por_v2_attempts WHERE app_name=? AND code_id=?
               AND state='billing_pending' LIMIT ?""",
            (APP_NAME, session.code_id, limit),
        ).fetchall()
    for row in rows:
        v2_settle_existing(session, row["request_id"])


def v2_reject_result(session: Session, request_id: str, logical_id: str) -> dict[str, Any]:
    with database() as db:
        billing_v2.ensure_schema(db)
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute("SELECT code_id FROM por_v2_attempts WHERE request_id=?", (request_id,)).fetchone()
            if row is None or row["code_id"] != session.code_id:
                raise ApiError(404, "模型尝试记录不存在。")
            state = billing_v2.confirm_saved(db, request_id, logical_id, "", "", False)
            db.execute("COMMIT")
            return {"ok": True, "state": state, "charged_units": 0}
        except billing_v2.BillingStateError as error:
            db.execute("ROLLBACK")
            raise ApiError(error.status, str(error)) from error
        except Exception:
            db.execute("ROLLBACK")
            raise


class Handler(BaseHTTPRequestHandler):
    server_version = "ProductOperationReportProxy/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Never log bodies, authorization headers, prompts, or provider replies.
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def json_response(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError as error:
            raise ApiError(400, "请求长度无效。") from error
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ApiError(413, "请求内容过大或为空。")
        try:
            return as_object(json.loads(self.rfile.read(length).decode("utf-8")))
        except ApiError:
            raise
        except Exception as error:
            raise ApiError(400, "请求 JSON 格式不正确。") from error

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path == "/health":
                self.json_response(200, {
                    "ok": True,
                    "service": "product-operation-report",
                    "models": list(ALLOWED_MODELS),
                    "provider_keyring": PROVIDER_KEYRING.health(),
                    "precise_billing_enabled": PRECISE_BILLING_ENABLED,
                    "precise_admission_enabled": PRECISE_ADMISSION_ENABLED,
                })
                return
            if path == "/wallet":
                session = require_session(self.headers)
                precise_request = (PRECISE_BILLING_ENABLED and
                                   self.headers.get("x-result-confirmation-capable") == "1")
                if precise_request:
                    v2_retry_pending(session)
                else:
                    release_stale_pending_billing(session)
                    try:
                        retry_pending_billing(session)
                    except ApiError:
                        # The failed settlement has already released its reservation;
                        # wallet status must remain available to the user.
                        pass
                with database() as db:
                    ensure_schema(db)
                    wallet = wallet_json_v2(session, db) if precise_request else wallet_json(session, db)
                    self.json_response(200, {"ok": True, "wallet": wallet})
                return
            if path == "/pricing":
                require_session(self.headers)
                self.json_response(200, {"ok": True, "pricing": pricing()})
                return
            raise ApiError(404, "unknown endpoint")
        except ApiError as error:
            self.json_response(error.status, {"ok": False, "message": error.message})
        except Exception:
            self.json_response(500, {"ok": False, "message": "服务器内部错误。"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path == "/billing/result/confirm":
                if not PRECISE_BILLING_ENABLED:
                    raise ApiError(404, "unknown endpoint")
                session = require_session(self.headers, verify=True)
                body = self.read_json()
                self.json_response(200, v2_confirm_saved(
                    session, text(body.get("request_id"), 240),
                    text(body.get("logical_task_id"), 240),
                    text(body.get("output_sha256"), 80),
                    text(body.get("receipt_id"), 240),
                    body.get("locally_valid") is True,
                ))
                return
            if path == "/billing/result/reject":
                if not PRECISE_BILLING_ENABLED:
                    raise ApiError(404, "unknown endpoint")
                session = require_session(self.headers)
                body = self.read_json()
                self.json_response(200, v2_reject_result(
                    session, text(body.get("request_id"), 240),
                    text(body.get("logical_task_id"), 240),
                ))
                return
            if path == "/session":
                token, _session = create_session(self.read_json())
                self.json_response(200, {"ok": True, "access_token": token, "expires_in": SESSION_TTL_SECONDS})
                return
            if path == "/wallet/redeem":
                session = require_session(self.headers, verify=True)
                payload = self.read_json()
                code = text(payload.get("activation_code"), 512)
                if not code:
                    raise ApiError(400, "请输入积分充值码。")
                added, wallet = redeem_points(session, code)
                self.json_response(200, {"ok": True, "message": "积分充值成功。", "added_points": milli_to_points(added), "wallet": wallet})
                return
            if path == "/chat/completions":
                self.proxy_chat()
                return
            raise ApiError(404, "unknown endpoint")
        except ApiError as error:
            self.json_response(error.status, {"ok": False, "message": error.message})
        except Exception:
            self.json_response(500, {"ok": False, "message": "服务器内部错误。"})

    def proxy_chat(self) -> None:
        session = require_session(self.headers, verify=True)
        body = self.read_json()
        precise_request = (PRECISE_BILLING_ENABLED and
                           self.headers.get("x-result-confirmation-capable") == "1")
        if precise_request and not PRECISE_ADMISSION_ENABLED:
            raise ApiError(503, "模型任务入口暂时关闭，已有积分和结果不受影响。")
        requested_model, input_estimate = validate_messages(body)
        request_id = text(self.headers.get("x-request-id"), 240)
        billing_request_id = text(self.headers.get("x-billing-request-id"), 240)
        report_id = text(self.headers.get("x-report-session-id"), 200)
        task_key = text(self.headers.get("x-task-key"), 200)
        task_type = text(self.headers.get("x-task-type"), 80)
        try:
            attempt = int(self.headers.get("x-task-attempt", "0"))
        except ValueError:
            attempt = 0
        if (
            not REQUEST_ID_RE.fullmatch(request_id)
            or not billing_request_id
            or not SAFE_TEXT_RE.fullmatch(billing_request_id)
            or not report_id
            or not task_key
            or not task_type
        ):
            raise ApiError(400, "模型任务标识不完整。")
        if task_type not in ALLOWED_TASK_TYPES or not SAFE_TEXT_RE.fullmatch(task_type):
            raise ApiError(400, "模型任务类型无效。")
        if attempt < 1 or attempt > 20:
            raise ApiError(400, "模型任务尝试次数无效。")
        model = model_for_task(task_type, requested_model)
        provider_candidates = provider_route_candidates(model)
        if not provider_candidates:
            raise ApiError(503, "模型服务密钥尚未在服务器配置。")
        temperature = body.get("temperature")
        if temperature is not None and (
            isinstance(temperature, bool) or not isinstance(temperature, (int, float))
            or not math.isfinite(float(temperature)) or float(temperature) < 0 or float(temperature) > 2
        ):
            raise ApiError(400, "模型 temperature 参数无效。")
        output_limit = min(MAX_OUTPUT_TOKENS, TASK_OUTPUT_RESERVES.get(task_type, MAX_OUTPUT_TOKENS))
        upstream_body = {
            "model": model,
            "messages": body["messages"],
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_completion_tokens": output_limit,
        }
        prompt_cache_key = text(body.get("prompt_cache_key"), 200)
        if prompt_cache_key and SAFE_TEXT_RE.fullmatch(prompt_cache_key):
            upstream_body["prompt_cache_key"] = prompt_cache_key
        if temperature is not None:
            upstream_body["temperature"] = float(temperature)
        if task_type in ("source_clean", "summary") and body.get("reasoning_effort") == "low":
            upstream_body["reasoning_effort"] = "low"
        # The server, not the untrusted client, decides which task may search.
        apply_server_task_options(upstream_body, task_type)
        uses_responses_api = task_type == "module_benchmark"
        if uses_responses_api:
            upstream_body = responses_request_body(upstream_body)
        upstream_endpoint_path = "responses" if uses_responses_api else "chat/completions"
        if precise_request:
            v2_start_attempt(session, billing_request_id, request_id,
                             task_key, task_type, model, input_estimate,
                             text(self.headers.get("x-manual-redo-of"), 240), report_id=report_id)
        else:
            reserve_request(
                session, request_id, report_id, task_key, task_type, model, attempt,
                input_estimate, billing_request_id,
            )
        upstream_data = json.dumps(upstream_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if not precise_request:
            mark_upstream_submitted(request_id)
        usage: dict[str, Any] | None = None
        final_usage_valid = False
        stream_error = False
        search_call_ids: set[str] = set()
        search_call_states: dict[str, str] = {}
        search_queries: dict[str, str] = {}
        search_evidence: dict[str, dict[str, str]] = {}
        search_metadata_sent = False
        output_chars = 0
        sent_content = False
        v2_chunks: list[str] = []
        client_open = True
        final_status = "failed"
        saw_done = False
        finish_reason = ""
        def send_search_metadata() -> None:
            nonlocal client_open, search_metadata_sent
            if task_type != "module_benchmark" or search_metadata_sent or not client_open:
                return
            search_metadata_sent = True
            successful_calls = {call_id for call_id, state in search_call_states.items() if state == "completed"}
            verified = bool(not stream_error and final_usage_valid and successful_calls and search_evidence
                            and (usage or {}).get("web_search_calls", 1) > 0)
            status = "verified" if verified else "attempted" if search_call_ids else "unavailable"
            call_ids = sorted(search_call_ids)
            status_payload = {
                "type": "por.search_status",
                "status": status,
                "search_calls": len(call_ids),
                "evidence_count": len(search_evidence) if verified else 0,
            }
            payloads: list[dict[str, Any]] = [status_payload]
            if verified:
                fallback_call_id = sorted(successful_calls)[0]
                for evidence_item in search_evidence.values():
                    payloads.append({
                        "type": "por.search_evidence",
                        "evidence": {
                            **evidence_item,
                            "callId": fallback_call_id,
                            "query": search_queries.get(fallback_call_id, ""),
                            "retrievedAt": utc_now(),
                        },
                    })
            try:
                for item in payloads:
                    encoded = json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    self.wfile.write(b"data: " + encoded + b"\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                client_open = False
        def send_chat_delta(delta: str) -> None:
            nonlocal client_open
            if not delta or not client_open:
                return
            payload = json.dumps(
                {"choices": [{"delta": {"content": delta}}]},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            try:
                self.wfile.write(b"data: " + payload + b"\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                client_open = False
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            if precise_request:
                self.send_header("X-POR-Precise-Billing", "1")
            self.send_header("Cache-Control", "no-cache, no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                for item_type, raw_line in provider_request_items(
                    provider_candidates, upstream_data, request_id, upstream_endpoint_path
                ):
                    forward_raw_line = not uses_responses_api
                    if item_type == "heartbeat":
                        if client_open:
                            try:
                                self.wfile.write(raw_line)
                                self.wfile.flush()
                            except (BrokenPipeError, ConnectionResetError, OSError):
                                client_open = False
                        continue
                    if len(raw_line) > 4 * 1024 * 1024:
                        raise ApiError(502, "模型服务返回单行内容过大。")
                    if raw_line.startswith(b"data:"):
                        data = raw_line[5:].strip()
                        if data == b"[DONE]":
                            saw_done = True
                            if precise_request:
                                # Do not let the desktop acknowledge a result
                                # before its server-side completion proof is durable.
                                forward_raw_line = False
                        elif data:
                            try:
                                event = as_object(json.loads(data.decode("utf-8", "replace")))
                                event_type = text(event.get("type"), 120)
                                response = event.get("response") if isinstance(event.get("response"), dict) else {}
                                if event.get("error") or event_type in ("error", "response.failed", "response.incomplete"):
                                    stream_error = True
                                if event_type == "response.completed" and response.get("status", "completed") != "completed":
                                    stream_error = True
                                if event_type in ("por.search_status", "por.search_evidence"):
                                    # Only this proxy may emit trusted internal metadata events.
                                    forward_raw_line = False
                                choices = event.get("choices")
                                previous_finish = finish_reason
                                stopped_here = isinstance(choices, list) and any(
                                    isinstance(choice, dict) and choice.get("finish_reason") == "stop" for choice in choices)
                                has_usage = (event.get("usage") is not None or response.get("usage") is not None
                                             or (not uses_responses_api and choices == [] and "usage" in event))
                                if has_usage:
                                    # A supplied malformed snapshot must invalidate an older valid one.
                                    usage = provider_usage(event)
                                    final_usage_valid = bool(usage and (
                                        event_type == "response.completed" if uses_responses_api
                                        else stopped_here or finish_reason == "stop"))
                                elif uses_responses_api and event_type == "response.completed":
                                    usage = None
                                    final_usage_valid = False
                                if task_type == "module_benchmark":
                                    calls, evidence_items = search_event_details(event)
                                    for call in calls:
                                        call_id = call["callId"]
                                        search_call_ids.add(call_id)
                                        if call.get("status"):
                                            search_call_states[call_id] = call["status"]
                                        if call.get("query"):
                                            search_queries[call_id] = call["query"]
                                    for evidence_item in evidence_items:
                                        search_evidence.setdefault(evidence_item["url"], evidence_item)
                                if uses_responses_api:
                                    response_delta = ""
                                    if event_type == "response.output_text.delta":
                                        response_delta = event.get("delta")
                                        if not isinstance(response_delta, str) or len(response_delta) > MAX_TEXT_CHARS:
                                            raise ApiError(502, "模型流式文本格式或长度无效。")
                                        if previous_finish and response_delta:
                                            stream_error = True
                                    elif event_type == "response.completed":
                                        finish_reason = "stop"
                                        final_text = responses_output_text(response)
                                        if precise_request and sent_content and final_text and final_text != "".join(v2_chunks):
                                            stream_error = True
                                        if not sent_content:
                                            response_delta = final_text
                                    elif event_type in ("response.failed", "response.incomplete", "error"):
                                        finish_reason = "error"
                                        error = event.get("error") if isinstance(event.get("error"), dict) else {}
                                        message = text(error.get("message") or event.get("message"), 500) or "Responses API返回失败。"
                                        if client_open:
                                            payload = json.dumps({"error": {"message": message}}, ensure_ascii=False).encode("utf-8")
                                            try:
                                                self.wfile.write(b"data: " + payload + b"\n\n")
                                                self.wfile.flush()
                                            except (BrokenPipeError, ConnectionResetError, OSError):
                                                client_open = False
                                    if response_delta:
                                        if output_chars + len(response_delta) > MAX_TEXT_CHARS:
                                            raise ApiError(502, "模型输出超过长度限制。")
                                        output_chars += len(response_delta)
                                        sent_content = True
                                        if precise_request:
                                            v2_chunks.append(response_delta)
                                        send_chat_delta(response_delta)
                                if isinstance(choices, list):
                                    for choice in choices:
                                        if isinstance(choice, dict) and choice.get("finish_reason") is not None:
                                            finish_reason = text(choice.get("finish_reason"), 80)
                                        delta = choice.get("delta", {}) if isinstance(choice, dict) else {}
                                        content = delta.get("content") if isinstance(delta, dict) else None
                                        if isinstance(content, str) and content:
                                            if previous_finish:
                                                stream_error = True
                                            if output_chars + len(content) > MAX_TEXT_CHARS:
                                                raise ApiError(502, "模型输出超过长度限制。")
                                            output_chars += len(content)
                                            sent_content = True
                                            if precise_request:
                                                v2_chunks.append(content)
                            except Exception:
                                stream_error = True
                                forward_raw_line = False
                    if raw_line.startswith(b"data:") and raw_line[5:].strip() == b"[DONE]":
                        send_search_metadata()
                    if client_open and forward_raw_line:
                        try:
                            self.wfile.write(raw_line)
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError, OSError):
                            client_open = False
            except HTTPError as error:
                stream_error = True
                error.read(16 * 1024)
                message = (
                    f"provider_route_unavailable：模型线路暂时不可用（{error.code}）"
                    if error.code in (401, 403, 404, 408, 425, 429) or error.code >= 500
                    else f"模型服务拒绝请求（{error.code}）。"
                )
                if client_open:
                    payload = json.dumps({"error": {"message": message}}, ensure_ascii=False).encode("utf-8")
                    try:
                        self.wfile.write(b"data: " + payload + b"\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        client_open = False
            except (URLError, TimeoutError, OSError):
                stream_error = True
                if client_open:
                    payload = json.dumps(
                        {"error": {"message": "provider_route_unavailable：模型线路连接失败。"}},
                        ensure_ascii=False,
                    ).encode("utf-8")
                    try:
                        self.wfile.write(b"data: " + payload + b"\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        client_open = False
            completed = (not stream_error and (bool(sent_content and finish_reason == "stop") if uses_responses_api
                         else provider_stream_completed(saw_done, finish_reason, usage, sent_content)))
            send_search_metadata()
            if completed and not saw_done and client_open and not precise_request:
                try:
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                    saw_done = True
                except (BrokenPipeError, ConnectionResetError, OSError):
                    client_open = False
            final_status = "success" if completed else "partial" if sent_content else "failed"
        except ApiError:
            if final_status == "failed" and (usage or sent_content):
                final_status = "partial"
            raise
        except Exception:
            final_status = "partial" if sent_content else "failed"
        finally:
            search_calls = max(len(search_call_ids), (usage or {}).get("web_search_calls", 0)) if task_type == "module_benchmark" else 0
            if precise_request:
                v2_state = v2_finish_attempt(request_id, final_status == "success" and client_open and final_usage_valid,
                                             "".join(v2_chunks),
                                             text(usage.get("response_model"), 200) if usage else "", usage)
                if final_status == "success" and v2_state == "awaiting_receipt" and client_open:
                    try:
                        self.wfile.write(b"data: [DONE]\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                elif final_status == "success" and client_open:
                    try:
                        message = json.dumps({"error": {"message": "上游缺少可核对的实际 Token 用量，结果未计费，请重试。"}},
                                             ensure_ascii=False).encode("utf-8")
                        self.wfile.write(b"data: " + message + b"\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
            else:
                settle_request(session, request_id, final_status, model, usage,
                               input_estimate, output_chars, sent_content, search_calls)


def main() -> None:
    if not PROVIDER_KEYRING.has_any_key():
        print("WARNING: no server-side provider key is configured; chat requests will be rejected.", flush=True)
    if PRECISE_BILLING_ENABLED:
        recover_interrupted_requests()
        with database() as db:
            ensure_schema(db)
            billing_v2.ensure_schema(db)
            db.execute("BEGIN IMMEDIATE")
            try:
                billing_v2.recover_interrupted(db)
                billing_v2.expire_unconfirmed(db)
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
    else:
        recover_interrupted_requests()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"ProductOperationReport proxy listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
