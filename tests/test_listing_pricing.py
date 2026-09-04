"""Offline price generation and monetary validation tests."""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from listing_pricing import build_pricing_request, normalize_price, parse_pricing_response, suggest_price
from openai_vision import VisionProviderError, VisionResponseError
from tests.test_depop_csv import approved_facts


class PricingTests(unittest.TestCase):
    def test_only_validated_facts_are_sent_with_existing_provider_settings(self):
        request = build_pricing_request(approved_facts())
        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(request["reasoning"], {"effort": "low"})
        self.assertFalse(request["store"])
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertNotIn("tools", request)
        payload = json.loads(request["input"][0]["content"][0]["text"])
        self.assertEqual(payload, approved_facts())
        with self.assertRaises(ValueError):
            build_pricing_request(approved_facts(size="bad"))

    def test_price_is_half_resale_value_rounded_to_cents(self):
        for value, expected in [(24, "12.00"), (25.01, "12.51"), (100, "50.00")]:
            result = parse_pricing_response({"status": "completed", "output_text": json.dumps({"estimated_resale_value_usd": value})})
            self.assertEqual(result["price"], expected)

    def test_invalid_money_is_rejected_without_echoing_input(self):
        for value in [None, True, "", "0", "-1", "12.345", "$12", "NaN", "Infinity", "1e2"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_price(value)
        self.assertEqual(normalize_price("15"), "15.00")
        self.assertEqual(normalize_price("12.5"), "12.50")

    def test_malformed_refused_and_non_numeric_model_outputs_fail(self):
        for output in ['{"estimated_resale_value_usd": true}', '{"estimated_resale_value_usd":"24"}', '{"estimated_resale_value_usd":-1}', '{"estimated_resale_value_usd":NaN}', '{}', 'not json']:
            with self.subTest(output=output), self.assertRaises(VisionResponseError):
                parse_pricing_response({"status": "completed", "output_text": output})
        with self.assertRaises(VisionResponseError):
            parse_pricing_response({"status": "incomplete"})
        with self.assertRaises(VisionResponseError):
            parse_pricing_response({"status": "completed", "output": [{"content": [{"type": "refusal"}]}]})

    def test_hosted_boundary_records_metadata_and_sets_timeout(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            status="completed", output=[], output_text='{"estimated_resale_value_usd":24}',
            id="resp_price", model="gpt-5.6-luna", usage=None,
        )
        result = suggest_price(approved_facts(), client=client, environ={"OPENAI_API_KEY": "test-only"})
        self.assertEqual(result.analysis["price"], "12.00")
        self.assertEqual(result.metadata["response_id"], "resp_price")
        self.assertEqual(client.responses.create.call_args.kwargs["timeout"], 60)
        with self.assertRaises(VisionProviderError):
            suggest_price(approved_facts(), client=client, environ={})
