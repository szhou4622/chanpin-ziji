#!/usr/bin/env python3
import importlib.util
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("product_report_proxy.py")
SPEC = importlib.util.spec_from_file_location("product_report_proxy_request_lifecycle", MODULE_PATH)
proxy = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = proxy
SPEC.loader.exec_module(proxy)


class RequestLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="por-request-lifecycle-")
        proxy.DB_PATH = os.path.join(self.temp.name, "points.sqlite3")
        self.session = proxy.Session(
            token_hash="test",
            code_id="MAIN-A",
            machine_code="MACHINE-A",
            license_id="MAIN-A",
            device_credential="credential",
            device_session="session",
            expires_at=9_999_999_999,
        )
        with proxy.database() as db:
            proxy.ensure_schema(db)
            now = proxy.utc_now()
            db.execute(
                "INSERT INTO wallets(app_name,code_id,machine_code,balance_milli,total_topup_milli,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (proxy.APP_NAME, self.session.code_id, self.session.machine_code, 500_000, 500_000, now, now),
            )
        self.consume_patch = patch.object(
            proxy, "consume_authoritative_credits", side_effect=self.fake_consume
        )
        self.consume_mock = self.consume_patch.start()

    def tearDown(self) -> None:
        self.consume_patch.stop()
        self.temp.cleanup()

    def fake_consume(self, session, amount_milli, billing_request_id, reason):
        with proxy.database() as db:
            wallet = db.execute(
                "SELECT balance_milli FROM wallets WHERE app_name=? AND code_id=?",
                (proxy.APP_NAME, session.code_id),
            ).fetchone()
        return max(0, wallet["balance_milli"] - amount_milli), session.unlimited

    def reserve(self, task_key: str = "module:v2:product-info") -> str:
        request_id = str(uuid.uuid4())
        proxy.reserve_request(
            self.session,
            request_id,
            "report-a",
            task_key,
            "module_product_info",
            "gpt-5.5",
            1,
            1000,
            task_key,
        )
        return request_id

    def test_request_state_and_cancel_are_owned_and_idempotent(self) -> None:
        request_id = self.reserve()

        before = proxy.request_state(self.session, request_id)
        self.assertEqual(before["status"], "running")
        self.assertFalse(before["cancelRequested"])

        first = proxy.request_cancel(self.session, request_id)
        second = proxy.request_cancel(self.session, request_id)

        self.assertTrue(first["cancelRequested"])
        self.assertTrue(second["cancelRequested"])
        self.assertEqual(first["status"], "running")
        self.assertTrue(proxy.request_cancel_requested(request_id))

        other = proxy.Session(
            token_hash="other",
            code_id="MAIN-B",
            machine_code="MACHINE-B",
            license_id="MAIN-B",
            device_credential="credential-b",
            device_session="session-b",
            expires_at=9_999_999_999,
        )
        with self.assertRaises(proxy.ApiError) as caught:
            proxy.request_state(other, request_id)
        self.assertEqual(caught.exception.status, 404)
        with self.assertRaises(proxy.ApiError) as caught:
            proxy.request_cancel(other, request_id)
        self.assertEqual(caught.exception.status, 404)

    def test_terminal_request_cancel_is_a_noop_and_keeps_terminal_status(self) -> None:
        request_id = self.reserve()
        proxy.settle_request(
            self.session,
            request_id,
            "success",
            "gpt-5.5",
            {"input_tokens": 1000, "output_tokens": 100, "cached_input_tokens": 0,
             "cache_creation_input_tokens": 0},
            1000,
            300,
            True,
        )

        state = proxy.request_cancel(self.session, request_id)
        self.assertEqual(state["status"], "success")
        self.assertFalse(state["cancelRequested"])

    def test_cancel_without_verified_provider_usage_never_estimate_charges_user(self) -> None:
        request_id = self.reserve("module:v2:no-usage")
        proxy.request_cancel(self.session, request_id)
        proxy.mark_upstream_submitted(request_id)

        proxy.settle_request(
            self.session,
            request_id,
            "aborted",
            "gpt-5.5",
            None,
            1000,
            900,
            True,
        )

        with proxy.database() as db:
            request = db.execute(
                "SELECT status,usage_source,charged_milli,input_tokens,output_tokens FROM model_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
            wallet = db.execute(
                "SELECT balance_milli,locked_milli FROM wallets WHERE app_name=? AND code_id=?",
                (proxy.APP_NAME, self.session.code_id),
            ).fetchone()
        self.assertEqual(request["status"], "aborted")
        self.assertEqual(request["usage_source"], "missing")
        self.assertEqual(request["charged_milli"], 0)
        self.assertEqual(request["input_tokens"], 0)
        self.assertEqual(request["output_tokens"], 0)
        self.assertEqual(wallet["balance_milli"], 500_000)
        self.assertEqual(wallet["locked_milli"], 0)
        self.consume_mock.assert_not_called()

    def test_cancel_with_verified_provider_usage_charges_only_real_usage(self) -> None:
        request_id = self.reserve("module:v2:verified-usage")
        proxy.request_cancel(self.session, request_id)
        usage = {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cached_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }

        proxy.settle_request(
            self.session,
            request_id,
            "aborted",
            "gpt-5.5",
            usage,
            99_999,
            99_999,
            True,
        )

        with proxy.database() as db:
            request = db.execute(
                "SELECT status,usage_source,charged_milli,input_tokens,output_tokens FROM model_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
        expected_charge, _cost = proxy.points_for_verified_usage(
            "gpt-5.5", "", 1000, 200, 0, 0
        )
        self.assertEqual(request["status"], "aborted")
        self.assertEqual(request["usage_source"], "provider")
        self.assertEqual(request["charged_milli"], expected_charge)
        self.assertEqual(request["input_tokens"], 1000)
        self.assertEqual(request["output_tokens"], 200)
        self.consume_mock.assert_called_once()
        self.assertEqual(self.consume_mock.call_args.args[1], expected_charge)

    def test_recovery_releases_interrupted_unverified_requests_without_estimate_charge(self) -> None:
        request_id = self.reserve("module:v2:interrupted")
        proxy.mark_upstream_submitted(request_id)

        proxy.recover_interrupted_requests()

        with proxy.database() as db:
            request = db.execute(
                "SELECT status,usage_source,charged_milli FROM model_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
            wallet = db.execute(
                "SELECT balance_milli,locked_milli FROM wallets WHERE app_name=? AND code_id=?",
                (proxy.APP_NAME, self.session.code_id),
            ).fetchone()
        self.assertEqual(request["status"], "interrupted")
        self.assertEqual(request["usage_source"], "missing")
        self.assertEqual(request["charged_milli"], 0)
        self.assertEqual(wallet["balance_milli"], 500_000)
        self.assertEqual(wallet["locked_milli"], 0)
        self.consume_mock.assert_not_called()

    def test_provider_request_generator_honors_cancel_before_upstream_open(self) -> None:
        with patch.object(proxy, "open_provider_stream") as opener:
            items = list(proxy.provider_request_items(
                tuple(), b"{}", str(uuid.uuid4()), heartbeat_seconds=0.005,
                should_cancel=lambda: True,
            ))
        self.assertEqual(items, [("cancelled", b"")])
        opener.assert_not_called()

    def test_active_request_lookup_finds_running_task_without_prior_request_id(self) -> None:
        task_key = "report-a:module:v2:product-info"
        first_id = self.reserve(task_key)
        active = proxy.active_requests_for_task(self.session, task_key)
        self.assertEqual([item["requestId"] for item in active], [first_id])
        self.assertEqual(active[0]["taskKey"], task_key)
        self.assertEqual(active[0]["status"], "running")

        proxy.settle_request(
            self.session, first_id, "success", "gpt-5.5",
            {"input_tokens": 1000, "output_tokens": 100, "cached_input_tokens": 0,
             "cache_creation_input_tokens": 0},
            1000, 300, True,
        )
        self.assertEqual(proxy.active_requests_for_task(self.session, task_key), [])

    def test_active_request_lookup_is_scoped_to_current_license_and_machine(self) -> None:
        task_key = "report-a:module:v2:audience"
        self.reserve(task_key)
        other = proxy.Session(
            token_hash="other", code_id="MAIN-B", machine_code="MACHINE-B", license_id="MAIN-B",
            device_credential="credential-b", device_session="session-b", expires_at=9_999_999_999,
        )
        self.assertEqual(proxy.active_requests_for_task(other, task_key), [])

    def test_active_request_path_parser_accepts_only_safe_task_keys(self) -> None:
        task_key = "report-a:module:v2:product-info"
        self.assertEqual(proxy.active_request_task_key(f"/requests/active/{task_key}"), task_key)
        self.assertIsNone(proxy.active_request_task_key("/requests/active/bad%2Ftask"))
        self.assertIsNone(proxy.active_request_task_key("/requests/active/../../wallet"))

    def test_request_api_path_parser_accepts_only_canonical_request_ids(self) -> None:
        request_id = str(uuid.uuid4())
        self.assertEqual(proxy.request_api_path(f"/requests/{request_id}"), (request_id, "status"))
        self.assertEqual(proxy.request_api_path(f"/requests/{request_id}/cancel"), (request_id, "cancel"))
        self.assertIsNone(proxy.request_api_path("/requests/not-a-request"))
        self.assertIsNone(proxy.request_api_path(f"/requests/{request_id}/other"))


if __name__ == "__main__":
    unittest.main()
