"""Per-result billing state machine for the isolated POR release.

No prompt, model output, activation code, provider key, or device credential is
stored here. A logical task may have many upstream attempts but one debit.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable


UNITS_PER_POINT = 1_000_000
SAFE_ID = re.compile(r"^[A-Za-z0-9_.:@/+\-]{1,240}$")


class BillingStateError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def _id(value: str, field: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise BillingStateError(f"invalid {field}", 400)
    return value


def amount_units(cost_cny: str, points_per_cny: str, cost_rate: str) -> int:
    if not isinstance(cost_cny, str) or not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d{1,12})?", cost_cny):
        raise BillingStateError("cost_cny must be a decimal string", 400)
    try:
        rate = Decimal(cost_rate)
        whole_points = (
            Decimal(cost_cny) * Decimal(points_per_cny) / rate
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        result = whole_points * UNITS_PER_POINT
    except (InvalidOperation, ZeroDivisionError) as error:
        raise BillingStateError("invalid pricing conversion", 503) from error
    if rate <= 0 or result < 0 or result > 9_000_000_000_000_000_000:
        raise BillingStateError("charge is outside supported precision", 409)
    return int(result)


def output_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _private_digest(public_digest: str) -> str:
    key = os.environ.get("POR_RESULT_PROOF_SECRET", "").encode("utf-8")
    if len(key) < 32:
        raise BillingStateError("result proof key is unavailable", 503)
    return hmac.new(key, public_digest.encode("ascii"), hashlib.sha256).hexdigest()


def ensure_schema(db: sqlite3.Connection) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS por_v2_tasks (
          app_name TEXT NOT NULL, code_id TEXT NOT NULL,
          logical_task_id TEXT NOT NULL, task_key TEXT NOT NULL,
          task_type TEXT NOT NULL, state TEXT NOT NULL,
          redo_of TEXT NOT NULL DEFAULT '', charged_attempt_id TEXT NOT NULL DEFAULT '',
          charge_units INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(app_name, code_id, logical_task_id)
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS por_v2_attempts (
          request_id TEXT PRIMARY KEY, app_name TEXT NOT NULL, code_id TEXT NOT NULL,
          logical_task_id TEXT NOT NULL, requested_model TEXT NOT NULL,
          response_model TEXT NOT NULL DEFAULT '', state TEXT NOT NULL,
          output_sha256 TEXT NOT NULL DEFAULT '', output_bytes INTEGER NOT NULL DEFAULT 0,
          reserved_units INTEGER NOT NULL DEFAULT 0,
          provider_usage_json TEXT NOT NULL DEFAULT '', receipt_sha256 TEXT NOT NULL DEFAULT '',
          billed_model TEXT NOT NULL DEFAULT '', bill_ref TEXT NOT NULL DEFAULT '',
          cost_cny TEXT NOT NULL DEFAULT '', cost_source TEXT NOT NULL DEFAULT '',
          amount_units INTEGER NOT NULL DEFAULT 0,
          started_at TEXT NOT NULL, finished_at TEXT NOT NULL DEFAULT ''
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS por_v2_ledger (
          app_name TEXT NOT NULL, code_id TEXT NOT NULL,
          logical_task_id TEXT NOT NULL, request_id TEXT NOT NULL,
          amount_units INTEGER NOT NULL, balance_after_units INTEGER NOT NULL,
          central_transaction_id TEXT NOT NULL, cost_source TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(app_name, code_id, logical_task_id)
        )"""
    )


