"""Offline integration tests for the thin FastAPI adapter."""

import unittest
import base64
import csv
from io import BytesIO, StringIO
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import create_app
from review_validation import FINAL_FACT_NAMES
from openai_vision import VisionCallResult, VisionProviderError
from tests.test_depop_csv import approved_facts, PICTURE_URLS
from photo_hosting import PhotoHostingError
from local_persistence import save_approved_result
from tests.test_photo_hosting import TEST_ENV, upload_response
from PIL import Image


TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakePipelineService:
    def start_folder_classification(self, photo_paths):
        return {"status": "facts_validated", "paths": photo_paths}

    def classify_explicit(self, item_photo_paths, tag_photo_path):
        return {"status": "facts_validated", "items": item_photo_paths, "tag": tag_photo_path}

    def classify_confirmed_folder(self, photo_paths, detection, confirmed_roles):
        return {"status": "facts_validated", "tag": confirmed_roles.tag_photo}


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        location_patch = patch.dict("os.environ", {"DEPOP_SHIPPING_LOCATION": "California, United States"})
        location_patch.start()
        self.addCleanup(location_patch.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.upload_root = Path(directory.name)
        uploads_patch = patch("api.LOCAL_UPLOAD_DIRECTORY", self.upload_root)
        uploads_patch.start()
        self.addCleanup(uploads_patch.stop)
        self.client = TestClient(create_app(FakePipelineService()))

    def test_health_and_explicit_classification_delegate_to_service(self) -> None:
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        response = self.client.post(
            "/classifications/explicit",
            json={"item_photo_paths": ["a.jpg", "b.jpg"], "tag_photo_path": "tag.jpg"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "facts_validated")

    def test_browser_automation_routes_are_not_available(self) -> None:
        self.assertEqual(self.client.post("/depop/uploads", json={}).status_code, 404)
        self.assertEqual(self.client.get("/depop/uploads/" + "a" * 64).status_code, 404)

    def test_path_counts_are_checked_at_the_http_boundary(self) -> None:
        response = self.client.post(
            "/classifications/explicit",
            json={"item_photo_paths": ["a.jpg"], "tag_photo_path": "tag.jpg"},
        )
        self.assertEqual(response.status_code, 422)

    def test_folder_roles_are_returned_without_prompting(self) -> None:
        response = self.client.post(
            "/photo-roles",
            json={"photo_paths": ["a.jpg", "b.jpg", "tag.jpg"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "facts_validated")

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

    def test_csv_export_requires_explicit_approval_and_downloads_csv(self) -> None:
        facts = {name: None for name in FINAL_FACT_NAMES}
        facts.update(
            {
                "category": "Men >> Bottoms >> Jeans (menswear, bottoms, jeans)",
                "item_type": "Jeans",
                "brand": "Levi's (levi-s)",
                "condition": "Used - Good (used_good)",
                "size": '36"',
                "primary_color": "Black (black)",
            }
        )
        payload = {
            "approved_facts": facts,
            "listing_draft": {"draft_title": "Title", "description": "Description"},
            "user_approved": True,
            "price": "14.50",
            "picture_urls": PICTURE_URLS,
        }
        response = self.client.post("/listings/export.csv", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/csv; charset=utf-8")
        self.assertIn("attachment; filename=", response.headers["content-disposition"])
        reference = json.loads(
            (Path(__file__).parent / "fixtures" / "depop_csv_template_v6.json").read_text()
        )
        rows = list(csv.reader(StringIO(response.text)))
        self.assertEqual(rows[:3], reference["rows"])
        self.assertEqual(rows[3][0], "Description")
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[3][2], "14.50")
        self.assertEqual(rows[3][14], "California, United States")
        self.assertEqual(rows[3][15:18], PICTURE_URLS)

        payload["listing_draft"]["description"] = "a" * 1001
        self.assertEqual(self.client.post("/listings/export.csv", json=payload).status_code, 422)
        payload["listing_draft"]["description"] = "Description"

        payload["user_approved"] = False
        self.assertEqual(
            self.client.post("/listings/export.csv", json=payload).status_code,
            422,
        )

    def test_model_price_is_editable_saved_and_exported_without_repricing(self):
        suggestion = VisionCallResult(analysis={"price": "12.00", "estimated_resale_value_usd": "24.00"}, metadata={"response_id": "price-test"})
        with patch("api.suggest_price", return_value=suggestion) as pricing, patch("api.save_approved_result") as save, patch("api.host_listing_photos", return_value=PICTURE_URLS) as host:
            response = self.client.post("/listing-drafts", json={"facts": approved_facts()})
            self.assertEqual(response.status_code, 200)
            generated = response.json()
            self.assertEqual(generated["price"], "12.00")
            approved = self.client.post("/listings/approve", json={
                "facts": approved_facts(), "pipeline_result": {},
                "listing_draft": generated["listing_draft"], "price": "14.75",
                "photo_paths": ["front.jpg", "back.jpg", "tag.jpg"],
            })
            self.assertEqual(approved.status_code, 200)
            self.assertEqual(save.call_args.args[0]["price"], "14.75")
            self.assertEqual(approved.json()["shipping_location"], "California, United States")
            self.assertEqual(save.call_args.args[0]["picture_urls"], PICTURE_URLS)
            self.assertEqual(host.call_args.args[0], ["front.jpg", "back.jpg", "tag.jpg"])
            exported = self.client.post("/listings/export.csv", json={
                "approved_facts": approved.json()["approved_facts"],
                "listing_draft": approved.json()["listing_draft"],
                "price": approved.json()["price"], "user_approved": True,
                "picture_urls": approved.json()["picture_urls"],
            })
            self.assertEqual(exported.status_code, 200)
            self.assertEqual(list(csv.reader(StringIO(exported.text)))[3][2], "14.75")
            pricing.assert_called_once()
            self.assertEqual(list(csv.reader(StringIO(exported.text)))[3][15:18], PICTURE_URLS)
            self.client.post("/listings/export.csv", json={
                "approved_facts": approved.json()["approved_facts"], "listing_draft": approved.json()["listing_draft"],
                "price": "14.75", "user_approved": True, "picture_urls": PICTURE_URLS,
            })
            host.assert_called_once()

    def test_invalid_facts_skip_pricing_and_invalid_price_skips_save(self):
        with patch("api.suggest_price") as pricing, patch("api.save_approved_result") as save, patch("api.host_listing_photos") as host:
            self.assertEqual(self.client.post("/listing-drafts", json={"facts": {}}).status_code, 422)
            pricing.assert_not_called()
            self.assertEqual(self.client.post("/listings/approve", json={
                "facts": approved_facts(), "pipeline_result": {},
                "listing_draft": {"draft_title": "Title", "description": "Description"}, "price": "",
                "photo_paths": ["front.jpg", "back.jpg", "tag.jpg"],
            }).status_code, 422)
            save.assert_not_called()
            host.assert_not_called()

    def test_hosting_failure_blocks_save_and_missing_links_block_export(self):
        with patch("api.host_listing_photos", side_effect=PhotoHostingError("Photo upload failed.")), patch("api.save_approved_result") as save:
            response = self.client.post("/listings/approve", json={
                "facts": approved_facts(), "pipeline_result": {}, "price": "12",
                "listing_draft": {"draft_title": "Title", "description": "Description"},
                "photo_paths": ["front.jpg", "back.jpg", "tag.jpg"],
            })
            self.assertEqual(response.status_code, 502)
            save.assert_not_called()
        response = self.client.post("/listings/export.csv", json={
            "approved_facts": approved_facts(), "price": "12", "user_approved": True,
            "listing_draft": {"draft_title": "Title", "description": "Description"},
        })
        self.assertEqual(response.status_code, 422)

    def test_upload_save_and_csv_work_together_with_only_cloudinary_network_mocked(self):
        paths = []
        for color in ("red", "green", "blue"):
            image = BytesIO()
            Image.new("RGB", (32, 32), color).save(image, format="PNG")
            response = self.client.post("/uploads", files={"photo": ("photo.png", image.getvalue(), "image/png")})
            self.assertEqual(response.status_code, 200)
            paths.append(response.json()["photo_path"])
        with patch.dict("os.environ", TEST_ENV), patch("photo_hosting.cloudinary.uploader.upload", side_effect=upload_response) as upload, patch(
            "api.save_approved_result", side_effect=lambda result: save_approved_result(result, output_directory=self.upload_root / "approved")
        ):
            response = self.client.post("/listings/approve", json={
                "facts": approved_facts(), "pipeline_result": {}, "price": "12",
                "listing_draft": {"draft_title": "Title", "description": "Description"},
                "photo_paths": paths,
            })
            self.assertEqual(response.status_code, 200)
            approved = response.json()
            saved = json.loads(Path(approved["saved_to"]).read_text())
            self.assertEqual(saved["picture_urls"], approved["picture_urls"])
            self.assertEqual(saved["uploaded_photo_paths"], paths)
            for _ in range(2):
                exported = self.client.post("/listings/export.csv", json={
                    "approved_facts": approved["approved_facts"], "listing_draft": approved["listing_draft"],
                    "price": approved["price"], "picture_urls": approved["picture_urls"], "user_approved": True,
                })
                self.assertEqual(exported.status_code, 200)
                self.assertEqual(list(csv.reader(StringIO(exported.text)))[3][15:18], approved["picture_urls"])
            self.assertEqual(upload.call_count, 3)

    def test_pricing_failure_does_not_leak_raw_provider_details(self):
        with patch("api.suggest_price", side_effect=VisionProviderError("test", "private-provider-detail")):
            response = self.client.post("/listing-drafts", json={"facts": approved_facts()})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private-provider-detail", response.text)


if __name__ == "__main__":
    unittest.main()
