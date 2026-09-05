"""Terminal-independent orchestration for the resale listing pipeline.

This module deliberately returns plain structured dictionaries.  It is the
boundary shared by the HTTP and CLI adapters without parsing arguments, prompting,
printing, or translating process exit codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import cv2
import numpy as np

from contracts import PipelineResult
from fact_validation import validate_candidate_analysis
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
    proposed_tag_confidence,
    resolve_proposed_roles,
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

VisionRunner = Callable[[Sequence[str], str], VisionCallResult]
PhotoRoleRunner = Callable[[Sequence[str]], VisionCallResult]


@dataclass(frozen=True)
class PipelineService:
    """Run classification stages with injectable hosted-provider boundaries."""

    vision_runner: VisionRunner = analyze_images
    photo_role_runner: PhotoRoleRunner = detect_photo_roles

    def classify_explicit(
        self,
        item_photo_paths: Sequence[str],
        tag_photo_path: str | None,
        *,
        photo_role_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Classify already assigned photos without any UI interaction."""
        item_paths = list(item_photo_paths)
        errors = validate_inputs(item_paths, tag_photo_path)
        if errors:
            result = PipelineResult(status="input_error", image_analysis={}).to_dict()
            result["errors"] = errors
            return result

        assert tag_photo_path is not None
        item_photos = [describe_image(photo) for photo in item_paths]
        tag_photo = describe_image(tag_photo_path)
        warnings: list[dict[str, str]] = []
        for index, item_photo in enumerate(item_photos, start=1):
            warnings.extend(build_quality_warnings(item_photo, f"item_photo_{index}"))
        warnings.extend(build_quality_warnings(tag_photo, "tag_photo"))
        image_analysis = {"item_photos": item_photos, "tag_photo": tag_photo}

        try:
            model_result = self.vision_runner(item_paths, tag_photo_path)
        except VisionConfigurationError as error:
            result = PipelineResult(
                status="configuration_error", image_analysis=image_analysis, warnings=warnings
            ).to_dict()
            result["error"] = {"code": error.code, "message": error.safe_message}
            _add_compatibility_keys(result, item_photos, tag_photo, next_step="configure_api")
            _attach_photo_role_context(result, photo_role_context)
            return result
        except VisionProviderError as error:
            result = PipelineResult(
                status="model_error", image_analysis=image_analysis, warnings=warnings
            ).to_dict()
            result["error"] = {"code": error.code, "message": error.safe_message}
            _add_compatibility_keys(result, item_photos, tag_photo, next_step="retry_model_analysis")
            _attach_photo_role_context(result, photo_role_context)
            return result

        validation = validate_candidate_analysis(model_result.analysis)
        model_warnings = [
            {"code": "model_warning", "message": message}
            for message in model_result.analysis["warnings"]
        ]
        role_warnings = (
            [
                {"code": "photo_role_warning", "message": message}
                for message in photo_role_context["detection"].analysis["warnings"]
            ]
            if photo_role_context is not None
            else []
        )
        combined_warnings = [*warnings, *role_warnings, *model_warnings]
        if validation.validated_facts is None:
            status, next_step = "tag_retake_required", "retake_tag_photo"
        elif validation.needs_review or combined_warnings:
            status, next_step = "review_required", "review_facts"
        else:
            status, next_step = "facts_validated", "review_facts"

        result = PipelineResult(
            status=status,
            image_analysis=image_analysis,
            warnings=combined_warnings,
            model_analysis=model_result.analysis,
            model_metadata=model_result.metadata,
            validated_facts=validation.validated_facts,
        ).to_dict()
        result["review_reasons"] = [dict(issue) for issue in validation.issues]
        if validation.tag_retake_instructions:
            result["tag_retake_instructions"] = list(validation.tag_retake_instructions)
        _add_compatibility_keys(result, item_photos, tag_photo, next_step=next_step)
        _attach_photo_role_context(result, photo_role_context)
        return result

    def start_folder_classification(self, folder_photo_paths: Sequence[str]) -> dict[str, Any]:
        """Detect folder roles and continue with the deterministic best tag match."""
        photos = list(folder_photo_paths)
        errors = validate_folder_photos(photos)
        if errors:
            result = PipelineResult(status="input_error", image_analysis={}).to_dict()
            result["errors"] = errors
            return result
        try:
            detection = self.photo_role_runner(photos)
        except VisionConfigurationError as error:
            return _role_error_result("configuration_error", error, "configure_api")
        except VisionProviderError as error:
            return _role_error_result("model_error", error, "retry_photo_role_detection")

        confidence = proposed_tag_confidence(photos, detection.analysis)
        resolved = resolve_proposed_roles(photos, detection.analysis)
        return self.classify_confirmed_folder(
            photos,
            detection,
            resolved,
            resolution_mode="automatic_best_match",
            tag_confidence=confidence,
        )

    def classify_confirmed_folder(
        self,
        folder_photo_paths: Sequence[str],
        detection: VisionCallResult,
        confirmed_roles: ResolvedPhotoRoles,
        *,
        resolution_mode: str = "user_reviewed_low_confidence",
        tag_confidence: float | None = None,
    ) -> dict[str, Any]:
        """Classify roles already resolved by a caller without repeating detection."""
        photos = list(folder_photo_paths)
        if tag_confidence is None:
            tag_confidence = proposed_tag_confidence(photos, detection.analysis)
        context = _photo_role_context(
            photos,
            detection,
            confirmed=confirmed_roles,
            resolution_mode=resolution_mode,
            tag_confidence=tag_confidence,
        )
        return self.classify_explicit(
            confirmed_roles.item_photos,
            confirmed_roles.tag_photo,
            photo_role_context=context,
        )


