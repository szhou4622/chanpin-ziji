from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)


proxy_path = Path('server-updates/points-proxy-v1/product_report_proxy.py')
text = proxy_path.read_text(encoding='utf-8')

text = replace_once(
    text,
    'from typing import Any\n',
    'from typing import Any, Callable\n',
    'typing callable import',
)

text = replace_once(
    text,
    """          ,billing_error TEXT NOT NULL DEFAULT ''
          ,search_calls INTEGER NOT NULL DEFAULT 0
        );
""",
    """          ,billing_error TEXT NOT NULL DEFAULT ''
          ,search_calls INTEGER NOT NULL DEFAULT 0
          ,cancel_requested INTEGER NOT NULL DEFAULT 0
          ,cancel_requested_at TEXT
        );
""",
    'request lifecycle schema columns',
)

text = replace_once(
    text,
    """    if "search_calls" not in request_columns:
        db.execute("ALTER TABLE model_requests ADD COLUMN search_calls INTEGER NOT NULL DEFAULT 0")
""",
    """    if "search_calls" not in request_columns:
        db.execute("ALTER TABLE model_requests ADD COLUMN search_calls INTEGER NOT NULL DEFAULT 0")
    if "cancel_requested" not in request_columns:
        db.execute("ALTER TABLE model_requests ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
    if "cancel_requested_at" not in request_columns:
        db.execute("ALTER TABLE model_requests ADD COLUMN cancel_requested_at TEXT")
""",
    'request lifecycle schema migration',
)

marker = "\n\ndef finalize_billing_request(\n"
if text.count(marker) != 1:
    raise SystemExit('request lifecycle helpers insertion marker mismatch')
helpers = r'''

def request_api_path(path: str) -> tuple[str, str] | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) == 2 and parts[0] == "requests" and REQUEST_ID_RE.fullmatch(parts[1]):
        return parts[1], "status"
    if len(parts) == 3 and parts[0] == "requests" and parts[2] == "cancel" and REQUEST_ID_RE.fullmatch(parts[1]):
        return parts[1], "cancel"
    return None


def request_state_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "requestId": row["request_id"],
        "reportSessionId": row["report_session_id"],
        "taskKey": row["task_key"],
        "taskType": row["task_type"],
        "model": row["model"],
        "attempt": int(row["attempt"]),
        "status": row["status"],
        "cancelRequested": bool(row["cancel_requested"]),
        "upstreamSubmitted": bool(row["upstream_submitted"]),
        "usageSource": row["usage_source"],
        "startedAt": row["started_at"],
        "endedAt": row["ended_at"],
    }


def request_state(session: Session, request_id: str) -> dict[str, Any]:
    with database() as db:
        ensure_schema(db)
        row = db.execute("SELECT * FROM model_requests WHERE request_id=?", (request_id,)).fetchone()
        if (
            not row
            or row["app_name"] != APP_NAME
            or row["code_id"] != session.code_id
            or row["machine_code"] != session.machine_code
        ):
            raise ApiError(404, "没有找到这个模型请求。")
        return request_state_payload(row)


def request_cancel(session: Session, request_id: str) -> dict[str, Any]:
    with database() as db:
        ensure_schema(db)
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM model_requests WHERE request_id=?", (request_id,)).fetchone()
        if (
            not row
            or row["app_name"] != APP_NAME
            or row["code_id"] != session.code_id
            or row["machine_code"] != session.machine_code
        ):
            db.execute("ROLLBACK")
            raise ApiError(404, "没有找到这个模型请求。")
        if row["status"] == "running" and not row["cancel_requested"]:
            db.execute(
                "UPDATE model_requests SET cancel_requested=1,cancel_requested_at=? WHERE request_id=? AND status='running'",
                (utc_now(), request_id),
            )
            row = db.execute("SELECT * FROM model_requests WHERE request_id=?", (request_id,)).fetchone()
        db.execute("COMMIT")
        return request_state_payload(row)


def request_cancel_requested(request_id: str) -> bool:
    with database() as db:
        ensure_schema(db)
        row = db.execute(
            "SELECT cancel_requested FROM model_requests WHERE request_id=? AND status='running'",
            (request_id,),
        ).fetchone()
        return bool(row and row[0])
'''
text = text.replace(marker, helpers + marker)

