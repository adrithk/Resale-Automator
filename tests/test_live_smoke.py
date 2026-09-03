"""Explicitly opt-in, billed smoke tests using user-supplied photos."""

import os
from pathlib import Path
import unittest

from classifier import validate_inputs
from fact_validation import validate_candidate_analysis
from openai_vision import analyze_images


LIVE_ENABLED = os.environ.get("RESALE_RUN_LIVE_SMOKE") == "1"


@unittest.skipUnless(
    LIVE_ENABLED,
    "set RESALE_RUN_LIVE_SMOKE=1 to authorize two billed hosted API calls",
)
class LiveVisionSmokeTests(unittest.TestCase):
    """Exercise one readable and one unreadable tag against the real provider."""

    @classmethod
    def setUpClass(cls) -> None:
        item_value = os.environ.get("RESALE_LIVE_ITEM_PHOTOS", "")
        cls.item_photos = [value for value in item_value.split(os.pathsep) if value]
        cls.readable_tag = os.environ.get("RESALE_LIVE_READABLE_TAG_PHOTO", "")
        cls.unreadable_tag = os.environ.get("RESALE_LIVE_UNREADABLE_TAG_PHOTO", "")
        if not cls.readable_tag or not cls.unreadable_tag:
            raise ValueError(
                "Set both RESALE_LIVE_READABLE_TAG_PHOTO and "
                "RESALE_LIVE_UNREADABLE_TAG_PHOTO before opting in."
            )
        for tag_photo in (cls.readable_tag, cls.unreadable_tag):
            errors = validate_inputs(cls.item_photos, tag_photo)
            if errors:
                raise ValueError(
                    "Live smoke inputs failed local validation: " + "; ".join(errors)
                )
        cls.item_photos = [str(Path(photo).resolve()) for photo in cls.item_photos]

    def assert_metadata(self, metadata) -> None:
        self.assertTrue(metadata["response_id"])
        self.assertTrue(metadata["model"])
        self.assertIsNotNone(metadata["latency_ms"])
        self.assertIn("total_tokens", metadata["usage"])

    def test_readable_tag_returns_schema_valid_candidates(self) -> None:
        result = analyze_images(self.item_photos, self.readable_tag)

        self.assertEqual(result.analysis["tag_readability"]["status"], "readable")
        self.assertIsNotNone(
            validate_candidate_analysis(result.analysis).validated_facts
        )
        self.assert_metadata(result.metadata)

    def test_unreadable_tag_triggers_gate(self) -> None:
        result = analyze_images(self.item_photos, self.unreadable_tag)
        validation = validate_candidate_analysis(result.analysis)

        self.assertIn(
            result.analysis["tag_readability"]["status"],
            {"unreadable", "uncertain"},
        )
        self.assertIsNone(validation.validated_facts)
        self.assertTrue(validation.tag_retake_instructions)
        self.assert_metadata(result.metadata)


if __name__ == "__main__":
    unittest.main()
