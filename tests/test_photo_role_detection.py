"""Offline tests for unordered folder photo-role detection and review."""

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path

from openai_vision import VisionResponseError
from photo_role_detection import (
    ROLE_REVIEW_THRESHOLD,
    build_photo_role_request,
    detect_photo_roles,
    parse_photo_role_response,
    photo_role_review_required,
    proposed_tag_confidence,
    resolve_proposed_roles,
)
from review import ReviewCancelled, review_photo_roles_interactively


TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def valid_role_analysis() -> dict:
    return {
        "schema_version": 1,
        "assignments": [
            {
                "photo_id": "photo_1",
                "visual_role": "back_view",
                "confidence": 0.88,
                "tag_likelihood": 0.03,
                "evidence": "Rear garment view.",
            },
            {
                "photo_id": "photo_2",
                "visual_role": "tag_photo",
                "confidence": 0.96,
                "tag_likelihood": 0.99,
                "evidence": "Close-up of a printed clothing label.",
            },
            {
                "photo_id": "photo_3",
                "visual_role": "front_view",
                "confidence": 0.91,
                "tag_likelihood": 0.02,
                "evidence": "Front garment view.",
            },
        ],
        "warnings": [],
    }


class FakeResponses:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **request):
        self.calls.append(request)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.responses = FakeResponses(response)


class PhotoRoleDetectionTests(unittest.TestCase):
    def _photos(self, directory: str) -> list[Path]:
        photos = [Path(directory) / name for name in ("random-z.png", "1042.png", "x.png")]
        for photo in photos:
            photo.write_bytes(TEST_PNG)
        return photos

    def test_request_uses_neutral_ids_and_strict_model_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            photos = self._photos(directory)
            request = build_photo_role_request(photos)

        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(request["reasoning"], {"effort": "low"})
        self.assertIs(request["store"], False)
        self.assertIs(request["text"]["format"]["strict"], True)
        content = request["input"][0]["content"]
        labels = [part["text"] for part in content if part["type"] == "input_text"]
        self.assertIn("Photo ID: photo_1", labels)
        self.assertFalse(any("random-z" in label for label in labels))
        self.assertEqual(
            request["text"]["format"]["schema"]["properties"]["assignments"]
            ["items"]["properties"]["photo_id"]["enum"],
            ["photo_1", "photo_2", "photo_3"],
        )

    def test_parser_requires_each_photo_exactly_once(self) -> None:
        analysis = valid_role_analysis()
        response = {
            "status": "completed",
            "output_text": json.dumps(analysis),
            "output": [],
        }
        parsed = parse_photo_role_response(
            response,
            ids=("photo_1", "photo_2", "photo_3"),
        )
        self.assertEqual(parsed, analysis)

        analysis["assignments"][2]["photo_id"] = "photo_2"
        with self.assertRaisesRegex(VisionResponseError, "duplicate"):
            parse_photo_role_response(
                {"status": "completed", "output_text": json.dumps(analysis)},
                ids=("photo_1", "photo_2", "photo_3"),
            )

    def test_resolver_uses_tag_evidence_and_orders_front_before_back(self) -> None:
        photos = ["/tmp/back.png", "/tmp/tag.png", "/tmp/front.png"]
        resolved = resolve_proposed_roles(photos, valid_role_analysis())

        self.assertEqual(resolved.tag_photo, str(Path("/tmp/tag.png").resolve()))
        self.assertEqual(
            resolved.item_photos,
            (
                str(Path("/tmp/front.png").resolve()),
                str(Path("/tmp/back.png").resolve()),
            ),
        )

    def test_resolver_falls_back_to_highest_tag_likelihood(self) -> None:
        analysis = valid_role_analysis()
        for assignment in analysis["assignments"]:
            assignment["visual_role"] = "uncertain"
        photos = ["/tmp/a.png", "/tmp/b.png", "/tmp/c.png"]

        resolved = resolve_proposed_roles(photos, analysis)

        self.assertEqual(resolved.tag_photo, str(Path("/tmp/b.png").resolve()))

    def test_review_is_required_only_below_sixty_percent(self) -> None:
        photos = ["/tmp/a.png", "/tmp/b.png", "/tmp/c.png"]
        analysis = valid_role_analysis()
        self.assertEqual(ROLE_REVIEW_THRESHOLD, 0.60)
        self.assertEqual(proposed_tag_confidence(photos, analysis), 0.96)
        self.assertFalse(photo_role_review_required(photos, analysis))

        analysis["assignments"][1]["confidence"] = 0.60
        self.assertFalse(photo_role_review_required(photos, analysis))
        analysis["assignments"][1]["confidence"] = 0.59
        self.assertTrue(photo_role_review_required(photos, analysis))

    def test_hosted_call_returns_metadata_without_filename_assumptions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            photos = self._photos(directory)
            response = {
                "id": "resp_roles",
                "model": "gpt-5.6-luna",
                "status": "completed",
                "output_text": json.dumps(valid_role_analysis()),
                "output": [],
                "usage": {"input_tokens": 4, "output_tokens": 5, "total_tokens": 9},
            }
            client = FakeClient(response)
            times = iter((1.0, 1.05))
            result = detect_photo_roles(
                photos,
                client=client,
                environ={"OPENAI_API_KEY": "test-key"},
                clock=lambda: next(times),
            )

        self.assertEqual(result.analysis, valid_role_analysis())
        self.assertEqual(result.metadata["response_id"], "resp_roles")
        self.assertEqual(result.metadata["latency_ms"], 50.0)
        self.assertEqual(len(client.responses.calls), 1)

    def test_role_review_accepts_or_corrects_the_tag_by_number(self) -> None:
        photos = ["/tmp/back.png", "/tmp/tag.png", "/tmp/front.png"]
        accepted = review_photo_roles_interactively(
            photos,
            valid_role_analysis(),
            input_fn=lambda prompt: "",
            output=io.StringIO(),
        )
        self.assertEqual(accepted.tag_photo, str(Path("/tmp/tag.png").resolve()))

        responses = iter(("n", "3"))
        corrected = review_photo_roles_interactively(
            photos,
            valid_role_analysis(),
            input_fn=lambda prompt: next(responses),
            output=io.StringIO(),
        )
        self.assertEqual(corrected.tag_photo, str(Path("/tmp/front.png").resolve()))
        self.assertEqual(len(corrected.item_photos), 2)

    def test_role_review_can_be_cancelled_before_classification(self) -> None:
        with self.assertRaises(ReviewCancelled):
            review_photo_roles_interactively(
                ["/tmp/a.png", "/tmp/b.png", "/tmp/c.png"],
                valid_role_analysis(),
                input_fn=lambda prompt: "q",
                output=io.StringIO(),
            )


if __name__ == "__main__":
    unittest.main()