text = replace_once(
    text,
    """    if usage:
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
""",
    """    if usage:
        input_tokens = max(0, int(usage.get("input_tokens", 0)))
        output_tokens = max(0, int(usage.get("output_tokens", 0)))
        cached = max(0, min(input_tokens, int(usage.get("cached_input_tokens", 0))))
        created = max(0, min(input_tokens - cached, int(usage.get("cache_creation_input_tokens", 0))))
        usage_source = "provider"
        response_model = text(usage.get("response_model"), 200)
        charged, cost_cny = points_for_verified_usage(
            model, response_model, input_tokens, output_tokens, cached, created
        )
    else:
        # Estimates are admission/reservation hints only. They are never final user billing evidence.
        input_tokens = output_tokens = cached = created = 0
        usage_source = "missing"
        response_model = ""
        charged = 0
        cost_cny = 0.0
""",
    'actual usage only settlement',
)

old_provider = r'''def provider_request_items(
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
'''
new_provider = r'''def provider_request_items(
    candidates: tuple[ProviderRouteSnapshot, ...],
    upstream_data: bytes,
    request_id: str,
    endpoint_path: str = "chat/completions",
    heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS,
    should_cancel: Callable[[], bool] | None = None,
):
    """Open/read upstream with heartbeats and cooperative server-side cancellation.

    Cancellation is durable in SQLite. Once the provider response object exists we
    actively close it; if cancellation happens while urlopen is still waiting for
    response headers, the request thread can stop immediately and the worker closes
    the provider response as soon as that blocking open returns.
    """
    events: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=256)
    stop_event = threading.Event()
    upstream_lock = threading.Lock()
    upstream_holder: list[Any | None] = [None]

    def cancelled() -> bool:
        if stop_event.is_set():
            return True
        if should_cancel is None:
            return False
        try:
            return bool(should_cancel())
        except Exception:
            return False

    def put_event(kind: str, value: Any) -> None:
        while not stop_event.is_set():
            try:
                events.put((kind, value), timeout=0.1)
                return
            except queue.Full:
                continue

    def close_upstream() -> None:
        stop_event.set()
        with upstream_lock:
            upstream = upstream_holder[0]
        if upstream is not None:
            try:
                upstream.close()
            except Exception:
                pass

    def open_and_read() -> None:
        try:
            if cancelled():
                put_event("cancelled", None)
                return
            upstream = open_provider_stream(candidates, upstream_data, request_id, endpoint_path)
            with upstream_lock:
                upstream_holder[0] = upstream
            with upstream:
                if cancelled():
                    put_event("cancelled", None)
                    return
                for raw_line in upstream:
                    if cancelled():
                        put_event("cancelled", None)
                        return
                    put_event("line", raw_line)
        except BaseException as error:  # transferred back to the request thread
            if not stop_event.is_set():
                put_event("error", error)
        finally:
            with upstream_lock:
                upstream_holder[0] = None
            put_event("done", None)

    threading.Thread(target=open_and_read, name="por-provider-request", daemon=True).start()
    poll_seconds = min(max(0.01, heartbeat_seconds), 0.5)
    last_heartbeat = time.monotonic()
    try:
        while True:
            if cancelled():
                close_upstream()
                yield "cancelled", b""
                return
            try:
                kind, value = events.get(timeout=poll_seconds)
            except queue.Empty:
                if time.monotonic() - last_heartbeat >= max(0.01, heartbeat_seconds):
                    last_heartbeat = time.monotonic()
                    yield "heartbeat", b": heartbeat\n\n"
                continue
            if kind == "done":
                return
            if kind == "cancelled":
                close_upstream()
                yield "cancelled", b""
                return
            if kind == "error":
                raise value
            yield kind, value
    finally:
        close_upstream()
'''
text = replace_once(text, old_provider, new_provider, 'provider cooperative cancellation')

old_recovery = r'''def recover_interrupted_requests() -> None:
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
'''
new_recovery = r'''def recover_interrupted_requests() -> None:
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
                    "UPDATE model_requests SET status='interrupted_orphaned',usage_source='missing',charged_milli=0,ended_at=? WHERE request_id=?",
                    (utc_now(), row["request_id"]),
                )
                db.execute("COMMIT")
                continue
            # After process loss there is no trustworthy provider usage receipt in memory.
            # Never convert the admission estimate into a final user charge.
            now = utc_now()
            locked = max(0, wallet["locked_milli"] - row["reserved_milli"])
            db.execute(
                "UPDATE wallets SET locked_milli=?,updated_at=? WHERE app_name=? AND code_id=?",
                (locked, now, row["app_name"], row["code_id"]),
            )
            db.execute(
                "UPDATE model_requests SET status='interrupted',input_tokens=0,output_tokens=0,"
                "cached_input_tokens=0,cache_creation_input_tokens=0,usage_source='missing',cost_cny=0,"
                "charged_milli=0,billing_result_status='interrupted',billing_error='',ended_at=? WHERE request_id=?",
                (now, row["request_id"]),
            )
            db.execute("COMMIT")
'''
text = replace_once(text, old_recovery, new_recovery, 'interrupted actual usage only recovery')

