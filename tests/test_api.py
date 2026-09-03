"""Offline integration tests for the thin FastAPI adapter."""

import unittest
import base64

from fastapi.testclient import TestClient

from api import create_app


TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakePipelineService:
    def start_folder_classification(self, photo_paths):
        return {"status": "photo_role_review_required", "paths": photo_paths}

    def classify_explicit(self, item_photo_paths, tag_photo_path):
        return {"status": "facts_validated", "items": item_photo_paths, "tag": tag_photo_path}

    def classify_confirmed_folder(self, photo_paths, detection, confirmed_roles):
        return {"status": "facts_validated", "tag": confirmed_roles.tag_photo}


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app(FakePipelineService()))

    def test_health_and_explicit_classification_delegate_to_service(self) -> None:
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        response = self.client.post(
            "/classifications/explicit",
            json={"item_photo_paths": ["a.jpg", "b.jpg"], "tag_photo_path": "tag.jpg"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "facts_validated")

    def test_path_counts_are_checked_at_the_http_boundary(self) -> None:
        response = self.client.post(
            "/classifications/explicit",
            json={"item_photo_paths": ["a.jpg"], "tag_photo_path": "tag.jpg"},
        )
        self.assertEqual(response.status_code, 422)

    def test_low_confidence_role_state_is_returned_without_prompting(self) -> None:
        response = self.client.post(
            "/photo-roles",
            json={"photo_paths": ["a.jpg", "b.jpg", "tag.jpg"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "photo_role_review_required")

    def test_draft_validation_returns_structured_errors(self) -> None:
        response = self.client.post("/listing-drafts/validate", json={"draft_title": "", "description": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["valid"])

    def test_local_upload_requires_an_allowed_decodable_image(self) -> None:
        response = self.client.post(
            "/uploads",
            files={"photo": ("tag.png", TEST_PNG, "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["photo_path"].endswith(".png"))


if __name__ == "__main__":
    unittest.main()
