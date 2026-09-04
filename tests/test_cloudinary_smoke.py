"""Opt-in Cloudinary integration test using disposable synthetic images only."""

import hashlib
from io import BytesIO
import os
import ssl
from pathlib import Path
import tempfile
import unittest
from urllib.request import urlopen
import uuid

import cloudinary.uploader
import certifi
from PIL import Image, ImageDraw

from local_config import load_backend_environment
from photo_hosting import host_listing_photos, prepare_hosted_photo


@unittest.skipUnless(os.environ.get("RESALE_RUN_CLOUDINARY_SMOKE") == "1", "Cloudinary live smoke is opt-in")
class CloudinarySmokeTests(unittest.TestCase):
    def test_synthetic_uploads_are_publicly_readable_and_cleaned_up(self):
        load_backend_environment()
        credentials = {name: os.environ.get(f"CLOUDINARY_{name.upper()}", "")
                       for name in ("cloud_name", "api_key", "api_secret")}
        # Unique visible test markers make these IDs unrelated to user assets.
        marker = uuid.uuid4().hex
        public_ids = []
        failure = ""
        stage = "upload"
        cleanup_failed = False
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for index, color in enumerate(("red", "green", "blue")):
                image = Image.new("RGB", (320, 240), color)
                ImageDraw.Draw(image).text((10, 20), f"Disposable integration test {marker} {index}", fill="white")
                path = root / f"photo-{uuid.uuid4().hex}.png"
                image.save(path)
                paths.append(str(path))
                public_ids.append("relist/" + hashlib.sha256(prepare_hosted_photo(path)).hexdigest())
            try:
                urls = host_listing_photos(paths, upload_directory=root)
                if len(urls) != 3:
                    raise ValueError("missing images")
                stage = "public download"
                for url in urls:
                    with urlopen(url, timeout=30, context=ssl.create_default_context(cafile=certifi.where())) as response:
                        with Image.open(BytesIO(response.read(10 * 1024 * 1024))) as downloaded:
                            if downloaded.size != (320, 240) or downloaded.getexif():
                                raise ValueError("unexpected image")
            except Exception as error:
                # Never print provider exceptions, request URLs, or credentials.
                cause = type(error.__cause__).__name__ if error.__cause__ else "none"
                failure = f"{stage}: {type(error).__name__}, cause {cause}"
            finally:
                for public_id in public_ids:
                    try:
                        outcome = cloudinary.uploader.destroy(public_id, **credentials, resource_type="image", type="upload", invalidate=True, timeout=30)
                        if outcome.get("result") not in {"ok", "not found"}:
                            cleanup_failed = True
                    except Exception:
                        cleanup_failed = True
        self.assertFalse(cleanup_failed, "Synthetic test cleanup failed; remove only images showing this test marker in Cloudinary: " + marker)
        self.assertFalse(failure, "Cloudinary verification failed (" + failure + "). No provider details were printed.")