def start_attempt(
    db: sqlite3.Connection, app_name: str, code_id: str,
    logical_task_id: str, task_key: str, task_type: str,
    request_id: str, requested_model: str, redo_of: str = "",
    reserved_units: int = 0,
) -> str:
    for field, value in (
        ("app_name", app_name), ("code_id", code_id),
        ("logical_task_id", logical_task_id), ("task_key", task_key),
        ("task_type", task_type), ("request_id", request_id),
        ("requested_model", requested_model),
    ):
        _id(value, field)
    if redo_of:
        _id(redo_of, "redo_of")
    if type(reserved_units) is not int or reserved_units < 0:
        raise BillingStateError("invalid reservation", 400)
    existing_attempt = db.execute(
        "SELECT logical_task_id FROM por_v2_attempts WHERE request_id=?", (request_id,)
    ).fetchone()
    if existing_attempt:
        raise BillingStateError("attempt request_id already exists")
    task = db.execute(
        "SELECT state,task_key FROM por_v2_tasks WHERE app_name=? AND code_id=? AND logical_task_id=?",
        (app_name, code_id, logical_task_id),
    ).fetchone()
    if task is None:
        active_same_key = db.execute(
            """SELECT 1 FROM por_v2_tasks WHERE app_name=? AND code_id=? AND task_key=?
               AND state IN ('running','awaiting_receipt','awaiting_bill','billing_pending') LIMIT 1""",
            (app_name, code_id, task_key),
        ).fetchone()
        if active_same_key:
            raise BillingStateError("same task already has an unsettled attempt")
        prior = db.execute(
            """SELECT logical_task_id FROM por_v2_tasks
               WHERE app_name=? AND code_id=? AND task_key=? AND state='charged'
               ORDER BY rowid DESC LIMIT 1""",
            (app_name, code_id, task_key),
        ).fetchone()
        if prior is not None and (not redo_of or redo_of != prior["logical_task_id"]):
            raise BillingStateError("completed task requires an explicit redo identity")
        if redo_of and prior is None:
            raise BillingStateError("redo target is not a charged task")
        db.execute(
            "INSERT INTO por_v2_tasks(app_name,code_id,logical_task_id,task_key,task_type,state,redo_of) VALUES(?,?,?,?,?,'running',?)",
            (app_name, code_id, logical_task_id, task_key, task_type, redo_of),
        )
    else:
        if task["task_key"] != task_key:
            raise BillingStateError("logical task id conflicts with another task")
        if task["state"] not in ("retryable", "interrupted"):
            raise BillingStateError("logical task is already active or complete")
        db.execute(
            "UPDATE por_v2_tasks SET state='running' WHERE app_name=? AND code_id=? AND logical_task_id=?",
            (app_name, code_id, logical_task_id),
        )
    db.execute(
        "INSERT INTO por_v2_attempts(request_id,app_name,code_id,logical_task_id,requested_model,state,reserved_units,started_at) VALUES(?,?,?,?,?,'running',?,?)",
        (request_id, app_name, code_id, logical_task_id, requested_model, reserved_units, _now()),
    )
    return "running"


def finish_attempt(
    db: sqlite3.Connection, request_id: str, complete: bool,
    content: str, response_model: str, usage: dict[str, int] | None,
) -> str:
    attempt = db.execute(
        "SELECT app_name,code_id,logical_task_id,state FROM por_v2_attempts WHERE request_id=?",
        (request_id,),
    ).fetchone()
    if attempt is None or attempt["state"] != "running":
        raise BillingStateError("attempt is not running")
    # The proxy must have observed a normal provider finish itself. A client
    # receipt cannot turn an interrupted stream into a completed attempt.
    valid = bool(complete and content.strip() and usage)
    state = "awaiting_receipt" if valid else "failed_no_charge"
    safe_model = _id(response_model, "response_model") if response_model else ""
    usage_json = json.dumps(usage, sort_keys=True, separators=(",", ":")) if usage else ""
    db.execute(
        """UPDATE por_v2_attempts SET state=?,response_model=?,output_sha256=?,
                  output_bytes=?,provider_usage_json=?,finished_at=? WHERE request_id=?""",
        (state, safe_model, _private_digest(output_digest(content)) if content else "",
         len(content.encode("utf-8")), usage_json, _now(), request_id),
    )
    db.execute(
        "UPDATE por_v2_tasks SET state=? WHERE app_name=? AND code_id=? AND logical_task_id=?",
        ("awaiting_receipt" if valid else "retryable", attempt["app_name"],
         attempt["code_id"], attempt["logical_task_id"]),
    )
    return state


