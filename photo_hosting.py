"""Host metadata-free copies of browser uploads; never publish to a marketplace."""

from __future__ import annotations

import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

import cloudinary.uploader
from cloudinary.exceptions import NotAllowed
from PIL import Image, ImageOps, UnidentifiedImageError


LOCAL_UPLOAD_DIRECTORY = Path(__file__).resolve().parent / "local_uploads"
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_PHOTO_PIXELS = 40_000_000
UPLOAD_NAME = re.compile(r"photo-[a-f0-9]{32}\.(?:jpg|jpeg|png|webp)")
HOSTED_URL = re.compile(
    r"https://res\.cloudinary\.com/[a-z0-9_-]+/image/upload/"
    r"v[0-9]+/relist/[a-f0-9]{64}\.jpg"
)


class PhotoHostingError(ValueError):
    """Actionable, secret-safe error for local preparation or hosted upload."""


def validate_picture_urls(urls: Sequence[str], *, minimum: int = 3) -> list[str]:
    if not isinstance(urls, (list, tuple)) or not minimum <= len(urls) <= 8:
        raise PhotoHostingError("Include 3–8 uploaded photos before exporting the CSV.")
    if any(not isinstance(url, str) or not HOSTED_URL.fullmatch(url) for url in urls):
        raise PhotoHostingError("Photo links are missing or invalid. Approve the listing again to host its photos.")
    return list(urls)


def _credentials(environ: Mapping[str, str] | None) -> dict[str, str]:
    environment = os.environ if environ is None else environ
    values = {
        name: environment.get(f"CLOUDINARY_{name.upper()}", "").strip()
        for name in ("cloud_name", "api_key", "api_secret")
    }
    if any(not value or value.startswith("your_") for value in values.values()):
        raise PhotoHostingError("Fill in all three Cloudinary settings in the root .env file and restart the backend.")
    if not re.fullmatch(r"[a-z0-9_-]+", values["cloud_name"]):
        raise PhotoHostingError("CLOUDINARY_CLOUD_NAME must be the cloud name, not an email or URL.")
    return values


def _upload_path(value: str, root: Path) -> Path:
    path = Path(value)
    if path.is_symlink() or path.resolve().parent != root.resolve() or not UPLOAD_NAME.fullmatch(path.name):
        raise PhotoHostingError("Only photos uploaded through this website can be hosted. Select the photos again.")
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_PHOTO_BYTES:
        raise PhotoHostingError("A local photo is missing or exceeds 10 MB. Select the photos again.")
    return path


def prepare_hosted_photo(path: Path) -> bytes:
    """Preserve orientation/dimensions, flatten transparency, omit all metadata."""
    try:
        with Image.open(path) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"} or getattr(source, "n_frames", 1) != 1:
                raise PhotoHostingError("Use still JPEG, PNG, or WebP photos, not animated images.")
            if source.width * source.height > MAX_PHOTO_PIXELS:
                raise PhotoHostingError("Each photo must be at most 40 megapixels for hosting.")
            oriented = ImageOps.exif_transpose(source)
            rgba = oriented.convert("RGBA")
            clean = Image.new("RGB", rgba.size, "white")
            clean.paste(rgba, mask=rgba.getchannel("A"))
            output = BytesIO()
            clean.save(output, format="JPEG", quality=95)
            data = output.getvalue()
    except PhotoHostingError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise PhotoHostingError("A photo could not be prepared for hosting. Select a readable JPEG, PNG, or WebP.") from error
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoHostingError("A prepared photo exceeds 10 MB. Use a smaller image.")
    return data


def _checked_response(response: Any, cloud: str, public_id: str) -> str:
    if not isinstance(response, dict):
        raise PhotoHostingError("Cloudinary returned an invalid photo response. Retry saving the listing.")
    url = response.get("secure_url")
    validate_picture_urls([url], minimum=1)
    if (response.get("public_id") != public_id
            or not url.startswith(f"https://res.cloudinary.com/{cloud}/image/upload/")
            or not url.endswith(f"/{public_id}.jpg")):
        raise PhotoHostingError("Cloudinary returned an unexpected photo link. Retry saving the listing.")
    return url


def host_listing_photos(
    photo_paths: Sequence[str],
    *,
    upload_directory: Path = LOCAL_UPLOAD_DIRECTORY,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Upload all photos in caller order, caching successes for safe retries."""
    if isinstance(photo_paths, (str, bytes)) or not 3 <= len(photo_paths) <= 8:
        raise PhotoHostingError("Choose 3–8 photos. Depop's CSV supports at most eight; none will be omitted.")
    credentials = _credentials(environ)
    try:
        # Validate the entire batch before sending any photo to Cloudinary.
        paths = [_upload_path(value, upload_directory) for value in photo_paths]
        prepared = [prepare_hosted_photo(path) for path in paths]
        cache_directory = upload_directory / "hosted"
        cache_directory.mkdir(parents=True, exist_ok=True)
        urls = []
        for data in prepared:
            digest = hashlib.sha256(data).hexdigest()
            public_id = f"relist/{digest}"
            cache_key = hashlib.sha256(f"{credentials['cloud_name']}:{public_id}".encode()).hexdigest()
            cache = cache_directory / f"{cache_key}.json"
            if cache.is_file():
                try:
                    response = json.loads(cache.read_text(encoding="utf-8"))
                    urls.append(_checked_response(response, credentials["cloud_name"], public_id))
                    continue
                except (ValueError, TypeError):
                    pass  # Recover a malformed cache via the same non-overwriting ID.
            try:
                response = cloudinary.uploader.upload(
                    BytesIO(data), **credentials, public_id=public_id,
                    resource_type="image", type="upload", overwrite=False,
                    unique_filename=False, use_filename=False, timeout=60,
                )
            except NotAllowed as error:
                raise PhotoHostingError("Cloudinary denied image creation. Check this API key's create/upload permission in Cloudinary Settings → API Keys, update .env if needed, and restart the backend.") from error
            except Exception as error:
                # SDK exceptions may contain request credentials or provider details.
                raise PhotoHostingError("Photo upload failed. Check Cloudinary credentials, quota, and connection, then retry saving. Completed uploads will be reused.") from error
            url = _checked_response(response, credentials["cloud_name"], public_id)
            # Persist only the safe fields, not the full provider response.
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", dir=cache_directory, delete=False, encoding="utf-8") as stream:
                    temporary = Path(stream.name)
                    json.dump({"public_id": public_id, "secure_url": url}, stream)
                temporary.replace(cache)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            urls.append(url)
        return validate_picture_urls(urls)
    except OSError as error:
        raise PhotoHostingError("Local photo files or the upload cache could not be accessed. Check file permissions and retry.") from error