text = replace_once(
    text,
    """            if path == "/pricing":
                require_session(self.headers)
                self.json_response(200, {"ok": True, "pricing": pricing()})
                return
            raise ApiError(404, "unknown endpoint")
""",
    """            if path == "/pricing":
                require_session(self.headers)
                self.json_response(200, {"ok": True, "pricing": pricing()})
                return
            request_route = request_api_path(path)
            if request_route and request_route[1] == "status":
                session = require_session(self.headers)
                self.json_response(200, {"ok": True, "request": request_state(session, request_route[0])})
                return
            raise ApiError(404, "unknown endpoint")
""",
    'request status endpoint',
)

text = replace_once(
    text,
    """            if path == "/chat/completions":
                self.proxy_chat()
                return
            raise ApiError(404, "unknown endpoint")
""",
    """            if path == "/chat/completions":
                self.proxy_chat()
                return
            request_route = request_api_path(path)
            if request_route and request_route[1] == "cancel":
                session = require_session(self.headers, verify=True)
                self.json_response(200, {"ok": True, "request": request_cancel(session, request_route[0])})
                return
            raise ApiError(404, "unknown endpoint")
""",
    'request cancel endpoint',
)

text = replace_once(
    text,
    """        client_open = True
        final_status = "failed"
        saw_done = False
""",
    """        client_open = True
        final_status = "failed"
        cancelled_upstream = False
        saw_done = False
""",
    'proxy cancel state',
)

text = replace_once(
    text,
    """                for item_type, raw_line in provider_request_items(
                    provider_candidates, upstream_data, request_id, upstream_endpoint_path
                ):
                    forward_raw_line = not uses_responses_api
                    if item_type == "heartbeat":
""",
    """                for item_type, raw_line in provider_request_items(
                    provider_candidates,
                    upstream_data,
                    request_id,
                    upstream_endpoint_path,
                    should_cancel=lambda: request_cancel_requested(request_id),
                ):
                    forward_raw_line = not uses_responses_api
                    if item_type == "cancelled":
                        cancelled_upstream = True
                        break
                    if item_type == "heartbeat":
""",
    'proxy provider cancel hook',
)

text = replace_once(
    text,
    """            completed = finish_reason != "error" and provider_stream_completed(saw_done, finish_reason, usage, sent_content)
            send_search_metadata()
            if completed and not saw_done and client_open:
""",
    """            completed = (
                not cancelled_upstream
                and finish_reason != "error"
                and provider_stream_completed(saw_done, finish_reason, usage, sent_content)
            )
            send_search_metadata()
            if completed and not saw_done and client_open:
""",
    'cancelled request not completed',
)

text = replace_once(
    text,
    """            final_status = "success" if completed else "partial" if sent_content else "failed"
""",
    """            final_status = (
                "aborted" if cancelled_upstream
                else "success" if completed
                else "partial" if sent_content
                else "failed"
            )
""",
    'cancelled final status',
)

proxy_path.write_text(text, encoding='utf-8')

nginx_path = Path('server-updates/points-proxy-v1/nginx-location.conf')
nginx = nginx_path.read_text(encoding='utf-8')
nginx = replace_once(
    nginx,
    """location = /api/product-operation-report/v1/chat/completions {
    limit_req zone=por_chat burst=8 nodelay;
    limit_conn por_conn 6;
    include /etc/nginx/snippets/product-operation-report-proxy.conf;
    proxy_read_timeout 360s;
    proxy_send_timeout 360s;
    proxy_pass http://127.0.0.1:8794/chat/completions;
}

# Unknown business-proxy routes must not be forwarded accidentally.
""",
    """location = /api/product-operation-report/v1/chat/completions {
    limit_req zone=por_chat burst=8 nodelay;
    limit_conn por_conn 6;
    include /etc/nginx/snippets/product-operation-report-proxy.conf;
    proxy_read_timeout 360s;
    proxy_send_timeout 360s;
    proxy_pass http://127.0.0.1:8794/chat/completions;
}

location ^~ /api/product-operation-report/v1/requests/ {
    limit_req zone=por_read burst=20 nodelay;
    limit_conn por_conn 10;
    include /etc/nginx/snippets/product-operation-report-proxy.conf;
    proxy_pass http://127.0.0.1:8794/requests/;
}

# Unknown business-proxy routes must not be forwarded accidentally.
""",
    'nginx request lifecycle route',
)
nginx_path.write_text(nginx, encoding='utf-8')