def confirm_saved(
    db: sqlite3.Connection, request_id: str, logical_task_id: str,
    received_sha256: str, receipt_id: str, locally_valid: bool,
) -> str:
    attempt = db.execute(
        """SELECT app_name,code_id,logical_task_id,state,output_sha256
           FROM por_v2_attempts WHERE request_id=?""", (request_id,)
    ).fetchone()
    if attempt is None or attempt["logical_task_id"] != logical_task_id:
        raise BillingStateError("result confirmation does not match an attempt")
    if attempt["state"] == "receipt_expired_no_charge":
        task = db.execute(
            "SELECT state FROM por_v2_tasks WHERE app_name=? AND code_id=? AND logical_task_id=?",
            (attempt["app_name"], attempt["code_id"], logical_task_id),
        ).fetchone()
        if task is None or task["state"] != "retryable":
            raise BillingStateError("result confirmation arrived after another attempt began")
        db.execute("UPDATE por_v2_attempts SET state='awaiting_receipt' WHERE request_id=?", (request_id,))
        db.execute(
            "UPDATE por_v2_tasks SET state='awaiting_receipt' WHERE app_name=? AND code_id=? AND logical_task_id=?",
            (attempt["app_name"], attempt["code_id"], logical_task_id),
        )
        attempt = db.execute(
            "SELECT app_name,code_id,logical_task_id,state,output_sha256 FROM por_v2_attempts WHERE request_id=?",
            (request_id,),
        ).fetchone()
    if attempt["state"] in ("awaiting_bill", "billing_pending", "charged"):
        if locally_valid and re.fullmatch(r"[0-9a-f]{64}", received_sha256) and hmac.compare_digest(
            _private_digest(received_sha256), attempt["output_sha256"]
        ):
            return attempt["state"]
        raise BillingStateError("result confirmation conflicts with an earlier receipt")
    if attempt["state"] != "awaiting_receipt":
        raise BillingStateError("attempt is not awaiting result confirmation")
    if not locally_valid:
        db.execute("UPDATE por_v2_attempts SET state='failed_no_charge' WHERE request_id=?", (request_id,))
        db.execute(
            "UPDATE por_v2_tasks SET state='retryable' WHERE app_name=? AND code_id=? AND logical_task_id=?",
            (attempt["app_name"], attempt["code_id"], logical_task_id),
        )
        return "failed_no_charge"
    if not re.fullmatch(r"[0-9a-f]{64}", received_sha256) or not hmac.compare_digest(
        _private_digest(received_sha256), attempt["output_sha256"]
    ):
        raise BillingStateError("saved result hash does not match provider output")
    _id(receipt_id, "receipt_id")
    db.execute(
        "UPDATE por_v2_attempts SET state='awaiting_bill',receipt_sha256=? WHERE request_id=?",
        (_private_digest(hashlib.sha256(receipt_id.encode()).hexdigest()), request_id),
    )
    db.execute(
        "UPDATE por_v2_tasks SET state='awaiting_bill' WHERE app_name=? AND code_id=? AND logical_task_id=?",
        (attempt["app_name"], attempt["code_id"], logical_task_id),
    )
    return "awaiting_bill"


def attach_trusted_bill(
    db: sqlite3.Connection, request_id: str, billed_model: str,
    cost_cny: str, bill_ref: str, source: str,
    points_per_cny: str = "100", cost_rate: str = "0.5",
) -> int:
    if source not in ("ccg_verified", "versioned_tariff", "isolated_mock"):
        raise BillingStateError("untrusted billing source", 403)
    attempt = db.execute(
        "SELECT state FROM por_v2_attempts WHERE request_id=?", (request_id,)
    ).fetchone()
    if attempt is None or attempt["state"] != "awaiting_bill":
        raise BillingStateError("attempt is not awaiting a bill")
    units = amount_units(cost_cny, points_per_cny, cost_rate)
    db.execute(
        """UPDATE por_v2_attempts SET state='billing_pending',billed_model=?,
                  bill_ref=?,cost_cny=?,cost_source=?,amount_units=? WHERE request_id=?""",
        (_id(billed_model, "billed_model"), _id(bill_ref, "bill_ref"),
         cost_cny, source, units, request_id),
    )
    return units


