"""Command-line entry point for the resale classifier prototype."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import cv2
import numpy as np

from contracts import PipelineResult
from fact_validation import validate_candidate_analysis
from listing_generation import ListingDraft, generate_listing_draft
from openai_vision import (
    VisionCallResult,
    VisionConfigurationError,
    VisionProviderError,
    analyze_images,
)
from photo_role_detection import (
    ROLE_REVIEW_THRESHOLD,
    ResolvedPhotoRoles,
    detect_photo_roles,
    photo_role_review_required,
    proposed_tag_confidence,
    resolve_proposed_roles,
)
from review import (
    ReviewCancelled,
    review_facts_interactively,
    review_listing_draft_interactively,
    review_photo_roles_interactively,
)


SUPPORTED_IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png", ".webp"}
MIN_IMAGE_EDGE = 1000
BLUR_SCORE_WARNING_THRESHOLD = 25.0
DARK_BRIGHTNESS_THRESHOLD = 45.0
BRIGHT_BRIGHTNESS_THRESHOLD = 210.0
LOW_CONTRAST_THRESHOLD = 20.0
GLARE_BRIGHTNESS_THRESHOLD = 245
GLARE_SATURATION_THRESHOLD = 40
GLARE_AREA_WARNING_PERCENT = 5.0
APPROVED_LISTINGS_DIRECTORY = Path(__file__).resolve().parent / "approved_listings"


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
        default=[],
        help="Path to an item photo. Repeat this option for each item photo.",
    )
    parser.add_argument(
        "--tag",
        help="Path to the separately identified tag photo.",
    )
    parser.add_argument(
        "--photo-folder",
        help=(
            "Folder containing at least three unordered photos. Cannot be combined "
            "with --item or --tag."
        ),
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Interactively edit and approve validated facts after classification.",
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


def validate_inputs(item_photos: Sequence[str], tag_photo: str | None) -> list[str]:
    """Return human-readable validation errors, or an empty list when valid."""
    errors: list[str] = []

    if len(item_photos) < 2:
        errors.append("Provide at least two item photos using --item.")

    for photo in item_photos:
        errors.extend(validate_image_file(photo, "Item photo"))

    if tag_photo is None:
        errors.append("Provide one separately identified tag photo using --tag.")
    else:
        errors.extend(validate_image_file(tag_photo, "Tag photo"))

    return errors


def discover_photo_folder(folder: str) -> tuple[list[str], list[str]]:
    """Return supported top-level images in stable order after local validation."""
    directory = Path(folder)
    if not directory.is_dir():
        return [], [f"Photo folder does not exist or is not a directory: {folder}"]

    photos = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )
    errors: list[str] = []
    if len(photos) < 3:
        errors.append(
            "Photo folder must contain at least three supported images "
            "(two item photos and one tag photo)."
        )
    for photo in photos:
        errors.extend(validate_image_file(str(photo), "Folder photo"))
    return [str(photo.resolve()) for photo in photos], errors


def _add_compatibility_keys(
    result: dict[str, Any],
    item_photos: Sequence[dict[str, Any]],
    tag_photo: dict[str, Any],
    *,
    next_step: str,
) -> None:
    """Retain Phase I/II aliases while consumers migrate to stage objects."""
    result["item_photos"] = list(item_photos)
    result["tag_photo"] = tag_photo
    result["next_step"] = next_step


def _add_photo_role_keys(
    result: dict[str, Any],
    *,
    source_folder: str,
    detection: VisionCallResult,
    confirmed: ResolvedPhotoRoles | None = None,
    resolution_mode: str | None = None,
    tag_confidence: float | None = None,
) -> None:
    """Attach the separate role-detection stage without mixing it into facts."""
    role_stage: dict[str, Any] = {
        "source_folder": str(Path(source_folder).resolve()),
        "analysis": dict(detection.analysis),
    }
    if confirmed is not None:
        role_stage["resolved_roles"] = confirmed.to_dict()
    if tag_confidence is not None:
        role_stage["resolution"] = {
            "mode": resolution_mode,
            "tag_confidence": tag_confidence,
            "review_threshold": ROLE_REVIEW_THRESHOLD,
        }
    result["photo_role_detection"] = role_stage
    result["photo_role_metadata"] = dict(detection.metadata)


def _random_output_filename() -> str:
    """Return a hard-to-collide JSON filename for one approved listing."""
    return f"approved-listing-{uuid.uuid4().hex}.json"


def save_approved_result(
    result: dict[str, Any],
    *,
    output_directory: str | Path = APPROVED_LISTINGS_DIRECTORY,
    filename_factory: Callable[[], str] = _random_output_filename,
) -> Path:
    """Save approved JSON under a unique name without overwriting any file."""
    directory = Path(output_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)

    for _ in range(10):
        output_path = directory / filename_factory()
        result["saved_to"] = str(output_path)
        try:
            with output_path.open("x", encoding="utf-8") as output_file:
                json.dump(result, output_file, indent=2)
                output_file.write("\n")
            return output_path
        except FileExistsError:
            result.pop("saved_to", None)

    raise OSError("Could not allocate a unique approved-listing filename.")


def main(
    arguments: Sequence[str] | None = None,
    *,
    vision_runner: Callable[[Sequence[str], str], VisionCallResult] = analyze_images,
    review_runner: Callable[[Mapping[str, Any]], Mapping[str, str | None]] = review_facts_interactively,
    listing_generator: Callable[[Mapping[str, Any]], ListingDraft] = generate_listing_draft,
    listing_review_runner: Callable[[Mapping[str, str]], Mapping[str, str]] = review_listing_draft_interactively,
    photo_role_runner: Callable[[Sequence[str]], VisionCallResult] = detect_photo_roles,
    photo_role_review_runner: Callable[
        [Sequence[str], Mapping[str, Any]], ResolvedPhotoRoles
    ] = review_photo_roles_interactively,
    output_directory: str | Path = APPROVED_LISTINGS_DIRECTORY,
    filename_factory: Callable[[], str] = _random_output_filename,
) -> int:
    """Validate photos, call hosted vision, validate facts, and print JSON."""
    args = build_parser().parse_args(arguments)
    folder_photos: list[str] = []
    errors: list[str] = []
    if args.photo_folder:
        if args.item or args.tag:
            errors.append("Use --photo-folder by itself instead of --item or --tag.")
        else:
            folder_photos, folder_errors = discover_photo_folder(args.photo_folder)
            errors.extend(folder_errors)
    else:
        errors.extend(validate_inputs(args.item, args.tag))

    if errors:
        result = PipelineResult(
            status="input_error",
            image_analysis={},
        ).to_dict()
        result["errors"] = errors
        print(json.dumps(result, indent=2))
        return 1

    photo_role_result: VisionCallResult | None = None
    confirmed_photo_roles: ResolvedPhotoRoles | None = None
    photo_role_resolution_mode: str | None = None
    tag_role_confidence: float | None = None
    item_photo_paths = list(args.item)
    tag_photo_path = args.tag
    if args.photo_folder:
        try:
            photo_role_result = photo_role_runner(folder_photos)
        except VisionConfigurationError as error:
            result = PipelineResult(
                status="configuration_error",
                image_analysis={},
            ).to_dict()
            result["error"] = {"code": error.code, "message": error.safe_message}
            result["photo_role_detection"] = None
            result["photo_role_metadata"] = None
            result["next_step"] = "configure_api"
            print(json.dumps(result, indent=2))
            return 2
        except VisionProviderError as error:
            result = PipelineResult(
                status="model_error",
                image_analysis={},
            ).to_dict()
            result["error"] = {"code": error.code, "message": error.safe_message}
            result["photo_role_detection"] = None
            result["photo_role_metadata"] = None
            result["next_step"] = "retry_photo_role_detection"
            print(json.dumps(result, indent=2))
            return 3

        tag_role_confidence = proposed_tag_confidence(
            folder_photos,
            photo_role_result.analysis,
        )
        if photo_role_review_required(
            folder_photos,
            photo_role_result.analysis,
        ):
            try:
                confirmed_photo_roles = photo_role_review_runner(
                    folder_photos,
                    photo_role_result.analysis,
                )
                photo_role_resolution_mode = "user_reviewed_low_confidence"
            except ReviewCancelled:
                result = PipelineResult(
                    status="review_cancelled",
                    image_analysis={},
                ).to_dict()
                result["review_stage"] = "photo_roles"
                _add_photo_role_keys(
                    result,
                    source_folder=args.photo_folder,
                    detection=photo_role_result,
                    resolution_mode="review_cancelled_low_confidence",
                    tag_confidence=tag_role_confidence,
                )
                result["next_step"] = "review_photo_roles"
                print(json.dumps(result, indent=2))
                return 0
        else:
            confirmed_photo_roles = resolve_proposed_roles(
                folder_photos,
                photo_role_result.analysis,
            )
            photo_role_resolution_mode = "automatic_high_confidence"

        item_photo_paths = list(confirmed_photo_roles.item_photos)
        tag_photo_path = confirmed_photo_roles.tag_photo

    # Folder photos were already checked before role detection. This repeats the
    # universal input boundary after a user correction and protects injected UI callers.
    resolved_errors = validate_inputs(item_photo_paths, tag_photo_path)
    if resolved_errors:
        result = PipelineResult(
            status="input_error",
            image_analysis={},
        ).to_dict()
        result["errors"] = resolved_errors
        print(json.dumps(result, indent=2))
        return 1

    item_photos = [describe_image(photo) for photo in item_photo_paths]
    tag_photo = describe_image(tag_photo_path)
    warnings: list[dict[str, str]] = []

    for index, item_photo in enumerate(item_photos, start=1):
        warnings.extend(build_quality_warnings(item_photo, f"item_photo_{index}"))
    warnings.extend(build_quality_warnings(tag_photo, "tag_photo"))

    image_analysis = {
        "item_photos": item_photos,
        "tag_photo": tag_photo,
    }
    try:
        model_result = vision_runner(item_photo_paths, tag_photo_path)
    except VisionConfigurationError as error:
        result = PipelineResult(
            status="configuration_error",
            image_analysis=image_analysis,
            warnings=warnings,
        ).to_dict()
        result["error"] = {"code": error.code, "message": error.safe_message}
        _add_compatibility_keys(
            result,
            item_photos,
            tag_photo,
            next_step="configure_api",
        )
        if photo_role_result is not None and confirmed_photo_roles is not None:
            _add_photo_role_keys(
                result,
                source_folder=args.photo_folder,
                detection=photo_role_result,
                confirmed=confirmed_photo_roles,
                resolution_mode=photo_role_resolution_mode,
                tag_confidence=tag_role_confidence,
            )
        print(json.dumps(result, indent=2))
        return 2
    except VisionProviderError as error:
        result = PipelineResult(
            status="model_error",
            image_analysis=image_analysis,
            warnings=warnings,
        ).to_dict()
        result["error"] = {"code": error.code, "message": error.safe_message}
        _add_compatibility_keys(
            result,
            item_photos,
            tag_photo,
            next_step="retry_model_analysis",
        )
        if photo_role_result is not None and confirmed_photo_roles is not None:
            _add_photo_role_keys(
                result,
                source_folder=args.photo_folder,
                detection=photo_role_result,
                confirmed=confirmed_photo_roles,
                resolution_mode=photo_role_resolution_mode,
                tag_confidence=tag_role_confidence,
            )
        print(json.dumps(result, indent=2))
        return 3

    validation = validate_candidate_analysis(model_result.analysis)
    model_warnings = [
        {"code": "model_warning", "message": message}
        for message in model_result.analysis["warnings"]
    ]
    role_warnings = (
        [
            {"code": "photo_role_warning", "message": message}
            for message in photo_role_result.analysis["warnings"]
        ]
        if photo_role_result is not None
        else []
    )
    combined_warnings = [*warnings, *role_warnings, *model_warnings]

    approved_facts: Mapping[str, str | None] | None = None
    listing_draft: Mapping[str, str] | None = None
    review_cancelled = False
    if args.review and validation.validated_facts is not None:
        try:
            approved_facts = review_runner(validation.validated_facts.to_dict())
            generated_draft = listing_generator(approved_facts).to_dict()
            listing_draft = listing_review_runner(generated_draft)
        except ReviewCancelled:
            review_cancelled = True

    if listing_draft is not None:
        status = "listing_approved"
        next_step = "export_later"
    elif review_cancelled:
        status = "review_cancelled"
        next_step = "review_facts"
    elif validation.validated_facts is None:
        status = "tag_retake_required"
        next_step = "retake_tag_photo"
    elif validation.needs_review or combined_warnings:
        status = "review_required"
        next_step = "review_facts"
    else:
        status = "facts_validated"
        next_step = "review_facts"

    result = PipelineResult(
        status=status,
        image_analysis=image_analysis,
        warnings=combined_warnings,
        model_analysis=model_result.analysis,
        model_metadata=model_result.metadata,
        validated_facts=validation.validated_facts,
        listing_draft=listing_draft,
    ).to_dict()
    result["review_reasons"] = [dict(issue) for issue in validation.issues]
    if approved_facts is not None:
        result["approved_facts"] = dict(approved_facts)
        result["review_reasons"] = []
    if validation.tag_retake_instructions:
        result["tag_retake_instructions"] = list(
            validation.tag_retake_instructions
        )
    _add_compatibility_keys(
        result,
        item_photos,
        tag_photo,
        next_step=next_step,
    )
    if photo_role_result is not None and confirmed_photo_roles is not None:
        _add_photo_role_keys(
            result,
            source_folder=args.photo_folder,
            detection=photo_role_result,
            confirmed=confirmed_photo_roles,
            resolution_mode=photo_role_resolution_mode,
            tag_confidence=tag_role_confidence,
        )
    if status == "listing_approved":
        try:
            save_approved_result(
                result,
                output_directory=output_directory,
                filename_factory=filename_factory,
            )
        except OSError:
            result.pop("saved_to", None)
            result["save_error"] = {
                "code": "output_unavailable",
                "message": "The approved listing could not be saved automatically.",
            }
            print(json.dumps(result, indent=2))
            return 5
    print(json.dumps(result, indent=2))
    return 4 if status == "tag_retake_required" else 0


if __name__ == "__main__":
    raise SystemExit(main())
