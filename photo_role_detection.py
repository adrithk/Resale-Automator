"""Detect photo roles before the main garment-analysis request."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from openai_vision import (
    DEFAULT_MODEL,
    REASONING_EFFORT,
    VisionCallResult,
    VisionResponseError,
    encode_image_data_url,
    run_structured_vision_call,
)


ROLE_SCHEMA_VERSION = 1
PHOTO_DETAIL = "high"
ROLE_REVIEW_THRESHOLD = 0.60
VISUAL_ROLES = (
    "front_view",
    "back_view",
    "item_detail",
    "tag_photo",
    "uncertain",
)
ITEM_ROLE_ORDER = {
    "front_view": 0,
    "back_view": 1,
    "item_detail": 2,
    "uncertain": 3,
    "tag_photo": 4,
}

ROLE_DETECTION_INSTRUCTIONS = """Identify the visual role of every supplied photo.
The adjacent photo IDs are opaque identifiers, not role hints, and filenames
must not affect your decision. Exactly one photo should normally be the close-up
brand, size, or care tag; garment photos should be labeled front_view,
back_view, or item_detail. Use uncertain only when the visual role genuinely
cannot be determined. Estimate tag_likelihood independently for every image so
Python can still propose one tag when role labels are ambiguous. Do not extract
garment facts, write listing text, infer from filenames, or omit any photo.
"""


@dataclass(frozen=True)
class ResolvedPhotoRoles:
    """Confirmed paths in the format required by the existing classifier."""

    item_photos: tuple[str, ...]
    tag_photo: str

    def __post_init__(self) -> None:
        all_photos = (*self.item_photos, self.tag_photo)
        if len(self.item_photos) < 2:
            raise ValueError("At least two item photos are required.")
        if not all(isinstance(photo, str) and photo for photo in all_photos):
            raise ValueError("Resolved photo paths must be non-empty strings.")
        if len(set(all_photos)) != len(all_photos):
            raise ValueError("Each resolved photo may have only one role.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_photos": list(self.item_photos),
            "tag_photo": self.tag_photo,
        }


def _object_schema(properties: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(properties),
        "additionalProperties": False,
    }


def photo_ids(photo_count: int) -> tuple[str, ...]:
    if photo_count < 3:
        raise ValueError("Photo-role detection requires at least three photos.")
    return tuple(f"photo_{index}" for index in range(1, photo_count + 1))


def build_photo_role_schema(ids: Sequence[str]) -> dict[str, Any]:
    """Build a strict role schema tied to the exact neutral IDs sent."""
    if len(ids) < 3 or len(set(ids)) != len(ids):
        raise ValueError("At least three unique photo IDs are required.")
    assignment = _object_schema(
        {
            "photo_id": {"type": "string", "enum": list(ids)},
            "visual_role": {"type": "string", "enum": list(VISUAL_ROLES)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "tag_likelihood": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {"type": "string"},
        }
    )
    return _object_schema(
        {
            "schema_version": {"type": "integer", "const": ROLE_SCHEMA_VERSION},
            "assignments": {"type": "array", "items": assignment},
            "warnings": {"type": "array", "items": {"type": "string"}},
        }
    )


def build_photo_role_request(photos: Sequence[str | Path]) -> dict[str, Any]:
    """Construct a neutral, filename-independent role-detection request."""
    ids = photo_ids(len(photos))
    content: list[dict[str, str]] = [
        {
            "type": "input_text",
            "text": "Classify every image by its visual role using its adjacent photo ID.",
        }
    ]
    for photo_id, photo in zip(ids, photos):
        content.extend(
            [
                {"type": "input_text", "text": f"Photo ID: {photo_id}"},
                {
                    "type": "input_image",
                    "image_url": encode_image_data_url(photo),
                    "detail": PHOTO_DETAIL,
                },
            ]
        )
    return {
        "model": DEFAULT_MODEL,
        "instructions": ROLE_DETECTION_INSTRUCTIONS,
        "input": [{"role": "user", "content": content}],
        "reasoning": {"effort": REASONING_EFFORT},
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "resale_photo_role_detection",
                "strict": True,
                "schema": build_photo_role_schema(ids),
            }
        },
    }


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _number_between_zero_and_one(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and 0 <= value <= 1
    )


def validate_photo_role_analysis(
    analysis: Any,
    *,
    ids: Sequence[str],
) -> dict[str, Any]:
    """Reject malformed, duplicate, missing, or invented photo assignments."""
    if not isinstance(analysis, Mapping) or set(analysis) != {
        "schema_version",
        "assignments",
        "warnings",
    }:
        raise VisionResponseError(
            "invalid_role_schema",
            "Photo-role output has missing or unexpected fields.",
        )
    if analysis["schema_version"] != ROLE_SCHEMA_VERSION:
        raise VisionResponseError(
            "invalid_role_schema",
            "Photo-role output uses an unsupported schema version.",
        )
    assignments = analysis["assignments"]
    if not isinstance(assignments, list) or len(assignments) != len(ids):
        raise VisionResponseError(
            "invalid_role_schema",
            "Photo-role output must assign every supplied photo exactly once.",
        )

    seen: set[str] = set()
    expected_keys = {
        "photo_id",
        "visual_role",
        "confidence",
        "tag_likelihood",
        "evidence",
    }
    for assignment in assignments:
        if not isinstance(assignment, Mapping) or set(assignment) != expected_keys:
            raise VisionResponseError(
                "invalid_role_schema",
                "A photo-role assignment has missing or unexpected fields.",
            )
        photo_id = assignment["photo_id"]
        if photo_id not in ids or photo_id in seen:
            raise VisionResponseError(
                "invalid_role_schema",
                "Photo-role output contains a duplicate or unknown photo ID.",
            )
        seen.add(photo_id)
        if assignment["visual_role"] not in VISUAL_ROLES:
            raise VisionResponseError(
                "invalid_role_schema",
                "Photo-role output contains an unsupported visual role.",
            )
        if not _number_between_zero_and_one(assignment["confidence"]):
            raise VisionResponseError(
                "invalid_role_schema",
                "Photo-role confidence must be from 0 through 1.",
            )
        if not _number_between_zero_and_one(assignment["tag_likelihood"]):
            raise VisionResponseError(
                "invalid_role_schema",
                "Tag likelihood must be from 0 through 1.",
            )
        if not isinstance(assignment["evidence"], str):
            raise VisionResponseError(
                "invalid_role_schema",
                "Photo-role evidence must be text.",
            )

    if seen != set(ids):
        raise VisionResponseError(
            "invalid_role_schema",
            "Photo-role output omitted a supplied photo.",
        )
    warnings = analysis["warnings"]
    if not isinstance(warnings, list) or not all(
        isinstance(warning, str) for warning in warnings
    ):
        raise VisionResponseError(
            "invalid_role_schema",
            "Photo-role warnings must be a string list.",
        )
    return dict(analysis)


def parse_photo_role_response(
    response: Any,
    *,
    ids: Sequence[str],
) -> dict[str, Any]:
    """Parse and defensively validate a strict photo-role response."""
    if _get(response, "status") != "completed":
        raise VisionResponseError(
            "incomplete_response",
            "The photo-role response did not complete.",
        )
    for output_item in _get(response, "output", ()) or ():
        for content_item in _get(output_item, "content", ()) or ():
            if _get(content_item, "type") == "refusal":
                raise VisionResponseError(
                    "model_refusal",
                    "The model declined photo-role detection.",
                )
    output_text = _get(response, "output_text")
    if not isinstance(output_text, str) or not output_text.strip():
        raise VisionResponseError(
            "malformed_response",
            "The model returned no structured photo-role output.",
        )
    try:
        analysis = json.loads(output_text)
    except json.JSONDecodeError as error:
        raise VisionResponseError(
            "malformed_response",
            "The model returned malformed photo-role output.",
        ) from error
    return validate_photo_role_analysis(analysis, ids=ids)


def resolve_proposed_roles(
    photos: Sequence[str | Path],
    analysis: Mapping[str, Any],
) -> ResolvedPhotoRoles:
    """Choose one proposed tag and deterministically order remaining item photos."""
    ids = photo_ids(len(photos))
    validated = validate_photo_role_analysis(analysis, ids=ids)
    by_id = {assignment["photo_id"]: assignment for assignment in validated["assignments"]}
    tag_id = max(
        ids,
        key=lambda photo_id: (
            by_id[photo_id]["tag_likelihood"],
            by_id[photo_id]["visual_role"] == "tag_photo",
            by_id[photo_id]["confidence"],
            -ids.index(photo_id),
        ),
    )

    return resolve_roles_with_tag_index(
        photos,
        analysis,
        tag_index=ids.index(tag_id),
    )


def proposed_tag_confidence(
    photos: Sequence[str | Path],
    analysis: Mapping[str, Any],
) -> float:
    """Return conservative confidence in the automatically selected tag photo."""
    ids = photo_ids(len(photos))
    validated = validate_photo_role_analysis(analysis, ids=ids)
    proposed = resolve_proposed_roles(photos, validated)
    proposed_path = Path(proposed.tag_photo)
    assignments = {
        assignment["photo_id"]: assignment
        for assignment in validated["assignments"]
    }
    for photo_id, photo in zip(ids, photos):
        if Path(photo).resolve() == proposed_path:
            assignment = assignments[photo_id]
            return min(
                float(assignment["confidence"]),
                float(assignment["tag_likelihood"]),
            )
    raise AssertionError("The proposed tag did not match a supplied photo.")


def photo_role_review_required(
    photos: Sequence[str | Path],
    analysis: Mapping[str, Any],
    *,
    threshold: float = ROLE_REVIEW_THRESHOLD,
) -> bool:
    """Require human role review only below the configured confidence threshold."""
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError("Photo-role review threshold must be numeric.")
    if not 0 <= threshold <= 1:
        raise ValueError("Photo-role review threshold must be from 0 through 1.")
    return proposed_tag_confidence(photos, analysis) < threshold


def resolve_roles_with_tag_index(
    photos: Sequence[str | Path],
    analysis: Mapping[str, Any],
    *,
    tag_index: int,
) -> ResolvedPhotoRoles:
    """Apply a confirmed zero-based tag selection and order the other photos."""
    ids = photo_ids(len(photos))
    if isinstance(tag_index, bool) or not 0 <= tag_index < len(ids):
        raise ValueError("The selected tag-photo index is out of range.")
    validated = validate_photo_role_analysis(analysis, ids=ids)
    by_id = {assignment["photo_id"]: assignment for assignment in validated["assignments"]}
    tag_id = ids[tag_index]

    paths_by_id = {
        photo_id: str(Path(photo).resolve())
        for photo_id, photo in zip(ids, photos)
    }
    item_ids = [photo_id for photo_id in ids if photo_id != tag_id]
    item_ids.sort(
        key=lambda photo_id: (
            ITEM_ROLE_ORDER[by_id[photo_id]["visual_role"]],
            ids.index(photo_id),
        )
    )
    return ResolvedPhotoRoles(
        item_photos=tuple(paths_by_id[photo_id] for photo_id in item_ids),
        tag_photo=paths_by_id[tag_id],
    )


def detect_photo_roles(
    photos: Sequence[str | Path],
    *,
    client: Any | None = None,
    environ: Mapping[str, str] | None = None,
    clock: Any = time.perf_counter,
    sleep: Any = time.sleep,
) -> VisionCallResult:
    """Call the hosted model once to classify neutral photo IDs by role."""
    ids = photo_ids(len(photos))
    request = build_photo_role_request(photos)
    return run_structured_vision_call(
        request,
        lambda response: parse_photo_role_response(response, ids=ids),
        client=client,
        environ=environ,
        clock=clock,
        sleep=sleep,
    )