def settle(
    db: sqlite3.Connection, request_id: str,
    central_consume: Callable[[str, str, int, str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    attempt = db.execute(
        "SELECT * FROM por_v2_attempts WHERE request_id=?", (request_id,)
    ).fetchone()
    if attempt is None or attempt["state"] not in ("billing_pending", "charged"):
        raise BillingStateError("attempt has no verified charge")
    if attempt["state"] == "charged":
        prior = db.execute(
            "SELECT * FROM por_v2_ledger WHERE app_name=? AND code_id=? AND logical_task_id=?",
            (attempt["app_name"], attempt["code_id"], attempt["logical_task_id"]),
        ).fetchone()
        if prior is None:
            raise BillingStateError("charged attempt has no ledger row", 500)
        return {"idempotent": True, "remaining_units": prior["balance_after_units"],
                "amount_units": prior["amount_units"]}
    result = central_consume(
        attempt["logical_task_id"], request_id, int(attempt["amount_units"]),
        attempt["billed_model"], attempt["bill_ref"], attempt["cost_cny"],
    )
    if not result.get("ok") or type(result.get("remaining_units")) is not int:
        raise BillingStateError("central exact settlement was not confirmed", 503)
    db.execute("BEGIN IMMEDIATE")
    try:
        prior = db.execute(
            "SELECT request_id,amount_units FROM por_v2_ledger WHERE app_name=? AND code_id=? AND logical_task_id=?",
            (attempt["app_name"], attempt["code_id"], attempt["logical_task_id"]),
        ).fetchone()
        if prior and (prior["request_id"] != request_id or prior["amount_units"] != attempt["amount_units"]):
            raise BillingStateError("local logical task ledger conflicts with central settlement", 409)
        if prior is None:
            db.execute(
                """INSERT INTO por_v2_ledger VALUES(?,?,?,?,?,?,?,?,?)""",
                (attempt["app_name"], attempt["code_id"], attempt["logical_task_id"],
                 request_id, int(attempt["amount_units"]), result["remaining_units"],
                 result["transaction_id"], attempt["cost_source"], _now()),
            )
        db.execute("UPDATE por_v2_attempts SET state='charged' WHERE request_id=?", (request_id,))
        db.execute(
            """UPDATE por_v2_tasks SET state='charged',charged_attempt_id=?,charge_units=?
               WHERE app_name=? AND code_id=? AND logical_task_id=?""",
            (request_id, int(attempt["amount_units"]), attempt["app_name"],
             attempt["code_id"], attempt["logical_task_id"]),
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return {"idempotent": bool(result.get("idempotent")),
            "remaining_units": result["remaining_units"],
            "amount_units": int(attempt["amount_units"])}


def recover_interrupted(db: sqlite3.Connection) -> int:
    rows = db.execute(
        "SELECT request_id,app_name,code_id,logical_task_id FROM por_v2_attempts WHERE state='running'"
    ).fetchall()
    for row in rows:
        db.execute(
            "UPDATE por_v2_attempts SET state='interrupted_no_charge',finished_at=? WHERE request_id=?",
            (_now(), row["request_id"]),
        )
        db.execute(
            "UPDATE por_v2_tasks SET state='interrupted' WHERE app_name=? AND code_id=? AND logical_task_id=?",
            (row["app_name"], row["code_id"], row["logical_task_id"]),
        )
    return len(rows)


def expire_unconfirmed(db: sqlite3.Connection, maximum_age_seconds: int = 900) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=maximum_age_seconds)).isoformat().replace("+00:00", "Z")
    rows = db.execute(
        """SELECT request_id,app_name,code_id,logical_task_id FROM por_v2_attempts
           WHERE state='awaiting_receipt' AND finished_at!='' AND finished_at<?""",
        (cutoff,),
    ).fetchall()
    for row in rows:
        db.execute(
            "UPDATE por_v2_attempts SET state='receipt_expired_no_charge' WHERE request_id=?",
            (row["request_id"],),
        )
        db.execute(
            """UPDATE por_v2_tasks SET state='retryable'
               WHERE app_name=? AND code_id=? AND logical_task_id=? AND state='awaiting_receipt'""",
            (row["app_name"], row["code_id"], row["logical_task_id"]),
        )
    return len(rows)
