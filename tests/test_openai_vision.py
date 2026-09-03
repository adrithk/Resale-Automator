"""Offline tests for the hosted OpenAI vision boundary."""

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx2
import openai

from openai_vision import (
    DEFAULT_MODEL,
    FACT_NAMES,
    VisionResponseError,
    VisionConfigurationError,
    VisionProviderError,
    analyze_images,
    build_model_analysis_schema,
    build_vision_request,
    encode_image_data_url,
    parse_model_response,
)


IMAGE_BYTES = b"test-image-bytes"


def candidate_fact(**overrides):
    value = {
        "value": None,
        "confidence": 0,
        "provenance": [],
        "needs_review": True,
        "evidence": None,
        "conflicts": [],
    }
    value.update(overrides)
    return value


def valid_analysis():
    return {
        "schema_version": 1,
        "tag_readability": {
            "status": "readable",
            "confidence": 0.95,
            "issues": [],
            "retake_instructions": [],
        },
        "facts": {name: candidate_fact() for name in FACT_NAMES},
        "warnings": [],
    }


class ImageRequestTests(unittest.TestCase):
    def test_encodes_supported_mime_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for suffix, mime in (
                (".jpg", "image/jpeg"),
                (".jpeg", "image/jpeg"),
                (".png", "image/png"),
                (".webp", "image/webp"),
            ):
                photo = Path(directory) / f"photo{suffix}"
                photo.write_bytes(IMAGE_BYTES)
                expected_payload = base64.b64encode(IMAGE_BYTES).decode("ascii")
                self.assertEqual(
                    encode_image_data_url(photo),
                    f"data:{mime};base64,{expected_payload}",
                )

    def test_request_uses_exact_model_configuration_and_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("front.jpg", "back.png", "tag.webp")]
            for path in paths:
                path.write_bytes(IMAGE_BYTES)

            request = build_vision_request(paths[:2], paths[2])

        self.assertEqual(request["model"], DEFAULT_MODEL)
        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(request["reasoning"], {"effort": "low"})
        self.assertIs(request["store"], False)
        self.assertIs(request["text"]["format"]["strict"], True)
        self.assertIn("up to three", request["instructions"])
        self.assertIn("lower confidence", request["instructions"])
        self.assertIn("never force a Style", request["instructions"])
        self.assertIn("W32 L34", request["instructions"])
        self.assertIn("do not discard either measurement", request["instructions"])
        content = request["input"][0]["content"]
        labels = [part["text"] for part in content if part["type"] == "input_text"]
        self.assertIn("Image role: item_photo_1", labels)
        self.assertIn("Image role: item_photo_2", labels)
        self.assertIn("Image role: tag_photo", labels)
        images = [part for part in content if part["type"] == "input_image"]
        self.assertEqual(len(images), 3)
        self.assertTrue(all(part["detail"] == "high" for part in images))

    def test_schema_is_strict_and_limits_provenance_to_sent_roles(self) -> None:
        schema = build_model_analysis_schema(("item_photo_1", "tag_photo"))

        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        fact = schema["properties"]["facts"]["properties"]["brand"]
        self.assertFalse(fact["additionalProperties"])
        self.assertEqual(fact["properties"]["provenance"]["items"]["enum"], ["tag_photo"])
        condition = schema["properties"]["facts"]["properties"]["condition"]
        self.assertEqual(
            condition["properties"]["provenance"]["items"]["enum"], ["item_photo_1"]
        )

    def test_schema_enumerates_controlled_destination_values(self) -> None:
        schema = build_model_analysis_schema(("item_photo_1", "tag_photo"))
        facts = schema["properties"]["facts"]["properties"]

        self.assertIn(
            "Men >> Bottoms >> Jeans (menswear, bottoms, jeans)",
            facts["category"]["properties"]["value"]["enum"],
        )
        self.assertNotIn("bottoms", facts["category"]["properties"]["value"]["enum"])
        self.assertIn("Used - Good (used_good)", facts["condition"]["properties"]["value"]["enum"])
        self.assertIn("gray", facts["primary_color"]["properties"]["value"]["enum"])
        self.assertIn("Vintage (vintage)", facts["source_1"]["properties"]["value"]["enum"])
        self.assertIn("Modern (modern)", facts["age"]["properties"]["value"]["enum"])
        self.assertIn("Utility (techwear)", facts["style_1"]["properties"]["value"]["enum"])


