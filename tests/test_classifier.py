"""Tests for the first classifier command-line chunk."""

import base64
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from classifier import (
    build_quality_warnings,
    discover_photo_folder,
    load_image,
    main,
    measure_blur_score,
    measure_image_dimensions,
    measure_lighting,
    measure_possible_glare,
    validate_image_file,
    validate_inputs,
)
from openai_vision import (
    FACT_NAMES,
    VisionCallResult,
    VisionConfigurationError,
    VisionProviderError,
)
from photo_role_detection import resolve_proposed_roles
from review import ReviewCancelled

TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def write_test_image(path: Path) -> None:
    """Write a tiny real image without needing a fixture file in the repository."""
    path.write_bytes(TEST_PNG)


def model_analysis(tag_status: str = "unreadable") -> dict:
    return {
        "schema_version": 1,
        "tag_readability": {
            "status": tag_status,
            "confidence": 0.8,
            "issues": ["Text is too small"] if tag_status != "readable" else [],
            "retake_instructions": (
                ["Retake the full tag closer and in focus."]
                if tag_status != "readable"
                else []
            ),
        },
        "facts": {
            name: {
                "value": None,
                "confidence": 0,
                "provenance": [],
                "needs_review": True,
                "evidence": None,
                "conflicts": [],
            }
            for name in FACT_NAMES
        },
        "warnings": [],
    }


def fake_vision_result(tag_status: str = "unreadable") -> VisionCallResult:
    return VisionCallResult(
        analysis=model_analysis(tag_status),
        metadata={
            "response_id": "resp_test",
            "model": "gpt-5.6-luna",
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            "latency_ms": 12.5,
            "attempts": 1,
        },
    )


def fake_photo_role_result(tag_confidence: float = 0.95) -> VisionCallResult:
    return VisionCallResult(
        analysis={
            "schema_version": 1,
            "assignments": [
                {
                    "photo_id": "photo_1",
                    "visual_role": "back_view",
                    "confidence": 0.8,
                    "tag_likelihood": 0.05,
                    "evidence": "Back view.",
                },
                {
                    "photo_id": "photo_2",
                    "visual_role": "tag_photo",
                    "confidence": tag_confidence,
                    "tag_likelihood": 0.99,
                    "evidence": "Close-up tag.",
                },
                {
                    "photo_id": "photo_3",
                    "visual_role": "front_view",
                    "confidence": 0.9,
                    "tag_likelihood": 0.02,
                    "evidence": "Front view.",
                },
            ],
            "warnings": [],
        },
        metadata={
            "response_id": "resp_roles",
            "model": "gpt-5.6-luna",
            "usage": {"input_tokens": 5, "output_tokens": 6, "total_tokens": 11},
            "latency_ms": 10.0,
            "attempts": 1,
        },
    )


