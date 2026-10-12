"""Offline contract checks for the Ark migration; no paid provider calls."""
import io
import json
import sys
import unittest
from unittest.mock import Mock, patch

import product_report_proxy as proxy
import rotate_provider_key as rotate
from provider_config import MANAGED_MODEL, ARK_BASE_URL


class ArkContractTests(unittest.TestCase):
    def test_all_tasks_accept_only_the_requested_doubao_model(self):
        for task in proxy.ALLOWED_TASK_TYPES:
            body = {"model": MANAGED_MODEL, "messages": [{"role": "user", "content": "OK"}]}
            model, _ = proxy.validate_messages(body)
            self.assertEqual(proxy.model_for_task(task, model), MANAGED_MODEL)
            for old in ("gpt-5.5", "gpt-5.6-sol", "claude-sonnet-4-6"):
                with self.assertRaises(proxy.ApiError):
                    proxy.validate_messages({**body, "model": old})

    def test_native_cny_price_and_cache_discount_do_not_depend_on_fx(self):
        expected = (12.0 + 30.0 + 1.2)  # 2M regular, 1M output, 1M cache hit.
        for fx in (7.2, 9.0):
            with patch.object(proxy, "USD_CNY_RATE", fx):
                charged, cost = proxy.points_for_usage(MANAGED_MODEL, 3_000_000, 1_000_000, 1_000_000)
            self.assertEqual(cost, expected)
            self.assertEqual(charged, 8_640_000)
        self.assertEqual(proxy.pricing()["model"], MANAGED_MODEL)
        self.assertEqual(proxy.points_for_usage(MANAGED_MODEL, 1000, 0), (1200, 0.006))

    def test_search_lifecycle_reuses_one_call_id_and_reads_ark_tool_usage(self):
        for state in ("in_progress", "searching", "completed"):
            calls, _ = proxy.search_event_details({
                "type": f"response.web_search_call.{state}", "item_id": "search-1"
            })
            self.assertEqual(calls[0]["callId"], "search-1")
        usage = proxy.provider_usage({"usage": {
            "input_tokens": 120, "output_tokens": 30, "total_tokens": 150,
            "tool_usage": {"web_search": 2},
        }})
        self.assertEqual(usage["web_search_calls"], 2)
        self.assertEqual(proxy.merge_provider_usage(usage, {**usage, "web_search_calls": 1})["web_search_calls"], 2)

    def test_real_proxy_handler_builds_ark_payloads_and_preserves_stream_contract(self):
        for task in ("source_clean", "module_product_info", "module_benchmark"):
            with self.subTest(task=task):
                handler = proxy.Handler.__new__(proxy.Handler)
                handler.headers = {
                    "x-request-id": "12345678-1234-4234-8234-123456789012",
                    "x-billing-request-id": "report-a:module:1", "x-report-session-id": "report-a",
                    "x-task-key": "module:1", "x-task-type": task, "x-task-attempt": "1",
                }
                handler.read_json = Mock(return_value={
                    "model": MANAGED_MODEL, "messages": [{"role": "user", "content": "OK"}],
                    "prompt_cache_key": "local-cache-only", "reasoning_effort": "low",
                    "tools": [{"type": "malicious-client-tool"}],
                })
                handler.send_response = Mock()
                handler.send_header = Mock()
                handler.end_headers = Mock()
                handler.wfile = io.BytesIO()
                captured = []
                def stream(candidates, data, request_id, endpoint):
                    captured.append((json.loads(data), endpoint))
                    if task == "module_benchmark":
                        event = {"type": "response.completed", "response": {
                            "model": MANAGED_MODEL,
                            "usage": {"input_tokens": 120, "output_tokens": 30, "tool_usage": {"web_search": 2}},
                            "output": [
                                {"type": "web_search_call", "id": "search-1", "action": {"query": "brand"}},
                                {"type": "message", "content": [{"type": "output_text", "text": "OK",
                                    "annotations": [{"type": "url_citation", "url": "https://example.com/brand", "title": "Brand"}]}]},
                            ],
                        }}
                    else:
                        event = {"model": MANAGED_MODEL,
                            "choices": [{"delta": {"content": "OK"}, "finish_reason": "stop"}],
                            "usage": {"prompt_tokens": 120, "completion_tokens": 30}}
                    yield "line", b"data: " + json.dumps(event).encode() + b"\n\n"
                with patch.object(proxy, "require_session", return_value=Mock()), \
                     patch.object(proxy, "provider_route_candidates", return_value=(Mock(),)), \
                     patch.object(proxy, "reserve_request"), patch.object(proxy, "mark_upstream_submitted"), \
                     patch.object(proxy, "provider_request_items", side_effect=stream), \
                     patch.object(proxy, "settle_request") as settle:
                    handler.proxy_chat()
                body, endpoint = captured[0]
                self.assertEqual(body["model"], MANAGED_MODEL)
                self.assertNotIn("prompt_cache_key", body)
                self.assertEqual(endpoint, "responses" if task == "module_benchmark" else "chat/completions")
                self.assertEqual(settle.call_args.args[2], "success")
                self.assertEqual(settle.call_args.args[4]["input_tokens"], 120)
                self.assertEqual(settle.call_args.args[-1], 2 if task == "module_benchmark" else 0)
                if task == "module_benchmark":
                    self.assertIn(b'"status":"verified"', handler.wfile.getvalue())
                else:
                    self.assertNotIn("tools", body)
                    self.assertIn("max_completion_tokens", body)
                    self.assertNotIn("max_tokens", body)
                self.assertIn(b"[DONE]", handler.wfile.getvalue())

    def test_rotation_migrates_old_routes_and_retains_profiles_for_rollback(self):
        document = {"version": 1, "generation": 3, "profiles": {
            "old": {"base_url": "https://old.example/v1", "keys": {"old": "old-private-value"}, "active_key_id": "old"}
        }, "models": {"gpt-5.5": "old", "claude-sonnet-4-6": "old"}}
        argv = ["rotate", "set", "--profile", "ark-doubao", "--key-id", "new",
                "--base-url", ARK_BASE_URL, "--models", MANAGED_MODEL, "--activate"]
        with patch.object(sys, "argv", argv), patch.object(rotate, "load_document", return_value=document), \
             patch.object(rotate, "read_secret", return_value="private-test-key-1234"), \
             patch.object(rotate, "probe_key") as probe, patch.object(rotate, "atomic_write") as write, \
             patch("builtins.print"):
            rotate.main()
        probe.assert_called_once_with(ARK_BASE_URL, MANAGED_MODEL, "private-test-key-1234")
        result = write.call_args.args[1]
        self.assertEqual(result["models"], {MANAGED_MODEL: "ark-doubao"})
        self.assertEqual(result["generation"], 4)
        self.assertIn("old", result["profiles"])
        self.assertNotIn("private-test-key-1234", json.dumps(rotate.redacted_status(result)))

    def test_key_probe_disables_thinking_and_requires_a_real_answer(self):
        response = Mock(status=200)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"choices":[{"message":{"content":"OK"}}]}'
        with patch.object(rotate, "urlopen", return_value=response) as request:
            rotate.probe_key(ARK_BASE_URL, MANAGED_MODEL, "private-test-key-1234")
        body = json.loads(request.call_args.args[0].data)
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertEqual(body["max_tokens"], 16)
        self.assertNotIn("max_completion_tokens", body)
        response.read.return_value = b'{"choices":[]}'
        with patch.object(rotate, "urlopen", return_value=response), self.assertRaises(SystemExit):
            rotate.probe_key(ARK_BASE_URL, MANAGED_MODEL, "private-test-key-1234")


if __name__ == "__main__":
    unittest.main()