class ResponseParsingTests(unittest.TestCase):
    def test_sanitized_live_regression_fixture_is_rejected_before_mapping(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "sanitized_live_response.json"
        analysis = json.loads(fixture.read_text(encoding="utf-8"))

        with self.assertRaisesRegex(VisionResponseError, "exact supported value"):
            parse_model_response(
                {"status": "completed", "output_text": json.dumps(analysis)},
                photo_roles=("item_photo_1", "item_photo_2", "tag_photo"),
            )

    def test_parses_strict_structured_response(self) -> None:
        analysis = valid_analysis()
        response = {
            "status": "completed",
            "output_text": json.dumps(analysis),
            "output": [],
        }

        self.assertEqual(
            parse_model_response(response, photo_roles=("item_photo_1", "tag_photo")),
            analysis,
        )

    def test_rejects_malformed_json(self) -> None:
        with self.assertRaisesRegex(VisionResponseError, "malformed"):
            parse_model_response({"status": "completed", "output_text": "{"})

    def test_rejects_unexpected_fields(self) -> None:
        analysis = valid_analysis()
        analysis["unexpected"] = "not allowed"

        with self.assertRaisesRegex(VisionResponseError, "unexpected"):
            parse_model_response(
                {"status": "completed", "output_text": json.dumps(analysis)},
            )

    def test_rejects_unsupplied_provenance_role(self) -> None:
        analysis = valid_analysis()
        analysis["facts"]["brand"] = candidate_fact(
            value="Example",
            confidence=0.7,
            provenance=["item_photo_99"],
            evidence="Visible text",
        )

        with self.assertRaisesRegex(VisionResponseError, "unsupplied role"):
            parse_model_response(
                {"status": "completed", "output_text": json.dumps(analysis)},
                photo_roles=("item_photo_1", "tag_photo"),
            )

    def test_rejects_disallowed_provenance_and_literal_null(self) -> None:
        analysis = valid_analysis()
        analysis["facts"]["condition"] = candidate_fact(
            value="Used - Good (used_good)",
            confidence=0.7,
            provenance=["tag_photo"],
            evidence="Visible wear",
        )
        with self.assertRaisesRegex(VisionResponseError, "unsupplied role"):
            parse_model_response(
                {"status": "completed", "output_text": json.dumps(analysis)},
                photo_roles=("item_photo_1", "tag_photo"),
            )

        analysis = valid_analysis()
        analysis["facts"]["age"]["value"] = "null"
        with self.assertRaisesRegex(VisionResponseError, "JSON null"):
            parse_model_response({"status": "completed", "output_text": json.dumps(analysis)})

    def test_rejects_non_vocabulary_controlled_values(self) -> None:
        invalid_values = {
            "category": "bottoms",
            "condition": "Good pre-owned condition with visible wear",
            "primary_color": "black-ish",
            "source_1": "thrifted",
            "age": "1990s",
            "style_1": "five-pocket",
        }
        for field_name, value in invalid_values.items():
            with self.subTest(field_name=field_name):
                analysis = valid_analysis()
                analysis["facts"][field_name]["value"] = value
                with self.assertRaisesRegex(VisionResponseError, "exact supported value"):
                    parse_model_response(
                        {"status": "completed", "output_text": json.dumps(analysis)}
                    )

    def test_accepts_exact_controlled_values_and_gray_alias(self) -> None:
        analysis = valid_analysis()
        exact_values = {
            "category": "Men >> Bottoms >> Jeans (menswear, bottoms, jeans)",
            "condition": "Used - Good (used_good)",
            "primary_color": "gray",
            "source_1": "Vintage (vintage)",
            "age": "Modern (modern)",
            "style_1": "Utility (techwear)",
        }
        for field_name, value in exact_values.items():
            analysis["facts"][field_name] = candidate_fact(
                value=value,
                confidence=0.8,
                provenance=["item_photo_1"],
                evidence="Visible evidence.",
            )

        parsed = parse_model_response(
            {"status": "completed", "output_text": json.dumps(analysis)},
            photo_roles=("item_photo_1", "tag_photo"),
        )
        self.assertEqual(parsed["facts"]["primary_color"]["value"], "gray")

    def test_rejects_refusal(self) -> None:
        response = {
            "status": "completed",
            "output_text": "ignored",
            "output": [{"content": [{"type": "refusal", "refusal": "no"}]}],
        }

        with self.assertRaisesRegex(VisionResponseError, "declined"):
            parse_model_response(response)


class FakeResponses:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **request):
        self.calls.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes):
        self.responses = FakeResponses(outcomes)