class InputValidationTests(unittest.TestCase):
    def test_discovers_supported_folder_photos_in_stable_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            for name in ("Z.png", "a.jpeg", "m.webp"):
                write_test_image(directory / name)
            (directory / ".DS_Store").write_text("ignored")
            (directory / "notes.txt").write_text("ignored")

            photos, errors = discover_photo_folder(str(directory))

        self.assertEqual(errors, [])
        self.assertEqual([Path(photo).name for photo in photos], ["a.jpeg", "m.webp", "Z.png"])

    def test_folder_requires_three_decodable_supported_images(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_test_image(directory / "one.png")
            write_test_image(directory / "two.png")

            photos, errors = discover_photo_folder(str(directory))

        self.assertEqual(len(photos), 2)
        self.assertIn("at least three", errors[0])

    def test_folder_mode_auto_routes_high_confidence_photo_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            for name in ("a.png", "b.png", "c.png"):
                write_test_image(directory / name)
            role_result = fake_photo_role_result()
            role_runner = mock.Mock(return_value=role_result)
            role_review_runner = mock.Mock()
            classifier_runner = mock.Mock(return_value=fake_vision_result())
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                exit_code = main(
                    ["--photo-folder", str(directory)],
                    photo_role_runner=role_runner,
                    photo_role_review_runner=role_review_runner,
                    vision_runner=classifier_runner,
                )

            result = json.loads(output.getvalue())
            discovered = role_runner.call_args.args[0]
            routed_items, routed_tag = classifier_runner.call_args.args

        self.assertEqual(exit_code, 4)
        self.assertEqual([Path(photo).name for photo in discovered], ["a.png", "b.png", "c.png"])
        self.assertEqual([Path(photo).name for photo in routed_items], ["c.png", "a.png"])
        self.assertEqual(Path(routed_tag).name, "b.png")
        self.assertEqual(result["photo_role_metadata"]["response_id"], "resp_roles")
        self.assertEqual(
            Path(result["photo_role_detection"]["resolved_roles"]["tag_photo"]).name,
            "b.png",
        )
        self.assertEqual(
            result["photo_role_detection"]["resolution"]["mode"],
            "automatic_high_confidence",
        )
        self.assertEqual(
            result["photo_role_detection"]["resolution"]["review_threshold"],
            0.6,
        )
        role_review_runner.assert_not_called()

    def test_folder_mode_reviews_photo_roles_below_sixty_percent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            for name in ("a.png", "b.png", "c.png"):
                write_test_image(directory / name)
            role_result = fake_photo_role_result(tag_confidence=0.59)
            reviewed_roles = resolve_proposed_roles(
                [str(directory / name) for name in ("a.png", "b.png", "c.png")],
                role_result.analysis,
            )
            role_review_runner = mock.Mock(return_value=reviewed_roles)
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                exit_code = main(
                    ["--photo-folder", str(directory)],
                    photo_role_runner=lambda photos: role_result,
                    photo_role_review_runner=role_review_runner,
                    vision_runner=lambda item_photos, tag_photo: fake_vision_result(),
                )

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 4)
        role_review_runner.assert_called_once()
        self.assertEqual(
            result["photo_role_detection"]["resolution"]["mode"],
            "user_reviewed_low_confidence",
        )

    def test_folder_mode_cannot_mix_with_explicit_roles(self) -> None:
        role_runner = mock.Mock()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                ["--photo-folder", "/tmp/photos", "--item", "/tmp/item.png"],
                photo_role_runner=role_runner,
            )

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(result["status"], "input_error")
        self.assertIn("by itself", result["errors"][0])
        role_runner.assert_not_called()

    def test_folder_role_provider_error_stops_before_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            for name in ("a.png", "b.png", "c.png"):
                write_test_image(directory / name)
            classifier_runner = mock.Mock()
            output = io.StringIO()

            def missing_key(photos):
                raise VisionConfigurationError(
                    "missing_api_key",
                    "Set OPENAI_API_KEY before running hosted vision analysis.",
                )

            with contextlib.redirect_stdout(output):
                exit_code = main(
                    ["--photo-folder", str(directory)],
                    photo_role_runner=missing_key,
                    vision_runner=classifier_runner,
                )

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(result["status"], "configuration_error")
        self.assertEqual(result["error"]["code"], "missing_api_key")
        classifier_runner.assert_not_called()

    def test_folder_role_review_can_cancel_before_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            for name in ("a.png", "b.png", "c.png"):
                write_test_image(directory / name)
            classifier_runner = mock.Mock()
            output = io.StringIO()

            def cancel_review(photos, analysis):
                raise ReviewCancelled("cancelled")

            with contextlib.redirect_stdout(output):
                exit_code = main(
                    ["--photo-folder", str(directory)],
                    photo_role_runner=lambda photos: fake_photo_role_result(
                        tag_confidence=0.59
                    ),
                    photo_role_review_runner=cancel_review,
                    vision_runner=classifier_runner,
                )

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "review_cancelled")
        self.assertEqual(result["review_stage"], "photo_roles")
        classifier_runner.assert_not_called()

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
                    ],
                    vision_runner=lambda item_photos, tag_photo: fake_vision_result(),
                )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 4)
            self.assertEqual(result["status"], "tag_retake_required")
            self.assertEqual(result["model_analysis"]["schema_version"], 1)
            self.assertEqual(result["model_metadata"]["response_id"], "resp_test")
            self.assertIsNone(result["validated_facts"])
            self.assertIsNone(result["listing_draft"])
            self.assertEqual(result["next_step"], "retake_tag_photo")
            self.assertTrue(result["tag_retake_instructions"])
            self.assertEqual(len(result["item_photos"]), 2)
            self.assertEqual(
                result["image_analysis"]["item_photos"],
                result["item_photos"],
            )
            self.assertEqual(
                result["image_analysis"]["tag_photo"],
                result["tag_photo"],
            )
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

    def test_input_errors_preserve_the_pipeline_stage_shape(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(["--item", "missing.jpg", "--tag", "missing-tag.jpg"])

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(result["status"], "input_error")
        self.assertEqual(result["image_analysis"], {})
        self.assertIsNone(result["model_analysis"])
        self.assertIsNone(result["model_metadata"])
        self.assertIsNone(result["validated_facts"])
        self.assertIsNone(result["listing_draft"])
        self.assertTrue(result["errors"])

    def test_invalid_local_inputs_never_call_vision_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            front = directory / "front.png"
            back = directory / "back.png"
            tag = directory / "tag.png"
            unsupported = directory / "item.gif"
            undecodable = directory / "item.jpg"
            for photo in (front, back, tag):
                write_test_image(photo)
            unsupported.write_bytes(TEST_PNG)
            undecodable.write_text("not an image")
            cases = {
                "too_few": ["--item", str(front), "--tag", str(tag)],
                "missing_tag_argument": [
                    "--item", str(front), "--item", str(back)
                ],
                "missing_item_arguments": ["--tag", str(tag)],
                "missing": [
                    "--item", str(front), "--item", str(directory / "missing.png"), "--tag", str(tag)
                ],
                "unsupported": [
                    "--item", str(unsupported), "--item", str(back), "--tag", str(tag)
                ],
                "undecodable": [
                    "--item", str(undecodable), "--item", str(back), "--tag", str(tag)
                ],
            }

            for name, arguments in cases.items():
                with self.subTest(name=name):
                    runner = mock.Mock()
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        exit_code = main(arguments, vision_runner=runner)

                    self.assertEqual(exit_code, 1)
                    runner.assert_not_called()

    def test_readable_analysis_produces_reviewable_validated_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = [Path(temporary_directory) / name for name in ("front.png", "back.png", "tag.png")]
            for path in paths:
                write_test_image(path)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    ["--item", str(paths[0]), "--item", str(paths[1]), "--tag", str(paths[2])],
                    vision_runner=lambda item_photos, tag_photo: fake_vision_result("readable"),
                )

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "review_required")
        self.assertIsNotNone(result["validated_facts"])
        self.assertIsNone(result["listing_draft"])

    def test_review_mode_returns_approved_facts_and_listing_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = [Path(temporary_directory) / name for name in ("front.png", "back.png", "tag.png")]
            for path in paths:
                write_test_image(path)
            approved = {
                "category": "Men >> Bottoms >> Jeans (menswear, bottoms, jeans)",
                "item_type": "Jeans",
                "brand": "Levi's (levi-s)",
                "condition": "Used - Good (used_good)",
                "size": '36"',
                "inseam": '34"',
                "primary_color": "Black (black)",
            }
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        "--item", str(paths[0]), "--item", str(paths[1]),
                        "--tag", str(paths[2]), "--review",
                    ],
                    vision_runner=lambda item_photos, tag_photo: fake_vision_result("readable"),
                    review_runner=lambda facts: approved,
                    listing_review_runner=lambda draft: draft,
                    output_directory=Path(temporary_directory) / "approved_listings",
                )

            result = json.loads(output.getvalue())
            saved_path = Path(result["saved_to"])
            saved = json.loads(saved_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "listing_approved")
        self.assertEqual(result["approved_facts"], approved)
        self.assertIn('34" inseam', result["listing_draft"]["description"])
        self.assertEqual(result["review_reasons"], [])
        self.assertEqual(result["next_step"], "export_later")
        self.assertEqual(saved, result)
        self.assertRegex(saved_path.name, r"^approved-listing-[0-9a-f]{32}\.json$")

    def test_review_mode_automatically_uses_a_unique_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            paths = [directory / name for name in ("front.png", "back.png", "tag.png")]
            for path in paths:
                write_test_image(path)
            output_directory = directory / "approved_listings"
            approved = {
                "category": "Men >> Bottoms >> Jeans (menswear, bottoms, jeans)",
                "item_type": "Jeans",
                "brand": "Levi's (levi-s)",
                "condition": "Used - Good (used_good)",
                "size": '36"',
                "inseam": '34"',
                "primary_color": "Black (black)",
            }
            arguments = [
                "--item", str(paths[0]), "--item", str(paths[1]),
                "--tag", str(paths[2]), "--review",
            ]
            saved_paths: list[Path] = []

            for _ in range(2):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    exit_code = main(
                        arguments,
                        vision_runner=lambda item_photos, tag_photo: fake_vision_result("readable"),
                        review_runner=lambda facts: approved,
                        listing_review_runner=lambda draft: draft,
                        output_directory=output_directory,
                    )
                result = json.loads(output.getvalue())
                saved_paths.append(Path(result["saved_to"]))
                self.assertEqual(exit_code, 0)
                self.assertEqual(result["status"], "listing_approved")

            self.assertNotEqual(saved_paths[0], saved_paths[1])
            self.assertTrue(all(path.is_file() for path in saved_paths))
            self.assertEqual(len(list(output_directory.glob("*.json"))), 2)

    def test_missing_api_key_is_a_structured_configuration_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = [Path(temporary_directory) / name for name in ("front.png", "back.png", "tag.png")]
            for path in paths:
                write_test_image(path)
            output = io.StringIO()
            environment = dict(os.environ)
            environment.pop("OPENAI_API_KEY", None)
            with mock.patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    exit_code = main(
                        ["--item", str(paths[0]), "--item", str(paths[1]), "--tag", str(paths[2])]
                    )

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(result["status"], "configuration_error")
        self.assertEqual(result["error"]["code"], "missing_api_key")

    def test_provider_error_is_structured_and_secret_safe(self) -> None:
        secret = "sk-user-secret-value"

        def failing_runner(item_photos, tag_photo):
            try:
                raise RuntimeError(f"Authorization: Bearer {secret}")
            except RuntimeError as error:
                raise VisionProviderError(
                    "connection_error",
                    "Hosted vision analysis could not reach the provider after bounded retries.",
                    transient=True,
                ) from error

        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = [Path(temporary_directory) / name for name in ("front.png", "back.png", "tag.png")]
            for path in paths:
                write_test_image(path)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    ["--item", str(paths[0]), "--item", str(paths[1]), "--tag", str(paths[2])],
                    vision_runner=failing_runner,
                )

        serialized = output.getvalue()
        self.assertEqual(exit_code, 3)
        self.assertNotIn(secret, serialized)
        self.assertEqual(json.loads(serialized)["status"], "model_error")


if __name__ == "__main__":
    unittest.main()
