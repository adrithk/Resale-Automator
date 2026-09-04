"""Offline photo-hosting checks: no customer photos or credentials are sent."""

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from cloudinary.exceptions import NotAllowed

from photo_hosting import PhotoHostingError, host_listing_photos, prepare_hosted_photo


TEST_ENV = {"CLOUDINARY_CLOUD_NAME": "test-cloud", "CLOUDINARY_API_KEY": "test-key", "CLOUDINARY_API_SECRET": "test-secret"}


def upload_response(file, **options):
    return {"public_id": options["public_id"], "secure_url": f"https://res.cloudinary.com/test-cloud/image/upload/v1/{options['public_id']}.jpg"}


class PhotoHostingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.paths = []
        for index, color in enumerate(("red", "green", "blue")):
            path = self.root / f"photo-{index:032x}.png"
            Image.new("RGB", (40, 60), color).save(path)
            self.paths.append(str(path))

    def host(self, paths=None):
        return host_listing_photos(self.paths if paths is None else paths, upload_directory=self.root, environ=TEST_ENV)

    def test_order_tag_inclusion_cache_and_private_response_fields(self):
        with patch("photo_hosting.cloudinary.uploader.upload", side_effect=upload_response) as upload:
            urls = self.host()
            self.assertEqual(len(urls), 3)
            self.assertEqual(upload.call_count, 3)
            for call in upload.call_args_list:
                self.assertFalse(call.kwargs["overwrite"])
                self.assertEqual(call.kwargs["timeout"], 60)
                self.assertEqual(call.kwargs["api_secret"], "test-secret")
            self.assertEqual(self.host(list(reversed(self.paths))), list(reversed(urls)))
            self.assertEqual(upload.call_count, 3)
        for cache in (self.root / "hosted").glob("*.json"):
            self.assertEqual(set(json.loads(cache.read_text())), {"secure_url", "public_id"})
            self.assertNotIn("test-secret", cache.read_text())

    def test_partial_failure_reuses_success_and_redacts_sdk_error(self):
        calls = 0
        def failing(file, **options):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("test-secret private SDK details")
            return upload_response(file, **options)
        with patch("photo_hosting.cloudinary.uploader.upload", side_effect=failing):
            with self.assertRaises(PhotoHostingError) as caught:
                self.host()
            self.assertNotIn("test-secret", str(caught.exception))
        with patch("photo_hosting.cloudinary.uploader.upload", side_effect=upload_response) as upload:
            self.assertEqual(len(self.host()), 3)
            self.assertEqual(upload.call_count, 2)

    def test_invalid_batches_and_paths_make_no_uploads(self):
        outside = self.root / "outside.png"
        Image.new("RGB", (10, 10)).save(outside)
        link = self.root / f"photo-{'f' * 32}.png"
        link.symlink_to(self.paths[0])
        for paths in ([], self.paths[:2], self.paths * 3, [*self.paths[:2], str(outside)], [*self.paths[:2], str(link)]):
            with self.subTest(paths=paths), patch("photo_hosting.cloudinary.uploader.upload") as upload:
                with self.assertRaises(PhotoHostingError):
                    self.host(paths)
                upload.assert_not_called()
        Path(self.paths[-1]).write_bytes(b"not an image")
        with patch("photo_hosting.cloudinary.uploader.upload") as upload:
            with self.assertRaises(PhotoHostingError):
                self.host()
            upload.assert_not_called()

    def test_wrong_cloud_response_is_rejected(self):
        with patch("photo_hosting.cloudinary.uploader.upload", return_value={
            "public_id": "bad", "secure_url": "http://localhost/private.jpg",
        }):
            with self.assertRaises(PhotoHostingError):
                self.host()

    def test_preparation_preserves_orientation_and_removes_exif(self):
        path = self.root / "oriented.jpg"
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "private location metadata"
        Image.new("RGB", (20, 40), "red").save(path, exif=exif)
        original = path.read_bytes()
        with Image.open(BytesIO(prepare_hosted_photo(path))) as clean:
            self.assertEqual(clean.size, (40, 20))
            self.assertFalse(clean.getexif())
        self.assertEqual(path.read_bytes(), original)

    def test_phone_mpo_primary_frame_is_hostable_and_limits_still_apply(self):
        path = self.root / "phone.jpg"
        Image.new("RGB", (40, 60), "red").save(
            path, format="MPO", save_all=True,
            append_images=[Image.new("RGB", (40, 60), "blue")],
        )
        original = path.read_bytes()
        with Image.open(BytesIO(prepare_hosted_photo(path))) as clean:
            self.assertEqual(clean.format, "JPEG")
            self.assertEqual(getattr(clean, "n_frames", 1), 1)
            self.assertGreater(clean.getpixel((0, 0))[0], 240)
        self.assertEqual(path.read_bytes(), original)
        for limit in ("MAX_PHOTO_PIXELS", "MAX_PHOTO_BYTES"):
            with patch(f"photo_hosting.{limit}", 1), self.assertRaises(PhotoHostingError):
                prepare_hosted_photo(path)

    def test_transparent_pixels_are_white_and_animation_is_rejected(self):
        path = self.root / "transparent.png"
        Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(path)
        with Image.open(BytesIO(prepare_hosted_photo(path))) as clean:
            self.assertEqual(clean.getpixel((0, 0)), (255, 255, 255))
        Image.new("RGB", (20, 20), "red").save(path, save_all=True,
            append_images=[Image.new("RGB", (20, 20), "blue")])
        with self.assertRaises(PhotoHostingError):
            prepare_hosted_photo(path)

    def test_missing_configuration_blocks_network(self):
        with patch("photo_hosting.cloudinary.uploader.upload") as upload:
            with self.assertRaises(PhotoHostingError):
                host_listing_photos(self.paths, upload_directory=self.root, environ={})
            upload.assert_not_called()

    def test_permission_failure_is_actionable_without_provider_details(self):
        with patch("photo_hosting.cloudinary.uploader.upload", side_effect=NotAllowed("private account detail")):
            with self.assertRaises(PhotoHostingError) as caught:
                self.host()
        self.assertIn("create/upload permission", str(caught.exception))
        self.assertNotIn("private account detail", str(caught.exception))


class LocalConfigTests(unittest.TestCase):
    def test_dotenv_is_root_scoped_and_preserves_shell_values(self):
        from local_config import load_backend_environment
        with patch("local_config.load_dotenv") as loader:
            load_backend_environment()
        self.assertEqual(loader.call_args.args[0], Path(__file__).resolve().parents[1] / ".env")
        self.assertEqual(loader.call_args.kwargs, {"override": False, "interpolate": False})
