"""Command-line entry point for the resale classifier prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


SUPPORTED_IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png", ".webp"}
MIN_IMAGE_EDGE = 1000
BLUR_SCORE_WARNING_THRESHOLD = 25.0
DARK_BRIGHTNESS_THRESHOLD = 45.0
BRIGHT_BRIGHTNESS_THRESHOLD = 210.0
LOW_CONTRAST_THRESHOLD = 20.0
GLARE_BRIGHTNESS_THRESHOLD = 245
GLARE_SATURATION_THRESHOLD = 40
GLARE_AREA_WARNING_PERCENT = 5.0


def load_image(photo: str) -> np.ndarray | None:
    """Decode a supported image into pixels in OpenCV's BGR color order."""
    return cv2.imread(str(Path(photo)), cv2.IMREAD_COLOR)


def measure_image_dimensions(photo: str) -> dict[str, int]:
    """Return the width and height of a decodable image."""
    image = load_image(photo)

    if image is None:
        raise ValueError(f"Could not decode image: {photo}")

    height, width = image.shape[:2]

    return {
        "width": int(width),
        "height": int(height),
    }


def measure_blur_score(image: np.ndarray) -> float:
    """Measure edge sharpness; lower scores suggest a blurrier image."""
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    score = cv2.Laplacian(grayscale, cv2.CV_64F).var()
    return round(float(score), 2)


def measure_lighting(image: np.ndarray) -> dict[str, float | str]:
    """Measure average brightness and contrast on a grayscale 0-255 scale."""
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    brightness = round(float(grayscale.mean()), 2)
    contrast = round(float(grayscale.std()), 2)

    if brightness < DARK_BRIGHTNESS_THRESHOLD:
        lighting_status = "too_dark"
    elif brightness > BRIGHT_BRIGHTNESS_THRESHOLD:
        lighting_status = "too_bright"
    else:
        lighting_status = "acceptable"

    return {
        "brightness_score": brightness,
        "lighting_status": lighting_status,
        "contrast_score": contrast,
        "contrast_status": (
            "acceptable" if contrast >= LOW_CONTRAST_THRESHOLD else "low_contrast"
        ),
    }


