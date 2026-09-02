"""Tests for the first classifier command-line chunk."""

import base64
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from classifier import (
    build_quality_warnings,
    load_image,
    main,
    measure_blur_score,
    measure_image_dimensions,
    measure_lighting,
    measure_possible_glare,
    validate_image_file,
    validate_inputs,
)

TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def write_test_image(path: Path) -> None:
    """Write a tiny real image without needing a fixture file in the repository."""
    path.write_bytes(TEST_PNG)


class InputValidationTests(unittest.TestCase):
    def test_requires_at_least_two_item_photos(self) -> None:
        errors = validate_inputs(["one.jpg"], "tag.jpg")

        self.assertIn("Provide at least two item photos using --item.", errors)

    def test_reports_missing_files(self) -> None:
        errors = validate_inputs(["front.jpg", "back.jpg"], "tag.jpg")

        self.assertEqual(len(errors), 3)

    def test_rejects_unsupported_image_format(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            photo = Path(temporary_directory) / "item.gif"
            photo.write_bytes(TEST_PNG)

            errors = validate_image_file(str(photo), "Item photo")

            self.assertIn("unsupported format", errors[0])

    def test_rejects_file_that_cannot_be_decoded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            photo = Path(temporary_directory) / "item.jpg"
            photo.write_text("This is not an image.")

            errors = validate_image_file(str(photo), "Item photo")

            self.assertIn("could not be decoded", errors[0])

    def test_measures_image_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            photo = Path(temporary_directory) / "item.png"
            write_test_image(photo)

            dimensions = measure_image_dimensions(str(photo))

            self.assertEqual(dimensions["width"], 1)
            self.assertEqual(dimensions["height"], 1)

    def test_uniform_image_has_zero_blur_score(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            photo = Path(temporary_directory) / "item.png"
            write_test_image(photo)
            image = load_image(str(photo))

            score = measure_blur_score(image)

            self.assertEqual(score, 0.0)

    def test_lighting_detects_dark_and_bright_images(self) -> None:
        dark_image = np.zeros((10, 10, 3), dtype=np.uint8)
        bright_image = np.full((10, 10, 3), 255, dtype=np.uint8)

        dark_result = measure_lighting(dark_image)
        bright_result = measure_lighting(bright_image)

        self.assertEqual(dark_result["brightness_score"], 0.0)
        self.assertEqual(dark_result["lighting_status"], "too_dark")
        self.assertEqual(dark_result["contrast_status"], "low_contrast")
        self.assertEqual(bright_result["brightness_score"], 255.0)
        self.assertEqual(bright_result["lighting_status"], "too_bright")

    def test_possible_glare_detects_large_white_area(self) -> None:
        dark_image = np.zeros((10, 10, 3), dtype=np.uint8)
        white_image = np.full((10, 10, 3), 255, dtype=np.uint8)

        dark_result = measure_possible_glare(dark_image)
        white_result = measure_possible_glare(white_image)

        self.assertEqual(dark_result["possible_glare_percent"], 0.0)
        self.assertEqual(dark_result["glare_status"], "acceptable")
        self.assertEqual(white_result["possible_glare_percent"], 100.0)
        self.assertEqual(white_result["glare_status"], "possible_glare")

    def test_quality_warning_includes_retake_instruction(self) -> None:
        image_record = {
            "path": "/photos/tag.jpg",
            "resolution_status": "acceptable",
            "blur_status": "possibly_blurry",
            "lighting_status": "acceptable",
            "contrast_status": "acceptable",
            "glare_status": "acceptable",
        }

        warnings = build_quality_warnings(image_record, "tag_photo")

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["code"], "possibly_blurry")
        self.assertEqual(warnings[0]["photo_role"], "tag_photo")
        self.assertIn("focus", warnings[0]["retake_instruction"])

    def test_valid_files_produce_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            photo_directory = Path(temporary_directory)
            front = photo_directory / "front.png"
            back = photo_directory / "back.png"
            tag = photo_directory / "tag.png"

            for photo in (front, back, tag):
                write_test_image(photo)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        "--item",
                        str(front),
                        "--item",
                        str(back),
                        "--tag",
                        str(tag),
                    ]
                )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["status"], "quality_review_needed")
            self.assertEqual(len(result["item_photos"]), 2)
            self.assertEqual(result["item_photos"][0]["path"], str(front.resolve()))
            self.assertEqual(result["item_photos"][0]["width"], 1)
            self.assertEqual(result["item_photos"][0]["height"], 1)
            self.assertEqual(result["item_photos"][0]["megapixels"], 0.0)
            self.assertEqual(result["item_photos"][0]["resolution_status"], "too_low")
            self.assertEqual(result["item_photos"][0]["blur_score"], 0.0)
            self.assertEqual(
                result["item_photos"][0]["blur_status"],
                "possibly_blurry",
            )
            self.assertIn("brightness_score", result["item_photos"][0])
            self.assertIn("contrast_score", result["item_photos"][0])
            self.assertIn("possible_glare_percent", result["item_photos"][0])
            warning_codes = {warning["code"] for warning in result["warnings"]}
            self.assertIn("low_resolution", warning_codes)
            self.assertIn("possibly_blurry", warning_codes)
            self.assertEqual(result["tag_photo"]["path"], str(tag.resolve()))
            self.assertEqual(result["tag_photo"]["width"], 1)
            self.assertEqual(result["tag_photo"]["height"], 1)


if __name__ == "__main__":
    unittest.main()
