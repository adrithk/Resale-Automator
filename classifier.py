"""Command-line adapter for the terminal-independent resale pipeline service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from listing_generation import ListingDraft, generate_listing_draft
from local_persistence import (
    APPROVED_LISTINGS_DIRECTORY,
    random_output_filename,
    save_approved_result,
)
from openai_vision import VisionCallResult, analyze_images
from photo_role_detection import ResolvedPhotoRoles, detect_photo_roles
from pipeline_service import (
    BLUR_SCORE_WARNING_THRESHOLD,
    BRIGHT_BRIGHTNESS_THRESHOLD,
    DARK_BRIGHTNESS_THRESHOLD,
    GLARE_AREA_WARNING_PERCENT,
    GLARE_BRIGHTNESS_THRESHOLD,
    GLARE_SATURATION_THRESHOLD,
    LOW_CONTRAST_THRESHOLD,
    MIN_IMAGE_EDGE,
    SUPPORTED_IMAGE_EXTENSIONS,
    PipelineService,
    build_quality_warnings,
    describe_image,
    discover_photo_folder,
    load_image,
    measure_blur_score,
    measure_image_dimensions,
    measure_lighting,
    measure_possible_glare,
    validate_image_file,
    validate_inputs,
)
from review import (
    ReviewCancelled,
    review_facts_interactively,
    review_listing_draft_interactively,
    review_photo_roles_interactively,
)


def build_parser() -> argparse.ArgumentParser:
    """Describe the command-line inputs accepted by the prototype."""
    parser = argparse.ArgumentParser(
        description="Validate clothing and tag photos for classification."
    )
    parser.add_argument("--item", action="append", default=[], help="Path to an item photo. Repeat this option for each item photo.")
    parser.add_argument("--tag", help="Path to the separately identified tag photo.")
    parser.add_argument("--photo-folder", help="Folder containing at least three unordered photos. Cannot be combined with --item or --tag.")
    parser.add_argument("--review", action="store_true", help="Interactively edit and approve validated facts after classification.")
    return parser


def _run_terminal_review(result: dict[str, Any], *, review_runner: Callable[[Mapping[str, Any]], Mapping[str, str | None]], listing_generator: Callable[[Mapping[str, Any]], ListingDraft], listing_review_runner: Callable[[Mapping[str, str]], Mapping[str, str]]) -> dict[str, Any]:
    """Apply terminal-only fact and listing-text reviews after classification."""
    if result.get("validated_facts") is None:
        return result
    try:
        approved_facts = review_runner(result["validated_facts"])
        listing_draft = listing_review_runner(listing_generator(approved_facts).to_dict())
    except ReviewCancelled:
        result["status"], result["next_step"] = "review_cancelled", "review_facts"
        return result
    result["status"], result["next_step"] = "listing_approved", "export_later"
    result["approved_facts"], result["listing_draft"], result["review_reasons"] = dict(approved_facts), dict(listing_draft), []
    return result


def _exit_code(result: Mapping[str, Any]) -> int:
    return {"input_error": 1, "configuration_error": 2, "model_error": 3, "tag_retake_required": 4}.get(result["status"], 0)


def main(arguments: Sequence[str] | None = None, *, vision_runner: Callable[[Sequence[str], str], VisionCallResult] = analyze_images, review_runner: Callable[[Mapping[str, Any]], Mapping[str, str | None]] = review_facts_interactively, listing_generator: Callable[[Mapping[str, Any]], ListingDraft] = generate_listing_draft, listing_review_runner: Callable[[Mapping[str, str]], Mapping[str, str]] = review_listing_draft_interactively, photo_role_runner: Callable[[Sequence[str]], VisionCallResult] = detect_photo_roles, photo_role_review_runner: Callable[[Sequence[str], Mapping[str, Any]], ResolvedPhotoRoles] = review_photo_roles_interactively, output_directory: str | Path = APPROVED_LISTINGS_DIRECTORY, filename_factory: Callable[[], str] = random_output_filename) -> int:
    """Parse CLI arguments, delegate pipeline work, and print exactly one result."""
    args = build_parser().parse_args(arguments)
    service = PipelineService(vision_runner=vision_runner, photo_role_runner=photo_role_runner)
    if args.photo_folder and (args.item or args.tag):
        result = service.classify_explicit([], None)
        result["errors"] = ["Use --photo-folder by itself instead of --item or --tag."]
    elif args.photo_folder:
        folder_photos, errors = discover_photo_folder(args.photo_folder)
        if errors:
            result = service.classify_explicit([], None)
            result["errors"] = errors
        else:
            result = service.start_folder_classification(folder_photos)
    else:
        result = service.classify_explicit(args.item, args.tag)
    if args.review and result["status"] in {"review_required", "facts_validated"}:
        result = _run_terminal_review(result, review_runner=review_runner, listing_generator=listing_generator, listing_review_runner=listing_review_runner)
    if result["status"] == "listing_approved":
        try:
            save_approved_result(result, output_directory=output_directory, filename_factory=filename_factory)
        except OSError:
            result.pop("saved_to", None)
            result["save_error"] = {"code": "output_unavailable", "message": "The approved listing could not be saved automatically."}
            print(json.dumps(result, indent=2))
            return 5
    print(json.dumps(result, indent=2))
    return _exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