def load_image(photo: str) -> np.ndarray | None:
    """Decode a supported image into pixels in OpenCV's BGR color order."""
    return cv2.imread(str(Path(photo)), cv2.IMREAD_COLOR)


def measure_image_dimensions(photo: str) -> dict[str, int]:
    image = load_image(photo)
    if image is None:
        raise ValueError(f"Could not decode image: {photo}")
    height, width = image.shape[:2]
    return {"width": int(width), "height": int(height)}


def measure_blur_score(image: np.ndarray) -> float:
    return round(float(cv2.Laplacian(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()), 2)


def measure_lighting(image: np.ndarray) -> dict[str, float | str]:
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    brightness, contrast = round(float(grayscale.mean()), 2), round(float(grayscale.std()), 2)
    return {
        "brightness_score": brightness,
        "lighting_status": "too_dark" if brightness < DARK_BRIGHTNESS_THRESHOLD else "too_bright" if brightness > BRIGHT_BRIGHTNESS_THRESHOLD else "acceptable",
        "contrast_score": contrast,
        "contrast_status": "acceptable" if contrast >= LOW_CONTRAST_THRESHOLD else "low_contrast",
    }


def measure_possible_glare(image: np.ndarray) -> dict[str, float | str]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    glare_percent = round(float(((hsv[:, :, 2] >= GLARE_BRIGHTNESS_THRESHOLD) & (hsv[:, :, 1] <= GLARE_SATURATION_THRESHOLD)).mean() * 100), 2)
    return {"possible_glare_percent": glare_percent, "glare_status": "possible_glare" if glare_percent >= GLARE_AREA_WARNING_PERCENT else "acceptable"}


def describe_image(photo: str) -> dict[str, str | int | float]:
    image = load_image(photo)
    if image is None:
        raise ValueError(f"Could not decode image: {photo}")
    height, width = image.shape[:2]
    dimensions = {"width": int(width), "height": int(height)}
    blur_score = measure_blur_score(image)
    return {
        "path": str(Path(photo).resolve()), **dimensions,
        "megapixels": round(dimensions["width"] * dimensions["height"] / 1_000_000, 2),
        "resolution_status": "acceptable" if min(dimensions.values()) >= MIN_IMAGE_EDGE else "too_low",
        "blur_score": blur_score,
        "blur_status": "acceptable" if blur_score >= BLUR_SCORE_WARNING_THRESHOLD else "possibly_blurry",
        **measure_lighting(image), **measure_possible_glare(image),
    }


def build_quality_warnings(image_record: Mapping[str, str | int | float], role: str) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    photo = str(image_record["path"])
    def add(code: str, message: str, instruction: str) -> None:
        warnings.append({"code": code, "photo_role": role, "photo": photo, "message": message, "retake_instruction": instruction})
    if image_record["resolution_status"] == "too_low": add("low_resolution", "The photo resolution may be too low for reliable analysis.", "Retake the photo at full camera resolution without cropping or zooming.")
    if image_record["blur_status"] == "possibly_blurry": add("possibly_blurry", "The photo may not contain enough sharp detail.", "Hold the phone steady, tap the item or tag to focus, and retake the photo.")
    if image_record["lighting_status"] == "too_dark": add("too_dark", "The photo appears too dark.", "Retake the photo in brighter, even lighting without using digital zoom.")
    elif image_record["lighting_status"] == "too_bright": add("too_bright", "The photo appears too bright.", "Move away from direct light and retake the photo with softer lighting.")
    if image_record["contrast_status"] == "low_contrast": add("low_contrast", "The photo has low contrast, which may hide details.", "Use more even lighting and place the item against a contrasting background.")
    if image_record["glare_status"] == "possible_glare": add("possible_glare", "A large bright area may be glare.", "Change the camera or light angle so reflections do not cover the item or tag.")
    return warnings


def validate_image_file(photo: str, label: str) -> list[str]:
    path = Path(photo)
    if not path.is_file(): return [f"{label} does not exist or is not a file: {photo}"]
    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        return [f"{label} has an unsupported format: {photo}. Use one of: {', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}"]
    image = load_image(str(path))
    return [] if image is not None and image.size else [f"{label} could not be decoded as an image: {photo}"]


def validate_inputs(item_photos: Sequence[str], tag_photo: str | None) -> list[str]:
    errors = [] if len(item_photos) >= 2 else ["Provide at least two item photos using --item."]
    for photo in item_photos: errors.extend(validate_image_file(photo, "Item photo"))
    if tag_photo is None: errors.append("Provide one separately identified tag photo using --tag.")
    else: errors.extend(validate_image_file(tag_photo, "Tag photo"))
    return errors


def validate_folder_photos(photos: Sequence[str]) -> list[str]:
    errors = [] if len(photos) >= 3 else ["Photo folder must contain at least three supported images (two item photos and one tag photo)."]
    for photo in photos: errors.extend(validate_image_file(photo, "Folder photo"))
    return errors


def discover_photo_folder(folder: str) -> tuple[list[str], list[str]]:
    directory = Path(folder)
    if not directory.is_dir(): return [], [f"Photo folder does not exist or is not a directory: {folder}"]
    photos = sorted((path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS), key=lambda path: (path.name.casefold(), path.name))
    return [str(photo.resolve()) for photo in photos], validate_folder_photos([str(photo) for photo in photos])


def _add_compatibility_keys(result: dict[str, Any], item_photos: Sequence[dict[str, Any]], tag_photo: dict[str, Any], *, next_step: str) -> None:
    result["item_photos"], result["tag_photo"], result["next_step"] = list(item_photos), tag_photo, next_step


def _photo_role_context(photos: Sequence[str], detection: VisionCallResult, *, confirmed: ResolvedPhotoRoles | None = None, resolution_mode: str, tag_confidence: float) -> dict[str, Any]:
    return {"source_folder": str(Path(photos[0]).resolve().parent), "detection": detection, "confirmed": confirmed, "resolution_mode": resolution_mode, "tag_confidence": tag_confidence}


def _attach_photo_role_context(result: dict[str, Any], context: Mapping[str, Any] | None) -> None:
    if context is None: return
    detection = context["detection"]
    stage: dict[str, Any] = {"source_folder": context["source_folder"], "analysis": dict(detection.analysis), "resolution": {"mode": context["resolution_mode"], "tag_confidence": context["tag_confidence"], "review_threshold": ROLE_REVIEW_THRESHOLD}}
    if context["confirmed"] is not None: stage["resolved_roles"] = context["confirmed"].to_dict()
    result["photo_role_detection"], result["photo_role_metadata"] = stage, dict(detection.metadata)


def _role_error_result(status: str, error: VisionConfigurationError | VisionProviderError, next_step: str) -> dict[str, Any]:
    result = PipelineResult(status=status, image_analysis={}).to_dict()
    result["error"] = {"code": error.code, "message": error.safe_message}
    result["photo_role_detection"], result["photo_role_metadata"], result["next_step"] = None, None, next_step
    return result
