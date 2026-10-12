"""Adversarial V2 protocol checks using loopback HTTP and an in-memory ledger.

The scripted upstream never opens a network connection. The reused HTTP fixture
provides only a local license endpoint and a real proxy request/response boundary.
No credentials, model calls, or temporary files are needed.

Protocol references:
https://docs.volcengine.com/docs/ark/response-lifecycle?lang=zh
https://docs.volcengine.com/docs/ark/streaming-output?lang=zh
"""

import hashlib
import json
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from unittest.mock import patch

import product_report_proxy as proxy
from provider_config import MANAGED_MODEL
from provider_keyring import ProviderKeyring
import test_ark_v2 as fixtures


MISSING = object()


def chat_usage(**overrides):
    return {"prompt_tokens": 1000, "completion_tokens": 1000, **overrides}


def responses_usage(**overrides):
    return {"input_tokens": 1000, "output_tokens": 1000,
            "tool_usage": {"web_search": 1}, **overrides}


def chat_event(content=None, finish=None, usage=MISSING):
    choice = {"delta": {} if content is None else {"content": content}}
    if finish is not None:
        choice["finish_reason"] = finish
    event = {"model": MANAGED_MODEL, "choices": [choice]}
    if usage is not MISSING:
        event["usage"] = usage
    return event


def response_event(event_type="response.completed", usage=MISSING,
                   search_status="completed", response_status="completed", output="OK"):
    call = {"type": "web_search_call", "id": "ws-offline",
            "action": {"type": "search", "query": "offline brand"}}
    if search_status is not MISSING:
        call["status"] = search_status
    response = {"model": MANAGED_MODEL, "status": response_status, "output": [call, {
        "type": "message", "content": [{"type": "output_text", "text": output,
            "annotations": [{"type": "url_citation", "url": "https://example.com/brand",
                             "title": "Offline source", "start_index": 0, "end_index": 2}]}]}]}
    if usage is not MISSING:
        response["usage"] = usage
    return {"type": event_type, "response": response}


def sse_events(stream):
    return [json.loads(line[5:].strip()) for line in stream.splitlines()
            if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]")]


def output_text(stream):
    return "".join(choice.get("delta", {}).get("content", "")
                   for event in sse_events(stream) for choice in event.get("choices", []))


class ProviderUsageValidationTests(unittest.TestCase):
    def test_both_token_counters_are_required_and_zero_must_be_explicit(self):
        for usage in ({"prompt_tokens": 10}, {"completion_tokens": 10},
                      {"input_tokens": 10}, {"output_tokens": 10}, {}):
            with self.subTest(usage=usage):
                self.assertIsNone(proxy.provider_usage({"usage": usage, "model": MANAGED_MODEL}))
        actual = proxy.provider_usage({"usage": {"input_tokens": 10, "output_tokens": 0}})
        self.assertIsNotNone(actual)
        self.assertEqual(actual["output_tokens"], 0)

    def test_invalid_counters_totals_and_cache_are_rejected(self):
        for usage in (chat_usage(completion_tokens="1000"), chat_usage(completion_tokens=True),
                      chat_usage(completion_tokens=1000.0), chat_usage(completion_tokens=-1),
                      chat_usage(total_tokens=1999),
                      chat_usage(prompt_tokens_details={"cached_tokens": 1001})):
            with self.subTest(usage=usage):
                self.assertIsNone(proxy.provider_usage({"usage": usage}))

    def test_reasoning_is_not_added_to_output_a_second_time(self):
        actual = proxy.provider_usage({"model": MANAGED_MODEL, "usage": {
            "input_tokens": 1000, "output_tokens": 1000, "total_tokens": 2000,
            "input_tokens_details": {"cached_tokens": 100},
            "output_tokens_details": {"reasoning_tokens": 900}}})
        self.assertEqual(actual["input_tokens"], 1000)
        self.assertEqual(actual["output_tokens"], 1000)
        self.assertEqual(actual["cached_input_tokens"], 100)