def measure_possible_glare(image: np.ndarray) -> dict[str, float | str]:
    """Estimate the percentage of very bright, low-saturation pixels."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    brightness = hsv[:, :, 2]
    glare_mask = (
        (brightness >= GLARE_BRIGHTNESS_THRESHOLD)
        & (saturation <= GLARE_SATURATION_THRESHOLD)
    )
    glare_percent = round(float(glare_mask.mean() * 100), 2)

    return {
        "possible_glare_percent": glare_percent,
        "glare_status": (
            "possible_glare"
            if glare_percent >= GLARE_AREA_WARNING_PERCENT
            else "acceptable"
        ),
    }


def describe_image(photo: str) -> dict[str, str | int | float]:
    """Return the path and basic resolution analysis for one validated image."""
    image = load_image(photo)
    if image is None:
        raise ValueError(f"Could not decode image: {photo}")

    height, width = image.shape[:2]
    dimensions = {"width": int(width), "height": int(height)}
    shortest_edge = min(dimensions["width"], dimensions["height"])
    blur_score = measure_blur_score(image)
    lighting = measure_lighting(image)
    glare = measure_possible_glare(image)

    return {
        "path": str(Path(photo).resolve()),
        **dimensions,
        "megapixels": round(
            dimensions["width"] * dimensions["height"] / 1_000_000,
            2,
        ),
        "resolution_status": (
            "acceptable" if shortest_edge >= MIN_IMAGE_EDGE else "too_low"
        ),
        "blur_score": blur_score,
        "blur_status": (
            "acceptable"
            if blur_score >= BLUR_SCORE_WARNING_THRESHOLD
            else "possibly_blurry"
        ),
        **lighting,
        **glare,
    }


def build_quality_warnings(
    image_record: dict[str, str | int | float],
    role: str,
) -> list[dict[str, str]]:
    """Turn non-acceptable measurements into useful retake guidance."""
    warnings: list[dict[str, str]] = []
    photo = str(image_record["path"])

    def add_warning(code: str, message: str, retake_instruction: str) -> None:
        warnings.append(
            {
                "code": code,
                "photo_role": role,
                "photo": photo,
                "message": message,
                "retake_instruction": retake_instruction,
            }
        )

    if image_record["resolution_status"] == "too_low":
        add_warning(
            "low_resolution",
            "The photo resolution may be too low for reliable analysis.",
            "Retake the photo at full camera resolution without cropping or zooming.",
        )

    if image_record["blur_status"] == "possibly_blurry":
        add_warning(
            "possibly_blurry",
            "The photo may not contain enough sharp detail.",
            "Hold the phone steady, tap the item or tag to focus, and retake the photo.",
        )

    if image_record["lighting_status"] == "too_dark":
        add_warning(
            "too_dark",
            "The photo appears too dark.",
            "Retake the photo in brighter, even lighting without using digital zoom.",
        )
    elif image_record["lighting_status"] == "too_bright":
        add_warning(
            "too_bright",
            "The photo appears too bright.",
            "Move away from direct light and retake the photo with softer lighting.",
        )

    if image_record["contrast_status"] == "low_contrast":
        add_warning(
            "low_contrast",
            "The photo has low contrast, which may hide details.",
            "Use more even lighting and place the item against a contrasting background.",
        )

    if image_record["glare_status"] == "possible_glare":
        add_warning(
            "possible_glare",
            "A large bright area may be glare.",
            "Change the camera or light angle so reflections do not cover the item or tag.",
        )

    return warnings


def build_parser() -> argparse.ArgumentParser:
    """Describe the command-line inputs accepted by the prototype."""
    parser = argparse.ArgumentParser(
        description="Validate clothing and tag photos for classification."
    )
    parser.add_argument(
        "--item",
        action="append",
        required=True,
        help="Path to an item photo. Repeat this option for each item photo.",
    )
    parser.add_argument(
        "--tag",
        required=True,
        help="Path to the separately identified tag photo.",
    )
    return parser


def validate_image_file(photo: str, label: str) -> list[str]:
    """Check that a path points to a supported, decodable image file."""
    path = Path(photo)

    if not path.is_file():
        return [f"{label} does not exist or is not a file: {photo}"]

    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS))
        return [f"{label} has an unsupported format: {photo}. Use one of: {supported}"]

    image = load_image(str(path))
    if image is None or image.size == 0:
        return [f"{label} could not be decoded as an image: {photo}"]

    return []


def validate_inputs(item_photos: Sequence[str], tag_photo: str) -> list[str]:
    """Return human-readable validation errors, or an empty list when valid."""
    errors: list[str] = []

    if len(item_photos) < 2:
        errors.append("Provide at least two item photos using --item.")

    for photo in item_photos:
        errors.extend(validate_image_file(photo, "Item photo"))

    errors.extend(validate_image_file(tag_photo, "Tag photo"))

    return errors


def main(arguments: Sequence[str] | None = None) -> int:
    """Validate command-line inputs and print a structured JSON result."""
    args = build_parser().parse_args(arguments)
    errors = validate_inputs(args.item, args.tag)

    if errors:
        result = {
            "status": "input_error",
            "errors": errors,
        }
        print(json.dumps(result, indent=2))
        return 1

    item_photos = [describe_image(photo) for photo in args.item]
    tag_photo = describe_image(args.tag)
    warnings: list[dict[str, str]] = []

    for index, item_photo in enumerate(item_photos, start=1):
        warnings.extend(build_quality_warnings(item_photo, f"item_photo_{index}"))
    warnings.extend(build_quality_warnings(tag_photo, "tag_photo"))

    result = {
        "status": (
            "quality_review_needed" if warnings else "quality_checks_complete"
        ),
        "item_photos": item_photos,
        "tag_photo": tag_photo,
        "warnings": warnings,
        "next_step": "structured_data_contract",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
