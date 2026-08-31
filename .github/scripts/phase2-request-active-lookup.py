from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

proxy_path = Path('server-updates/points-proxy-v1/product_report_proxy.py')
text = proxy_path.read_text(encoding='utf-8')

marker = '''def request_state_payload(row: sqlite3.Row) -> dict[str, Any]:\n'''
if text.count(marker) != 1:
    raise SystemExit('active lookup helper marker mismatch')
helpers = '''def active_request_task_key(path: str) -> str | None:\n    parts = [part for part in path.split("/") if part]\n    if len(parts) == 3 and parts[0] == "requests" and parts[1] == "active" and SAFE_TEXT_RE.fullmatch(parts[2]):\n        return parts[2]\n    return None\n\n\ndef active_requests_for_task(session: Session, task_key: str) -> list[dict[str, Any]]:\n    if not SAFE_TEXT_RE.fullmatch(task_key):\n        raise ApiError(400, "模型任务标识无效。")\n    with database() as db:\n        ensure_schema(db)\n        rows = db.execute(\n            "SELECT * FROM model_requests WHERE app_name=? AND code_id=? AND machine_code=? "\n            "AND task_key=? AND status='running' ORDER BY started_at",\n            (APP_NAME, session.code_id, session.machine_code, task_key),\n        ).fetchall()\n        return [request_state_payload(row) for row in rows]\n\n\n'''
text = text.replace(marker, helpers + marker)

text = replace_once(
    text,
    '''            request_route = request_api_path(path)\n            if request_route and request_route[1] == "status":\n                session = require_session(self.headers)\n                self.json_response(200, {"ok": True, "request": request_state(session, request_route[0])})\n                return\n            raise ApiError(404, "unknown endpoint")\n''',
    '''            active_task_key = active_request_task_key(path)\n            if active_task_key:\n                session = require_session(self.headers)\n                self.json_response(200, {"ok": True, "requests": active_requests_for_task(session, active_task_key)})\n                return\n            request_route = request_api_path(path)\n            if request_route and request_route[1] == "status":\n                session = require_session(self.headers)\n                self.json_response(200, {"ok": True, "request": request_state(session, request_route[0])})\n                return\n            raise ApiError(404, "unknown endpoint")\n''',
    'active request lookup endpoint',
)

proxy_path.write_text(text, encoding='utf-8')

test_path = Path('server-updates/points-proxy-v1/test_request_lifecycle.py')
test = test_path.read_text(encoding='utf-8')
insert_marker = '''    def test_request_api_path_parser_accepts_only_canonical_request_ids(self) -> None:\n'''
if test.count(insert_marker) != 1:
    raise SystemExit('request lifecycle test insertion marker mismatch')
new_tests = '''    def test_active_request_lookup_finds_running_task_without_prior_request_id(self) -> None:\n        task_key = "report-a:module:v2:product-info"\n        first_id = self.reserve(task_key)\n        active = proxy.active_requests_for_task(self.session, task_key)\n        self.assertEqual([item["requestId"] for item in active], [first_id])\n        self.assertEqual(active[0]["taskKey"], task_key)\n        self.assertEqual(active[0]["status"], "running")\n\n        proxy.settle_request(\n            self.session, first_id, "success", "gpt-5.5",\n            {"input_tokens": 1000, "output_tokens": 100, "cached_input_tokens": 0,\n             "cache_creation_input_tokens": 0},\n            1000, 300, True,\n        )\n        self.assertEqual(proxy.active_requests_for_task(self.session, task_key), [])\n\n    def test_active_request_lookup_is_scoped_to_current_license_and_machine(self) -> None:\n        task_key = "report-a:module:v2:audience"\n        self.reserve(task_key)\n        other = proxy.Session(\n            token_hash="other", code_id="MAIN-B", machine_code="MACHINE-B", license_id="MAIN-B",\n            device_credential="credential-b", device_session="session-b", expires_at=9_999_999_999,\n        )\n        self.assertEqual(proxy.active_requests_for_task(other, task_key), [])\n\n    def test_active_request_path_parser_accepts_only_safe_task_keys(self) -> None:\n        task_key = "report-a:module:v2:product-info"\n        self.assertEqual(proxy.active_request_task_key(f"/requests/active/{task_key}"), task_key)\n        self.assertIsNone(proxy.active_request_task_key("/requests/active/bad%2Ftask"))\n        self.assertIsNone(proxy.active_request_task_key("/requests/active/../../wallet"))\n\n'''
test = test.replace(insert_marker, new_tests + insert_marker)
test_path.write_text(test, encoding='utf-8')

ci_path = Path('.github/workflows/ci.yml')
ci = ci_path.read_text(encoding='utf-8')
if 'name: Server proxy regression' not in ci:
    ci = ci.rstrip() + '''\n\n  server-regression:\n    name: Server proxy regression\n    runs-on: ubuntu-latest\n    timeout-minutes: 10\n    steps:\n      - name: Check out source\n        uses: actions/checkout@v6\n\n      - name: Run server proxy tests\n        run: python -m unittest discover -s server-updates/points-proxy-v1 -p 'test*.py' -v\n''' + '\n'
ci_path.write_text(ci, encoding='utf-8')
