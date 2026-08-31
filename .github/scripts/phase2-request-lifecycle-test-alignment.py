from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)


path = Path('server-updates/points-proxy-v1/test_proxy.py')
text = path.read_text(encoding='utf-8')

text = replace_once(
    text,
    '''    def test_missing_usage_with_content_is_not_free(self) -> None:\n        request_id = "f82324d3-df4f-42a4-badb-e0ba393b8f3f"\n        proxy.reserve_request(self.session, request_id, "report-b", "part:1", "final_part", "gpt-5.5", 1, 1200)\n        proxy.settle_request(self.session, request_id, "aborted", "gpt-5.5", None, 1200, 2400, True)\n        with proxy.database() as db:\n            row = db.execute("SELECT usage_source,charged_milli FROM model_requests WHERE request_id=?", (request_id,)).fetchone()\n        self.assertEqual(row["usage_source"], "estimated")\n        self.assertGreater(row["charged_milli"], 0)\n''',
    '''    def test_missing_usage_with_content_releases_reservation_without_user_charge(self) -> None:\n        request_id = "f82324d3-df4f-42a4-badb-e0ba393b8f3f"\n        proxy.reserve_request(self.session, request_id, "report-b", "part:1", "final_part", "gpt-5.5", 1, 1200)\n        proxy.settle_request(self.session, request_id, "aborted", "gpt-5.5", None, 1200, 2400, True)\n        with proxy.database() as db:\n            row = db.execute(\n                "SELECT status,usage_source,charged_milli,input_tokens,output_tokens FROM model_requests WHERE request_id=?",\n                (request_id,),\n            ).fetchone()\n            wallet = db.execute(\n                "SELECT balance_milli,locked_milli FROM wallets WHERE code_id=?", (self.session.code_id,)\n            ).fetchone()\n        self.assertEqual(row["status"], "aborted")\n        self.assertEqual(row["usage_source"], "missing")\n        self.assertEqual(row["charged_milli"], 0)\n        self.assertEqual(row["input_tokens"], 0)\n        self.assertEqual(row["output_tokens"], 0)\n        self.assertEqual(wallet["balance_milli"], 500_000)\n        self.assertEqual(wallet["locked_milli"], 0)\n        self.consume_mock.assert_not_called()\n''',
    'missing usage settlement contract',
)

text = replace_once(
    text,
    '    def test_empty_or_zero_provider_usage_falls_back_to_estimation(self) -> None:\n',
    '    def test_empty_or_zero_provider_usage_is_not_verified_usage(self) -> None:\n',
    'provider usage test name',
)

text = replace_once(
    text,
    '''    def test_restart_conservatively_settles_submitted_requests(self) -> None:\n        request_id = "d57e23b0-2e3f-4b3b-8af2-000000000001"\n        proxy.reserve_request(\n            self.session, request_id, "report-crash", "summary:crash", "summary", "gpt-5.5", 1, 1400\n        )\n        proxy.mark_upstream_submitted(request_id)\n        proxy.recover_interrupted_requests()\n        with proxy.database() as db:\n            request = db.execute(\n                "SELECT status,usage_source,charged_milli FROM model_requests WHERE request_id=?", (request_id,)\n            ).fetchone()\n            wallet = db.execute(\n                "SELECT balance_milli,locked_milli FROM wallets WHERE code_id=?", (self.session.code_id,)\n            ).fetchone()\n        self.assertEqual(request["status"], "billing_pending")\n        self.assertEqual(request["usage_source"], "estimated")\n        self.assertGreater(request["charged_milli"], 0)\n        self.assertGreater(wallet["locked_milli"], 0)\n        self.assertEqual(wallet["balance_milli"], 500_000)\n        proxy.retry_pending_billing(self.session)\n        with proxy.database() as db:\n            request = db.execute(\n                "SELECT status FROM model_requests WHERE request_id=?", (request_id,)\n            ).fetchone()\n            wallet = db.execute(\n                "SELECT balance_milli,locked_milli FROM wallets WHERE code_id=?", (self.session.code_id,)\n            ).fetchone()\n        self.assertEqual(request["status"], "interrupted_estimated")\n        self.assertEqual(wallet["locked_milli"], 0)\n        self.assertLess(wallet["balance_milli"], 500_000)\n''',
    '''    def test_restart_releases_submitted_request_when_provider_usage_is_unrecoverable(self) -> None:\n        request_id = "d57e23b0-2e3f-4b3b-8af2-000000000001"\n        proxy.reserve_request(\n            self.session, request_id, "report-crash", "summary:crash", "summary", "gpt-5.5", 1, 1400\n        )\n        proxy.mark_upstream_submitted(request_id)\n        proxy.recover_interrupted_requests()\n        with proxy.database() as db:\n            request = db.execute(\n                "SELECT status,usage_source,charged_milli,input_tokens,output_tokens FROM model_requests WHERE request_id=?",\n                (request_id,),\n            ).fetchone()\n            wallet = db.execute(\n                "SELECT balance_milli,locked_milli FROM wallets WHERE code_id=?", (self.session.code_id,)\n            ).fetchone()\n        self.assertEqual(request["status"], "interrupted")\n        self.assertEqual(request["usage_source"], "missing")\n        self.assertEqual(request["charged_milli"], 0)\n        self.assertEqual(request["input_tokens"], 0)\n        self.assertEqual(request["output_tokens"], 0)\n        self.assertEqual(wallet["locked_milli"], 0)\n        self.assertEqual(wallet["balance_milli"], 500_000)\n        self.consume_mock.assert_not_called()\n''',
    'restart settlement contract',
)

path.write_text(text, encoding='utf-8')
