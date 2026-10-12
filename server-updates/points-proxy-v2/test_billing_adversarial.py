"""Offline state-machine and proxy billing counterexamples; in-memory data only."""

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import os
import sqlite3
import threading
import unittest
import uuid
from unittest.mock import patch

import por_billing_v2 as billing
import product_report_proxy as proxy
from provider_config import MANAGED_MODEL


class BillingFixtures(unittest.TestCase):
    def setUp(self):
        self.uri = f"file:billing-adversarial-{uuid.uuid4().hex}?mode=memory&cache=shared"
        self.db = self.connection()
        billing.ensure_schema(self.db)
        self.secret = patch.dict(os.environ, {"POR_RESULT_PROOF_SECRET": "offline-billing-proof-secret-long-enough"})
        self.secret.start()
        self.addCleanup(self.secret.stop)
        self.addCleanup(self.db.close)
        self.central_lock = threading.Lock()
        self.balance = 100_000_000
        self.debits = {}
        self.central_calls = 0

    def connection(self):
        db = sqlite3.connect(self.uri, uri=True, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def start(self, request="attempt-1", logical="logical-1", key="source:batch-1", **kwargs):
        return billing.start_attempt(self.db, proxy.APP_NAME, "license-1", logical,
                                     key, "source_clean", request, MANAGED_MODEL, **kwargs)

    def finish(self, request="attempt-1", complete=True, content="saved output", usage=None):
        return billing.finish_attempt(self.db, request, complete, content, MANAGED_MODEL,
                                      {"input_tokens": 1000, "output_tokens": 1000}
                                      if usage is None else usage)

    def confirm(self, request="attempt-1", logical="logical-1", **kwargs):
        arguments = {"received_sha256": billing.output_digest("saved output"),
                     "receipt_id": "receipt-1", "locally_valid": True, **kwargs}
        return billing.confirm_saved(self.db, request, logical, **arguments)

    def bill(self, request="attempt-1", **kwargs):
        arguments = {"billed_model": MANAGED_MODEL, "cost_cny": "0.036",
                     "bill_ref": "tariff:offline-1", "source": "versioned_tariff", **kwargs}
        return billing.attach_trusted_bill(self.db, request, **arguments)

    def pending(self, request="attempt-1", logical="logical-1", key="source:batch-1"):
        self.start(request, logical, key)
        self.finish(request)
        self.confirm(request, logical)
        self.bill(request)

    def consume(self, logical, attempt, units, model, bill, cost):
        with self.central_lock:
            self.central_calls += 1
            prior = self.debits.get(logical)
            evidence = (attempt, units, model, bill, cost)
            if prior is None:
                self.balance -= units
                prior = {"evidence": evidence, "remaining_units": self.balance,
                         "transaction_id": "central:" + logical}
                self.debits[logical] = prior
                idempotent = False
            else:
                if prior["evidence"] != evidence:
                    raise AssertionError("central idempotency evidence changed")
                idempotent = True
            return {"ok": True, "remaining_units": prior["remaining_units"],
                    "transaction_id": prior["transaction_id"], "idempotent": idempotent,
                    "amount_units": units, "logical_task_id": logical, "attempt_id": attempt}

    def attempt_state(self, request="attempt-1"):
        return self.db.execute("SELECT state FROM por_v2_attempts WHERE request_id=?", (request,)).fetchone()[0]

    def task_state(self, logical="logical-1"):
        return self.db.execute("SELECT state FROM por_v2_tasks WHERE logical_task_id=?", (logical,)).fetchone()[0]

    def expire(self, request="attempt-1"):
        self.db.execute("UPDATE por_v2_attempts SET finished_at='2000-01-01T00:00:00Z' WHERE request_id=?", (request,))
        return billing.expire_unconfirmed(self.db)


class BillingAdversarialTests(BillingFixtures):
    def test_rounding_keeps_actual_cost_times_two_with_integer_points(self):
        for cost, units in (("0.12", 24_000_000), ("0.036", 7_000_000),
                            ("0.0025", 1_000_000), ("0.000318", 0)):
            with self.subTest(cost=cost):
                self.assertEqual(billing.amount_units(cost, "100", "0.5"), units)

    def test_nonfinite_or_nonpositive_conversion_never_becomes_a_free_bill(self):
        for name in ("cost_rate", "points_per_cny"):
            for value in ("Infinity", "-Infinity", "NaN", "0", "-1", "invalid", None):
                with self.subTest(name=name, value=value):
                    args = {"cost_cny": "0.1", "points_per_cny": "100", "cost_rate": "0.5", name: value}
                    with self.assertRaises(billing.BillingStateError) as caught:
                        billing.amount_units(**args)
                    self.assertEqual(caught.exception.status, 503)

    def test_missing_or_malformed_usage_cannot_create_a_billable_result(self):
        invalid = [None, {}, {"input_tokens": 12}, {"output_tokens": 2},
                   {"input_tokens": 10, "output_tokens": True},
                   {"input_tokens": 10, "output_tokens": "2"},
                   {"input_tokens": 10, "output_tokens": -1},
                   {"input_tokens": 10, "output_tokens": 2, "cached_input_tokens": 11},
                   {"input_tokens": 10, "output_tokens": 2, "cache_creation_input_tokens": 1.5},
                   {"input_tokens": 10, "output_tokens": 2,
                    "cached_input_tokens": 9, "cache_creation_input_tokens": 2}]
        for index, usage in enumerate(invalid):
            with self.subTest(usage=usage):
                request, logical = f"bad-{index}", f"bad-logical-{index}"
                self.start(request, logical, f"key-{index}")
                self.assertEqual(billing.finish_attempt(self.db, request, True, "output", MANAGED_MODEL, usage),
                                 "failed_no_charge")
                with self.assertRaises(billing.BillingStateError):
                    self.confirm(request, logical)
        self.assertFalse(self.debits)

    def test_incomplete_or_empty_output_never_accepts_a_receipt(self):
        for index, (complete, content) in enumerate(((False, "partial"), (True, " \n"))):
            request, logical = f"failed-{index}", f"failed-logical-{index}"
            self.start(request, logical, f"key-{index}")
            self.assertEqual(self.finish(request, complete, content), "failed_no_charge")
            with self.assertRaises(billing.BillingStateError):
                self.confirm(request, logical, received_sha256=billing.output_digest(content))

    def test_repeated_valid_confirmation_and_bill_are_idempotent_in_every_saved_state(self):
        self.start()
        self.finish()
        self.assertEqual(self.confirm(), "awaiting_bill")
        self.assertEqual(self.confirm(receipt_id="fresh-desktop-receipt"), "awaiting_bill")
        self.assertEqual(self.bill(), 7_000_000)
        self.assertEqual(self.task_state(), "billing_pending")
        self.assertEqual(self.confirm(), "billing_pending")
        self.assertEqual(self.bill(cost_cny="0.036000"), 7_000_000)
        first = billing.settle(self.db, "attempt-1", self.consume)
        self.assertEqual(self.confirm(), "charged")
        self.assertEqual(self.bill(), 7_000_000)
        again = billing.settle(self.db, "attempt-1", self.consume)
        self.assertEqual(first["amount_units"], again["amount_units"])
        self.assertEqual(first["remaining_units"], again["remaining_units"])
        self.assertTrue(again["idempotent"])
        self.assertEqual(self.central_calls, 1)

    def test_conflicting_bill_evidence_is_rejected_before_and_after_charge(self):
        self.pending()
        conflicts = ({"billed_model": "different-model"}, {"cost_cny": "0.037"},
                     {"bill_ref": "tariff:different"}, {"source": "isolated_mock"},
                     {"points_per_cny": "200"})
        for state in ("billing_pending", "charged"):
            for changed in conflicts:
                with self.subTest(state=state, changed=changed):
                    with self.assertRaises(billing.BillingStateError) as caught:
                        self.bill(**changed)
                    self.assertEqual(caught.exception.status, 409)
                    self.assertEqual(self.attempt_state(), state)
            if state == "billing_pending":
                billing.settle(self.db, "attempt-1", self.consume)
        self.assertEqual(self.central_calls, 1)

    def test_changed_proof_or_invalid_receipt_does_not_replace_accepted_confirmation(self):
        self.pending()
        for changed in ({"received_sha256": billing.output_digest("other output")},
                        {"received_sha256": None}, {"receipt_id": ""}, {"locally_valid": False}):
            with self.subTest(changed=changed):
                with self.assertRaises(billing.BillingStateError):
                    self.confirm(**changed)
        self.assertEqual(self.attempt_state(), "billing_pending")

    def test_rejection_is_idempotent_and_cannot_reset_a_new_retry(self):
        self.start()
        self.finish()
        self.assertEqual(self.confirm(locally_valid=False), "failed_no_charge")
        self.assertEqual(self.confirm(locally_valid=False), "failed_no_charge")
        self.start("attempt-2")
        self.assertEqual(self.confirm(locally_valid=False), "failed_no_charge")
        self.assertEqual(self.task_state(), "running")
        self.assertEqual(self.attempt_state("attempt-2"), "running")

    def test_expiry_can_recover_the_latest_saved_result_without_a_second_attempt(self):
        self.start(reserved_units=15_000_000)
        self.finish()
        self.assertEqual(self.expire(), 1)
        self.assertEqual(self.attempt_state(), "receipt_expired_no_charge")
        self.assertEqual(self.confirm(), "awaiting_bill")
        self.assertEqual(self.task_state(), "awaiting_bill")

    def test_expired_receipt_cannot_revive_after_a_newer_attempt_failed(self):
        self.start()
        self.finish()
        self.expire()
        self.start("attempt-2")
        self.finish("attempt-2", complete=False)
        with self.assertRaises(billing.BillingStateError):
            self.confirm()
        self.assertEqual(self.attempt_state(), "receipt_expired_no_charge")
        self.assertEqual(self.task_state(), "retryable")

    def test_expired_receipt_cannot_revive_after_a_new_logical_task(self):
        self.start()
        self.finish()
        self.expire()
        self.start("attempt-2", "logical-2")
        with self.assertRaises(billing.BillingStateError):
            self.confirm()
        self.finish("attempt-2", complete=False)
        with self.assertRaises(billing.BillingStateError):
            self.confirm()
        self.assertEqual(self.attempt_state(), "receipt_expired_no_charge")

    def test_old_retryable_logical_id_cannot_bypass_replacement_task_guard(self):
        self.start()
        self.finish(complete=False)
        self.start("attempt-2", "logical-2")
        with self.assertRaises(billing.BillingStateError):
            self.start("attempt-3")
        self.finish("attempt-2")
        self.confirm("attempt-2", "logical-2")
        self.bill("attempt-2")
        billing.settle(self.db, "attempt-2", self.consume)
        with self.assertRaises(billing.BillingStateError):
            self.start("attempt-3")
        self.assertEqual(self.task_state(), "retryable")

    def test_explicit_redo_remains_supported_including_expiry_and_retry(self):
        self.pending()
        billing.settle(self.db, "attempt-1", self.consume)
        self.start("attempt-2", "logical-2", redo_of="logical-1")
        self.finish("attempt-2", complete=False)
        self.start("attempt-3", "logical-2")
        self.finish("attempt-3")
        self.expire("attempt-3")
        self.assertEqual(self.confirm("attempt-3", "logical-2"), "awaiting_bill")

    def test_retry_cannot_change_task_type_or_redo_identity(self):
        self.start()
        self.finish(complete=False)
        with self.assertRaises(billing.BillingStateError):
            billing.start_attempt(self.db, proxy.APP_NAME, "license-1", "logical-1",
                                  "source:batch-1", "module_benchmark", "attempt-2", MANAGED_MODEL)
        with self.assertRaises(billing.BillingStateError):
            self.start("attempt-2", redo_of="other-task")

    def test_recovery_interrupts_only_running_attempts_and_preserves_verified_bills(self):
        self.pending()
        self.start("attempt-2", "logical-2", "other-key")
        self.assertEqual(billing.recover_interrupted(self.db), 1)
        self.assertEqual(self.attempt_state(), "billing_pending")
        self.assertEqual(self.attempt_state("attempt-2"), "interrupted_no_charge")
        with self.assertRaises(billing.BillingStateError):
            self.finish("attempt-2")
        self.start("attempt-3", "logical-2", "other-key")
        self.assertEqual(self.task_state("logical-2"), "running")

    def test_timeout_after_central_debit_retries_same_identity_and_charges_once(self):
        self.pending()

        def lost_response(*args):
            self.consume(*args)
            raise TimeoutError("central response lost after commit")

        with self.assertRaises(TimeoutError):
            billing.settle(self.db, "attempt-1", lost_response)
        self.assertEqual(self.attempt_state(), "billing_pending")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM por_v2_ledger").fetchone()[0], 0)
        result = billing.settle(self.db, "attempt-1", self.consume)
        self.assertTrue(result["idempotent"])
        self.assertEqual(len(self.debits), 1)
        self.assertEqual(self.attempt_state(), "charged")

    def test_malformed_central_acknowledgement_stays_pending(self):
        self.pending()
        valid = {"ok": True, "remaining_units": 93_000_000, "transaction_id": "central:logical-1"}
        invalid = [None, {}, {**valid, "ok": 1}, {**valid, "remaining_units": -1},
                   {**valid, "remaining_units": True}, {**valid, "transaction_id": ""},
                   {**valid, "transaction_id": None}, {**valid, "amount_units": 8_000_000},
                   {**valid, "logical_task_id": "wrong"}, {**valid, "attempt_id": "wrong"}]
        for result in invalid:
            with self.subTest(result=result):
                with self.assertRaises(billing.BillingStateError) as caught:
                    billing.settle(self.db, "attempt-1", lambda *args: result)
                self.assertEqual(caught.exception.status, 503)
                self.assertEqual(self.attempt_state(), "billing_pending")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM por_v2_ledger").fetchone()[0], 0)

    def test_concurrent_settlement_reuses_one_central_transaction_and_local_ledger(self):
        self.pending()
        reached = threading.Barrier(3)
        release = [threading.Event(), threading.Event()]

        def worker(index):
            db = self.connection()
            try:
                def central(*args):
                    reached.wait(timeout=5)
                    if not release[index].wait(timeout=5):
                        raise TimeoutError("test synchronization timed out")
                    return self.consume(*args)
                return billing.settle(db, "attempt-1", central)
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(worker, 0), pool.submit(worker, 1)
            reached.wait(timeout=5)
            release[0].set()
            first_result = first.result(timeout=5)
            release[1].set()
            second_result = second.result(timeout=5)
        self.assertEqual(first_result["amount_units"], second_result["amount_units"])
        self.assertEqual(first_result["remaining_units"], second_result["remaining_units"])
        self.assertTrue(second_result["idempotent"])
        self.assertEqual(len(self.debits), 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM por_v2_ledger").fetchone()[0], 1)


class ProxyAdmissionAdversarialTests(BillingFixtures):
    """The proxy scenarios call its actual admission and confirmation functions."""

    def setUp(self):
        super().setUp()
        proxy.ensure_schema(self.db)
        self.balance = 16_000_000
        self.session = proxy.Session("hash", "license-1", "offline-machine", "offline-license",
                                     "offline-credential", "offline-session", 9_999_999_999)
        # Shared-cache in-memory SQLite reports SQLITE_LOCKED instead of waiting
        # like the production WAL database. Serialize local database scopes, then
        # force the request race between scopes where tariff lookup happens.
        database_lock = threading.RLock()

        @contextmanager
        def database():
            with database_lock:
                db = self.connection()
                try:
                    yield db
                finally:
                    db.close()

        settings = [patch.object(proxy, "database", database),
                    patch.object(proxy, "PRECISE_INTERNAL_TOKEN", "offline-internal"),
                    patch.object(proxy, "PRECISE_BILLING_SOURCE", "versioned_tariff"),
                    patch.object(proxy, "PRECISE_TARIFF_VERSION", "TEST-VERSION"),
                    patch.object(proxy, "DAILY_COST_LIMIT_CNY", float("inf")),
                    patch.object(proxy, "MAX_ACTIVE_PER_LICENSE", 8),
                    patch.object(proxy, "points_for_usage", return_value=(15_000, 0.075)),
                    patch.object(proxy, "v2_tariff_cost_cny", return_value="0.036"),
                    patch.object(proxy, "precise_license_balance", side_effect=lambda session: {
                        "ok": True, "remaining_units": self.balance, "unlimited": False}),
                    patch.object(proxy, "precise_license_consume", side_effect=lambda session, *args: self.consume(*args)),
                    patch.object(proxy, "sync_authoritative_wallet")]
        for setting in settings:
            setting.start()
            self.addCleanup(setting.stop)

    def admit(self, request="attempt-1", logical="logical-1", key="source:batch-1"):
        proxy.v2_start_attempt(self.session, logical, request, key, "source_clean", MANAGED_MODEL, 10)

    def assert_insufficient(self):
        with self.assertRaises(proxy.ApiError) as caught:
            self.admit("attempt-2", "logical-2", "other-key")
        self.assertEqual(caught.exception.status, 402)

    def test_unsettled_result_keeps_reservation_until_charge_or_rejection(self):
        self.admit()
        self.assert_insufficient()
        self.finish()
        self.assert_insufficient()
        self.confirm()
        self.assert_insufficient()
        self.bill()
        self.assert_insufficient()
        billing.settle(self.db, "attempt-1", self.consume)
        self.assertEqual(self.balance, 9_000_000)
        self.assert_insufficient()
        self.balance += 6_000_000
        self.admit("attempt-2", "logical-2", "other-key")

    def test_rejected_result_releases_reservation(self):
        self.admit()
        self.finish()
        self.assert_insufficient()
        self.assertEqual(proxy.v2_reject_result(self.session, "attempt-1", "logical-1")["state"], "failed_no_charge")
        self.admit("attempt-2", "logical-2", "other-key")
        self.assertEqual(self.balance, 16_000_000)
        self.assertFalse(self.debits)

    def test_expired_unconfirmed_result_releases_reservation(self):
        self.admit()
        self.finish()
        self.assert_insufficient()
        self.db.execute("UPDATE por_v2_attempts SET finished_at='2000-01-01T00:00:00Z' WHERE request_id='attempt-1'")
        self.admit("attempt-2", "logical-2", "other-key")
        self.assertEqual(self.attempt_state(), "receipt_expired_no_charge")
        self.assertEqual(self.balance, 16_000_000)

    def test_pending_actual_charge_larger_than_reservation_remains_locked(self):
        self.balance = 30_000_000
        self.admit()
        self.finish()
        self.confirm()
        self.assertEqual(self.bill(cost_cny="0.1"), 20_000_000)
        self.assert_insufficient()
        self.assertEqual(self.balance, 30_000_000)

    def test_late_expired_receipt_cannot_take_another_tasks_reservation(self):
        self.admit()
        self.finish()
        self.expire()
        self.admit("attempt-2", "logical-2", "other-key")
        with patch.object(proxy, "v2_tariff_cost_cny", return_value="0.075"):
            with self.assertRaises(proxy.ApiError) as caught:
                proxy.v2_confirm_saved(self.session, "attempt-1", "logical-1",
                                       billing.output_digest("saved output"), "late-receipt", True)
            self.assertEqual(caught.exception.status, 402)
            self.assertEqual(self.attempt_state(), "receipt_expired_no_charge")
            self.assertEqual(self.balance, 16_000_000)
            self.assertFalse(self.debits)
            self.finish("attempt-2")
            proxy.v2_reject_result(self.session, "attempt-2", "logical-2")
            result = proxy.v2_confirm_saved(self.session, "attempt-1", "logical-1",
                                            billing.output_digest("saved output"), "late-receipt", True)
        self.assertEqual(result["state"], "charged")
        self.assertEqual(self.balance, 1_000_000)

    def test_two_concurrent_proxy_confirmations_both_succeed_with_one_debit(self):
        self.admit()
        self.finish()
        both_saved = threading.Barrier(2)

        def tariff(*args):
            both_saved.wait(timeout=5)
            return "0.036"

        def worker():
            return proxy.v2_confirm_saved(self.session, "attempt-1", "logical-1",
                                          billing.output_digest("saved output"), "same-receipt", True)

        with patch.object(proxy, "v2_tariff_cost_cny", side_effect=tariff), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual([result["state"] for result in results], ["charged", "charged"])
        self.assertEqual([result["charged_units"] for result in results], [7_000_000, 7_000_000])
        self.assertEqual(self.balance, 9_000_000)
        self.assertEqual(len(self.debits), 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM por_v2_ledger").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
