"""Offline coverage for the terminal-independent pipeline service boundary."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openai_vision import VisionConfigurationError
from pipeline_service import PipelineService
from tests.test_classifier import (
    fake_photo_role_result,
    fake_vision_result,
    write_test_image,
)


class PipelineServiceTests(unittest.TestCase):
    def _photos(self, directory: str) -> tuple[list[str], str]:
        paths = [Path(directory) / name for name in ("a.png", "b.png", "c.png")]
        for path in paths:
            write_test_image(path)
        return [str(paths[0]), str(paths[2])], str(paths[1])

    def test_explicit_classification_returns_without_terminal_io(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            item_photos, tag_photo = self._photos(directory)
            runner = mock.Mock(return_value=fake_vision_result())
            service = PipelineService(vision_runner=runner)
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                result = service.classify_explicit(item_photos, tag_photo)

        self.assertEqual(output.getvalue(), "")
        self.assertEqual(result["status"], "tag_retake_required")
        runner.assert_called_once_with(item_photos, tag_photo)

    def test_high_confidence_folder_roles_continue_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            item_photos, tag_photo = self._photos(directory)
            folder_photos = [item_photos[0], tag_photo, item_photos[1]]
            service = PipelineService(
                vision_runner=mock.Mock(return_value=fake_vision_result()),
                photo_role_runner=mock.Mock(return_value=fake_photo_role_result()),
            )
            result = service.start_folder_classification(folder_photos)

        self.assertEqual(result["status"], "tag_retake_required")
        self.assertEqual(
            result["photo_role_detection"]["resolution"]["mode"],
            "automatic_high_confidence",
        )

    def test_low_confidence_folder_roles_return_structured_review_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            item_photos, tag_photo = self._photos(directory)
            service = PipelineService(
                vision_runner=mock.Mock(),
                photo_role_runner=mock.Mock(return_value=fake_photo_role_result(0.59)),
            )
            result = service.start_folder_classification([item_photos[0], tag_photo, item_photos[1]])

        self.assertEqual(result["status"], "photo_role_review_required")
        self.assertEqual(result["review_stage"], "photo_roles")
        self.assertEqual(result["next_step"], "review_photo_roles")
        self.assertEqual(result["photo_role_detection"]["resolution"]["tag_confidence"], 0.59)
        service.vision_runner.assert_not_called()

    def test_configuration_failure_is_structured_and_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            item_photos, tag_photo = self._photos(directory)
            def fail(items, tag):
                raise VisionConfigurationError(
                    "missing_api_key",
                    "Set OPENAI_API_KEY before running hosted vision analysis.",
                )
            result = PipelineService(vision_runner=fail).classify_explicit(item_photos, tag_photo)

        self.assertEqual(result["status"], "configuration_error")
        self.assertEqual(result["error"]["code"], "missing_api_key")
        self.assertEqual(
            result["error"]["message"],
            "Set OPENAI_API_KEY before running hosted vision analysis.",
        )


if __name__ == "__main__":
    unittest.main()