def completed_response():
    return {
        "id": "resp_test",
        "model": "gpt-5.6-luna",
        "status": "completed",
        "output_text": json.dumps(valid_analysis()),
        "output": [],
        "usage": {"input_tokens": 11, "output_tokens": 22, "total_tokens": 33},
    }


class HostedCallTests(unittest.TestCase):
    def _photos(self, directory):
        paths = [Path(directory) / name for name in ("front.jpg", "back.png", "tag.webp")]
        for path in paths:
            path.write_bytes(IMAGE_BYTES)
        return paths

    def test_missing_configuration_fails_before_client_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self._photos(directory)
            with mock.patch("openai_vision._create_sdk_client") as create_client:
                with self.assertRaisesRegex(VisionConfigurationError, "OPENAI_API_KEY"):
                    analyze_images(paths[:2], paths[2], environ={})

        create_client.assert_not_called()

    def test_success_captures_identifiers_usage_latency_and_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self._photos(directory)
            client = FakeClient([completed_response()])
            times = iter((10.0, 10.125))
            result = analyze_images(
                paths[:2],
                paths[2],
                client=client,
                environ={"OPENAI_API_KEY": "test-only-key"},
                clock=lambda: next(times),
            )

        self.assertEqual(result.metadata["response_id"], "resp_test")
        self.assertEqual(result.metadata["model"], "gpt-5.6-luna")
        self.assertEqual(result.metadata["usage"]["total_tokens"], 33)
        self.assertEqual(result.metadata["latency_ms"], 125.0)
        request = client.responses.calls[0]
        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(request["timeout"], 60.0)
        self.assertNotIn("api_key", request)

    def test_timeout_retries_are_bounded(self) -> None:
        request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
        timeouts = [openai.APITimeoutError(request=request) for _ in range(3)]
        client = FakeClient(timeouts)
        with tempfile.TemporaryDirectory() as directory:
            paths = self._photos(directory)
            with self.assertRaisesRegex(VisionProviderError, "timed out") as caught:
                analyze_images(
                    paths[:2],
                    paths[2],
                    client=client,
                    environ={"OPENAI_API_KEY": "test-only-key"},
                    sleep=lambda delay: None,
                )

        self.assertEqual(getattr(caught.exception, "code", None), "timeout")
        self.assertEqual(len(client.responses.calls), 3)

    def test_rate_limit_retries_and_redacts_provider_message(self) -> None:
        secret = "sk-secret-must-not-escape"
        request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
        errors = []
        for _ in range(3):
            response = httpx2.Response(429, request=request)
            errors.append(
                openai.RateLimitError(
                    f"Authorization: Bearer {secret}",
                    response=response,
                    body=None,
                )
            )
        client = FakeClient(errors)
        with tempfile.TemporaryDirectory() as directory:
            paths = self._photos(directory)
            with self.assertRaises(VisionProviderError) as caught:
                analyze_images(
                    paths[:2],
                    paths[2],
                    client=client,
                    environ={"OPENAI_API_KEY": secret},
                    sleep=lambda delay: None,
                )

        self.assertEqual(getattr(caught.exception, "code", None), "rate_limited")
        self.assertNotIn(secret, str(caught.exception))
        self.assertEqual(len(client.responses.calls), 3)

    def test_rejected_api_key_becomes_configuration_error_without_secret(self) -> None:
        secret = "sk-rejected-secret"
        request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
        response = httpx2.Response(401, request=request)
        client = FakeClient(
            [
                openai.AuthenticationError(
                    f"Rejected Authorization: Bearer {secret}",
                    response=response,
                    body=None,
                )
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            paths = self._photos(directory)
            with self.assertRaises(VisionConfigurationError) as caught:
                analyze_images(
                    paths[:2],
                    paths[2],
                    client=client,
                    environ={"OPENAI_API_KEY": secret},
                )

        self.assertEqual(caught.exception.code, "invalid_api_key")
        self.assertNotIn(secret, str(caught.exception))
        self.assertEqual(len(client.responses.calls), 1)

    def test_malformed_response_is_not_retried(self) -> None:
        client = FakeClient([{"status": "completed", "output_text": "{"}])
        with tempfile.TemporaryDirectory() as directory:
            paths = self._photos(directory)
            with self.assertRaises(VisionResponseError):
                analyze_images(
                    paths[:2],
                    paths[2],
                    client=client,
                    environ={"OPENAI_API_KEY": "test-only-key"},
                )

        self.assertEqual(len(client.responses.calls), 1)


if __name__ == "__main__":
    unittest.main()