class ProtocolAdversarialTests(unittest.TestCase):
    # Reuse the tested local license/session/database fixture without inheriting
    # its tests or its implicit, status-less search success response.
    post = fixtures.ArkV2Tests.post
    tearDown = fixtures.ArkV2Tests.tearDown

    def setUp(self):
        fixtures.ArkV2Tests.setUp(self)
        self.events = []
        self.upstream_calls = []

        # Match the production connection's autocommit behavior. The original
        # shared-memory fixture otherwise rolls back standalone updates (such
        # as the legacy submitted marker) when database() closes a connection.
        fixture_connection = proxy.connection

        def connection():
            db = fixture_connection()
            db.isolation_level = None
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=20000")
            return db

        autocommit = patch.object(proxy, "connection", connection)
        autocommit.start()
        self.patches.append(autocommit)

        def script(_candidates, upstream_data, _request_id, endpoint_path="chat/completions",
                   **_kwargs):
            self.upstream_calls.append((endpoint_path, json.loads(upstream_data)))
            for event in self.events:
                if isinstance(event, Exception):
                    raise event
                if isinstance(event, bytes):
                    yield "line", event
                else:
                    encoded = event if isinstance(event, str) else json.dumps(event)
                    yield "line", b"data: " + encoded.encode("utf-8") + b"\n\n"

        scripted = patch.object(proxy, "provider_request_items", script)
        scripted.start()
        self.patches.append(scripted)

    def chat(self, task="source_clean", report_id=None, precise=True):
        request_id = str(uuid.uuid4())
        logical_id = "offline:" + request_id
        headers = {"Authorization": "Bearer " + self.token, "x-request-id": request_id,
            "x-billing-request-id": logical_id, "x-report-session-id": report_id or request_id,
            "x-task-key": task + ":" + request_id, "x-task-type": task, "x-task-attempt": "1"}
        if precise:
            headers["x-result-confirmation-capable"] = "1"
        stream = self.post("/chat/completions", {"model": MANAGED_MODEL,
            "messages": [{"role": "user", "content": "OK"}]}, headers)
        return stream, request_id, logical_id

    def confirm_output(self, request_id, logical_id, output="OK"):
        return json.loads(self.post("/billing/result/confirm", {"request_id": request_id,
            "logical_task_id": logical_id, "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "receipt_id": "offline-receipt-" + request_id, "locally_valid": True},
            {"Authorization": "Bearer " + self.token}))

    def assert_rejected_result(self, stream, request_id, logical_id):
        self.assertNotIn("[DONE]", stream)
        with proxy.database() as db:
            row = db.execute("SELECT state FROM por_v2_attempts WHERE request_id=?", (request_id,)).fetchone()
        self.assertEqual(row["state"], "failed_no_charge")
        with self.assertRaises(HTTPError) as caught:
            self.confirm_output(request_id, logical_id)
        caught.exception.close()
        self.assertFalse(self.debits)

    def assert_successful_result(self, stream, request_id, logical_id, output="OK"):
        self.assertIn("[DONE]", stream)
        self.assertEqual(output_text(stream), output)
        self.assertFalse(self.debits)
        first = self.confirm_output(request_id, logical_id, output)
        second = self.confirm_output(request_id, logical_id, output)
        self.assertEqual(first["state"], "charged")
        self.assertEqual(first["charged_units"], 7_000_000)
        self.assertEqual(second["charged_units"], first["charged_units"])
        self.assertEqual(len(self.debits), 1)

    def test_responses_deltas_preserve_whitespace_and_match_saved_result_proof(self):
        chunks = ["  # Heading", "\n\n", "Hello", " ", "world", "\n", "| A | B |\n", "  "]
        expected = "".join(chunks)
        self.events = [{"type": "response.output_text.delta", "delta": value} for value in chunks]
        self.events.append(response_event(usage=responses_usage(), output=expected))
        self.assert_successful_result(*self.chat("module_benchmark"), output=expected)

    def test_official_completed_search_emits_verified_evidence_and_server_options(self):
        self.events = [
            {"type": "response.web_search_call.in_progress", "item_id": "ws-offline"},
            {"type": "response.web_search_call.completed", "item_id": "ws-offline"},
            {"type": "response.output_text.delta", "delta": "OK"},
            response_event(usage=responses_usage())]
        result = self.chat("module_benchmark")
        statuses = [event for event in sse_events(result[0]) if event.get("type") == "por.search_status"]
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0]["status"], "verified")
        self.assertEqual(statuses[0]["search_calls"], 1)
        self.assertEqual(statuses[0]["evidence_count"], 1)
        self.assertNotIn("offline-provider-secret", result[0])
        endpoint, body = self.upstream_calls[-1]
        self.assertEqual(endpoint, "responses")
        self.assertEqual(body["model"], MANAGED_MODEL)
        self.assertEqual(body["reasoning"], {"effort": "low"})
        self.assertEqual(body["max_tool_calls"], 1)
        self.assert_successful_result(*result)

    def test_responses_completed_message_without_deltas_is_not_lost(self):
        self.events = [response_event(usage=responses_usage())]
        self.assert_successful_result(*self.chat("module_benchmark"))

    def test_responses_final_body_mismatch_rejects_incomplete_streamed_content(self):
        self.events = [{"type": "response.output_text.delta", "delta": "OK"},
            response_event(usage=responses_usage(), output="OK plus a missing section")]
        self.assert_rejected_result(*self.chat("module_benchmark"))

    def test_chat_stop_with_later_usage_frame_is_a_valid_completion(self):
        self.events = [chat_event("OK"), chat_event(finish="stop"),
            {"model": MANAGED_MODEL, "choices": [], "usage": chat_usage()}, "[DONE]"]
        result = self.chat()
        endpoint, body = self.upstream_calls[-1]
        self.assertEqual(endpoint, "chat/completions")
        self.assertIn("max_completion_tokens", body)
        self.assertNotIn("max_tokens", body)
        self.assert_successful_result(*result)

    def test_chat_stop_with_same_frame_usage_needs_no_done_sentinel(self):
        self.events = [chat_event("OK"), chat_event(finish="stop", usage=chat_usage())]
        self.assert_successful_result(*self.chat())

    def test_missing_terminal_usage_cannot_reuse_a_chat_running_snapshot(self):
        self.events = [chat_event("OK", usage=chat_usage()), chat_event(finish="stop"), "[DONE]"]
        self.assert_rejected_result(*self.chat())

    def test_invalid_terminal_chat_usage_cannot_reuse_an_earlier_snapshot(self):
        self.events = [chat_event("OK", usage=chat_usage()),
            chat_event(finish="stop", usage=chat_usage(completion_tokens="corrupt")), "[DONE]"]
        self.assert_rejected_result(*self.chat())

    def test_invalid_final_usage_after_a_valid_stop_cannot_reuse_that_stop(self):
        self.events = [chat_event("OK"), chat_event(finish="stop", usage=chat_usage()),
            {"model": MANAGED_MODEL, "choices": [], "usage": {"prompt_tokens": 1000}}, "[DONE]"]
        self.assert_rejected_result(*self.chat())

    def test_explicit_null_final_usage_cannot_reuse_a_valid_stop_snapshot(self):
        self.events = [chat_event("OK"), chat_event(finish="stop", usage=chat_usage()),
            {"model": MANAGED_MODEL, "choices": [], "usage": None}, "[DONE]"]
        self.assert_rejected_result(*self.chat())

    def test_normal_chat_null_usage_frames_before_final_usage_are_allowed(self):
        self.events = [chat_event("OK", usage=None), chat_event(finish="stop", usage=None),
            {"model": MANAGED_MODEL, "choices": [], "usage": chat_usage()}, "[DONE]"]
        self.assert_successful_result(*self.chat())

    def test_empty_choices_usage_before_stop_is_not_final_billing_evidence(self):
        self.events = [{"model": MANAGED_MODEL, "choices": [], "usage": chat_usage()},
            chat_event("OK"), chat_event(finish="stop"), "[DONE]"]
        self.assert_rejected_result(*self.chat())

    def test_content_after_final_usage_invalidates_its_billing_evidence(self):
        self.events = [chat_event("OK"), chat_event(finish="stop", usage=chat_usage()),
            chat_event(" extra output"), "[DONE]"]
        self.assert_rejected_result(*self.chat())

    def test_later_valid_final_usage_can_replace_an_invalid_usage_snapshot(self):
        self.events = [chat_event("OK"), chat_event(finish="stop", usage={"prompt_tokens": 1000}),
            {"model": MANAGED_MODEL, "choices": [], "usage": chat_usage()}, "[DONE]"]
        self.assert_successful_result(*self.chat())

    def test_final_chat_usage_replaces_an_earlier_larger_snapshot_for_cost(self):
        self.events = [chat_event("OK", usage=chat_usage(prompt_tokens=10000, completion_tokens=10000)),
            chat_event(finish="stop", usage=chat_usage()), "[DONE]"]
        self.assert_successful_result(*self.chat())

    def test_final_responses_usage_replaces_an_earlier_larger_snapshot_for_cost(self):
        self.events = [response_event("response.in_progress", response_status="in_progress",
                                      usage=responses_usage(input_tokens=10000, output_tokens=10000)),
            {"type": "response.output_text.delta", "delta": "OK"}, response_event(usage=responses_usage())]
        self.assert_successful_result(*self.chat("module_benchmark"))

    def test_responses_completed_usage_must_not_reuse_in_progress_snapshot(self):
        self.events = [response_event("response.in_progress", usage=responses_usage(),
                                      response_status="in_progress"),
            {"type": "response.output_text.delta", "delta": "OK"}, response_event()]
        self.assert_rejected_result(*self.chat("module_benchmark"))

    def test_corrupt_responses_terminal_usage_invalidates_earlier_valid_usage(self):
        self.events = [response_event("response.in_progress", usage=responses_usage(),
                                      response_status="in_progress"),
            {"type": "response.output_text.delta", "delta": "OK"},
            response_event(usage=responses_usage(output_tokens=True))]
        self.assert_rejected_result(*self.chat("module_benchmark"))

    def test_responses_completed_event_cannot_hide_an_incomplete_response_status(self):
        self.events = [{"type": "response.output_text.delta", "delta": "OK"},
            response_event(usage=responses_usage(), response_status="incomplete")]
        self.assert_rejected_result(*self.chat("module_benchmark"))

    def test_responses_failure_cannot_be_overwritten_by_later_completed_event(self):
        self.events = [{"type": "response.output_text.delta", "delta": "OK"},
            {"type": "response.failed", "error": {"message": "offline failure"}},
            response_event(usage=responses_usage())]
        self.assert_rejected_result(*self.chat("module_benchmark"))

    def test_chat_error_cannot_be_overwritten_by_later_stop(self):
        self.events = [chat_event("OK"), {"error": {"message": "offline failure"}},
            chat_event(finish="stop", usage=chat_usage()), "[DONE]"]
        self.assert_rejected_result(*self.chat())

    def test_malformed_json_cannot_be_ignored_to_complete_and_bill(self):
        self.events = [chat_event("OK"), b"data: {invalid JSON}\n\n",
            chat_event(finish="stop", usage=chat_usage()), "[DONE]"]
        self.assert_rejected_result(*self.chat())

    def test_truncated_chat_finish_reason_never_creates_a_completion_proof(self):
        self.events = [chat_event("OK"), chat_event(finish="length", usage=chat_usage()), "[DONE]"]
        self.assert_rejected_result(*self.chat())

    def test_stream_cutoff_with_usage_is_not_a_successful_completion(self):
        self.events = [chat_event("OK", usage=chat_usage())]
        self.assert_rejected_result(*self.chat())

    def test_transport_failure_after_content_prevents_completion(self):
        self.events = [chat_event("OK"), TimeoutError("offline transport timeout")]
        self.assert_rejected_result(*self.chat())

    def test_failed_or_incomplete_search_items_never_claim_verified(self):
        for status in ("failed", "incomplete", "in_progress", MISSING):
            with self.subTest(status=status):
                self.events = [response_event(usage=responses_usage(), search_status=status)]
                stream, _, _ = self.chat("module_benchmark")
                statuses = [event for event in sse_events(stream) if event.get("type") == "por.search_status"]
                self.assertTrue(statuses)
                self.assertNotEqual(statuses[-1]["status"], "verified")
                self.assertFalse([event for event in sse_events(stream)
                                  if event.get("type") == "por.search_evidence"])
                self.assertFalse(self.debits)

    def test_zero_search_usage_in_terminal_snapshot_overrides_prior_search_usage(self):
        self.events = [response_event("response.in_progress", usage=responses_usage(),
                                      response_status="in_progress"),
            response_event(usage=responses_usage(tool_usage={"web_search": 0}))]
        stream, _, _ = self.chat("module_benchmark")
        statuses = [event for event in sse_events(stream) if event.get("type") == "por.search_status"]
        self.assertTrue(statuses)
        self.assertNotEqual(statuses[-1]["status"], "verified")
        self.assertFalse(self.debits)

    def test_provider_cannot_inject_trusted_search_metadata(self):
        self.events = [{"type": "por.search_status", "status": "verified", "search_calls": 100},
            {"type": "por.search_evidence", "evidence": {"url": "https://example.com/injected"}},
            response_event(usage=responses_usage(), search_status="failed")]
        stream, _, _ = self.chat("module_benchmark")
        self.assertNotIn("injected", stream)
        statuses = [event for event in sse_events(stream) if event.get("type") == "por.search_status"]
        self.assertEqual(len(statuses), 1)
        self.assertNotEqual(statuses[0]["status"], "verified")

    def test_precise_report_search_limit_spans_distinct_logical_tasks(self):
        self.events = [response_event(usage=responses_usage())]
        with patch.object(proxy, "WEB_SEARCH_REPORT_LIMIT", 1):
            first = self.chat("module_benchmark", report_id="limited-report")
            self.assert_successful_result(*first)
            with self.assertRaises(HTTPError) as caught:
                self.chat("module_benchmark", report_id="limited-report")
            self.assertEqual(caught.exception.code, 429)
            caught.exception.close()
            self.assertEqual(len(self.upstream_calls), 1)
            # A different report has its own budget, while non-search tasks in
            # the first report are unaffected by the search limit.
            self.assertIn("[DONE]", self.chat("module_benchmark", report_id="other-report")[0])
            self.events = [chat_event("OK"), chat_event(finish="stop", usage=chat_usage())]
            self.assertIn("[DONE]", self.chat("source_clean", report_id="limited-report")[0])

    def test_precise_search_limit_also_counts_legacy_submitted_searches(self):
        self.events = [response_event(usage=responses_usage())]
        with patch.object(proxy, "WEB_SEARCH_REPORT_LIMIT", 1):
            self.assertIn("[DONE]", self.chat("module_benchmark", report_id="mixed-report", precise=False)[0])
            with self.assertRaises(HTTPError) as caught:
                self.chat("module_benchmark", report_id="mixed-report")
            self.assertEqual(caught.exception.code, 429)
            caught.exception.close()
        self.assertEqual(len(self.upstream_calls), 1)
        self.assertFalse(self.debits)

    def test_legacy_admission_reserves_search_budget_before_upstream_submission(self):
        self.events = [response_event(usage=responses_usage())]
        admitted = threading.Event()
        release = threading.Event()
        original_mark = proxy.mark_upstream_submitted

        def wait_before_submission(request_id):
            admitted.set()
            if not release.wait(timeout=5):
                raise AssertionError("the test did not release the local request")
            original_mark(request_id)

        with patch.object(proxy, "WEB_SEARCH_REPORT_LIMIT", 1), \
                patch.object(proxy, "mark_upstream_submitted", wait_before_submission):
            with ThreadPoolExecutor(max_workers=1) as pool:
                first = pool.submit(self.chat, "module_benchmark", "concurrent-mixed-report", False)
                try:
                    self.assertTrue(admitted.wait(timeout=5))
                    with self.assertRaises(HTTPError) as caught:
                        self.chat("module_benchmark", report_id="concurrent-mixed-report")
                    self.assertEqual(caught.exception.code, 429)
                    caught.exception.close()
                finally:
                    release.set()
                self.assertIn("[DONE]", first.result(timeout=10)[0])
        self.assertEqual(len(self.upstream_calls), 1)
        self.assertFalse(self.debits)

    def configure_actual_cost_above_reservation(self):
        # Actual provider input may exceed the byte-based admission estimate.
        # Keep precisely enough balance for two estimates, but not for the
        # larger actual charge plus another estimate, at the current task cap.
        output_limit = min(proxy.MAX_OUTPUT_TOKENS, proxy.TASK_OUTPUT_RESERVES['source_clean'])
        reserved_units = fixtures.ArkV2Tests.expected_reserve(self, 'OK', output_limit)
        actual_cost = proxy.v2_tariff_cost_cny(MANAGED_MODEL,
            {'input_tokens': 10000, 'output_tokens': output_limit})
        actual_units = proxy.billing_v2.amount_units(actual_cost,
            str(proxy.POINTS_PER_CNY), str(proxy.COST_RATE))
        initial_balance = reserved_units * 2
        self.assertGreater(actual_units, reserved_units)
        self.assertLess(actual_units, initial_balance)
        self.assertLess(initial_balance - actual_units, reserved_units)
        self.balance_units = initial_balance
        self.events = [chat_event("OK"),
            chat_event(finish="stop", usage=chat_usage(prompt_tokens=10000, completion_tokens=output_limit))]
        return reserved_units, actual_units, initial_balance

    def assert_actual_unsettled_cost_is_reserved(self, confirm_saved_first=False):
        reserved_units, actual_units, initial_balance = self.configure_actual_cost_above_reservation()
        first_stream, request_id, logical_id = self.chat()
        self.assertIn("[DONE]", first_stream)
        with proxy.database() as db:
            self.assertEqual(db.execute('SELECT reserved_units FROM por_v2_attempts WHERE request_id=?',
                                        (request_id,)).fetchone()[0], reserved_units)
        if confirm_saved_first:
            with patch.object(proxy, "PRECISE_BILLING_SOURCE", "pending"):
                self.assertEqual(self.confirm_output(request_id, logical_id)["state"], "awaiting_bill")
        self.assertFalse(self.debits)
        with self.assertRaises(HTTPError) as caught:
            self.chat()
        self.assertEqual(caught.exception.code, 402)
        caught.exception.close()
        self.assertEqual(len(self.upstream_calls), 1)
        confirmed = self.confirm_output(request_id, logical_id)
        self.assertEqual(confirmed["state"], "charged")
        self.assertEqual(confirmed["charged_units"], actual_units)
        self.assertEqual(self.balance_units, initial_balance - actual_units)
        with self.assertRaises(HTTPError) as caught:
            self.chat()
        self.assertEqual(caught.exception.code, 402)
        caught.exception.close()
        self.assertEqual(len(self.upstream_calls), 1)
        self.assertEqual(len(self.debits), 1)

    def test_awaiting_receipt_reserves_actual_cost_when_estimate_was_too_low(self):
        self.assert_actual_unsettled_cost_is_reserved()

    def test_awaiting_bill_reserves_actual_cost_when_estimate_was_too_low(self):
        self.assert_actual_unsettled_cost_is_reserved(confirm_saved_first=True)

    def test_unverifiable_pending_cost_blocks_new_admission_and_preserves_result(self):
        self.events = [chat_event("OK"), chat_event(finish="stop", usage=chat_usage())]
        first_stream, request_id, logical_id = self.chat()
        self.assertIn("[DONE]", first_stream)
        with patch.object(proxy, "PRECISE_TARIFF_SHA256", "0" * 64):
            with self.assertRaises(HTTPError) as caught:
                self.chat()
            self.assertEqual(caught.exception.code, 503)
            caught.exception.close()
        with proxy.database() as db:
            state = db.execute("SELECT state FROM por_v2_attempts WHERE request_id=?", (request_id,)).fetchone()[0]
        self.assertEqual(state, "awaiting_receipt")
        self.assertFalse(self.debits)
        self.assertEqual(len(self.upstream_calls), 1)
        self.assertEqual(self.confirm_output(request_id, logical_id)["state"], "charged")
        self.assertIn("[DONE]", self.chat()[0])

    def test_expired_result_reclaims_actual_cost_without_taking_another_reservation(self):
        _, actual_units, initial_balance = self.configure_actual_cost_above_reservation()
        _, request_id, logical_id = self.chat()
        with proxy.database() as db:
            db.execute("UPDATE por_v2_attempts SET finished_at='2000-01-01T00:00:00Z' WHERE request_id=?",
                       (request_id,))
        self.events = [chat_event("OK"), chat_event(finish="stop", usage=chat_usage())]
        _, second_request, second_logical = self.chat()
        with self.assertRaises(HTTPError) as caught:
            self.confirm_output(request_id, logical_id)
        self.assertEqual(caught.exception.code, 402)
        caught.exception.close()
        with proxy.database() as db:
            state = db.execute("SELECT state FROM por_v2_attempts WHERE request_id=?", (request_id,)).fetchone()[0]
        self.assertEqual(state, "receipt_expired_no_charge")
        self.assertEqual(self.balance_units, initial_balance)
        self.assertFalse(self.debits)
        rejected = json.loads(self.post("/billing/result/reject", {
            "request_id": second_request, "logical_task_id": second_logical},
            {"Authorization": "Bearer " + self.token}))
        self.assertEqual(rejected["state"], "failed_no_charge")
        self.assertEqual(self.confirm_output(request_id, logical_id)["charged_units"], actual_units)
        self.assertEqual(self.balance_units, initial_balance - actual_units)

    def test_missing_provider_key_rejects_before_upstream_or_billing_admission(self):
        self.events = [chat_event("OK"), chat_event(finish="stop", usage=chat_usage())]
        with patch.object(proxy, "PROVIDER_KEYRING", ProviderKeyring("", {}, (MANAGED_MODEL,))):
            with self.assertRaises(HTTPError) as caught:
                self.chat()
            self.assertEqual(caught.exception.code, 503)
            body = caught.exception.read().decode()
            caught.exception.close()
        self.assertNotIn("offline-provider-secret", body)
        self.assertFalse(self.upstream_calls)
        self.assertFalse(self.debits)
        with proxy.database() as db:
            proxy.billing_v2.ensure_schema(db)
            count = db.execute("SELECT COUNT(*) FROM por_v2_attempts").fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
