"""Interactive terminal review for validated classifier facts."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence, TextIO

from listing_generation import validate_listing_draft
from photo_role_detection import (
    ResolvedPhotoRoles,
    photo_ids,
    resolve_proposed_roles,
    resolve_roles_with_tag_index,
    validate_photo_role_analysis,
)
from review_validation import FINAL_FACT_NAMES, validate_final_edits


FIELD_LABELS = {
    "category": "Category",
    "item_type": "Item Type",
    "brand": "Brand",
    "condition": "Condition",
    "size": "Size",
    "inseam": "Inseam for later description",
    "primary_color": "Primary Color",
    "secondary_color": "Secondary Color",
    "source_1": "Source 1",
    "source_2": "Source 2",
    "age": "Age",
    "style_1": "Style 1",
    "style_2": "Style 2",
    "style_3": "Style 3",
}
DRAFT_LABELS = {
    "draft_title": "Draft Title",
    "description": "Description",
}
PHOTO_ROLE_LABELS = {
    "front_view": "front view",
    "back_view": "back view",
    "item_detail": "item detail",
    "tag_photo": "tag photo",
    "uncertain": "uncertain",
}


class ReviewCancelled(RuntimeError):
    """The user exited terminal review without approving facts."""


def review_photo_roles_interactively(
    photos: Sequence[str],
    analysis: Mapping[str, Any],
    *,
    input_fn: Callable[[str], str] | None = None,
    output: TextIO | None = None,
) -> ResolvedPhotoRoles:
    """Show model roles and require confirmation of the selected tag photo."""
    reader = input_fn or _terminal_input
    stream = output or sys.stderr
    ids = photo_ids(len(photos))
    validated = validate_photo_role_analysis(analysis, ids=ids)
    proposed = resolve_proposed_roles(photos, validated)
    assignments = {
        assignment["photo_id"]: assignment
        for assignment in validated["assignments"]
    }

    print("Detected photo roles:", file=stream)
    for index, (photo_id, photo) in enumerate(zip(ids, photos), start=1):
        assignment = assignments[photo_id]
        role = PHOTO_ROLE_LABELS[assignment["visual_role"]]
        confidence = round(assignment["confidence"] * 100)
        marker = " (selected tag)" if str(Path(photo).resolve()) == proposed.tag_photo else ""
        print(
            f"{index}. {Path(photo).name}: {role}, {confidence}% confidence{marker}",
            file=stream,
        )

    while True:
        response = reader("Use these detected roles? [Y/n/q]: ").strip().casefold()
        if response in {"", "y", "yes"}:
            return proposed
        if response in {"q", "quit"}:
            raise ReviewCancelled("Photo-role review cancelled.")
        if response not in {"n", "no"}:
            print("Enter y to accept, n to select the tag, or q to cancel.", file=stream)
            continue

        while True:
            selection = reader(
                f"Enter the tag photo number [1-{len(photos)}], or q to cancel: "
            ).strip().casefold()
            if selection in {"q", "quit"}:
                raise ReviewCancelled("Photo-role review cancelled.")
            try:
                tag_index = int(selection) - 1
            except ValueError:
                tag_index = -1
            if 0 <= tag_index < len(photos):
                return resolve_roles_with_tag_index(
                    photos,
                    validated,
                    tag_index=tag_index,
                )
            print("Enter one of the displayed photo numbers.", file=stream)


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    try:
        return input()
    except EOFError as error:
        raise ReviewCancelled("Review ended before approval.") from error


def _fact_value(raw: Any) -> str | None:
    if isinstance(raw, Mapping):
        value = raw.get("value")
    else:
        value = raw
    return value if isinstance(value, str) else None


def _prompt_edit(
    field_name: str,
    current: str | None,
    input_fn: Callable[[str], str],
) -> str | None:
    shown = current or "blank"
    response = input_fn(f"{FIELD_LABELS[field_name]} [{shown}]: ").strip()
    if response.casefold() in {"q", "quit"}:
        raise ReviewCancelled("Review cancelled before approval.")
    if response == "":
        return current
    if response == "-":
        return None
    return response


def review_facts_interactively(
    initial_facts: Mapping[str, Any],
    *,
    input_fn: Callable[[str], str] | None = None,
    output: TextIO | None = None,
) -> dict[str, str | None]:
    """Edit, validate, retry, and explicitly approve facts in the terminal."""
    reader = input_fn or _terminal_input
    stream = output or sys.stderr
    edits = {
        field_name: _fact_value(initial_facts.get(field_name))
        for field_name in FINAL_FACT_NAMES
    }
    fields_to_prompt = list(FINAL_FACT_NAMES)

    print(
        "Review each field: Enter keeps it, - clears it, and q cancels.",
        file=stream,
    )
    while True:
        for field_name in fields_to_prompt:
            edits[field_name] = _prompt_edit(field_name, edits[field_name], reader)

        outcome = validate_final_edits(edits)
        if outcome.is_valid:
            approval = reader("Approve these final facts? [y/N]: ").strip().casefold()
            if approval in {"y", "yes"}:
                return dict(outcome.approved_facts or {})
            if approval in {"q", "quit"}:
                raise ReviewCancelled("Review cancelled before approval.")
            print("Approval not confirmed; review the fields again.", file=stream)
            fields_to_prompt = list(FINAL_FACT_NAMES)
            continue

        print("Please correct these fields:", file=stream)
        invalid_fields = set()
        for error in outcome.errors:
            field_name = error["field"]
            invalid_fields.add(field_name)
            print(f"- {FIELD_LABELS.get(field_name, field_name)}: {error['message']}", file=stream)
        fields_to_prompt = [
            field_name for field_name in FINAL_FACT_NAMES if field_name in invalid_fields
        ]


def review_listing_draft_interactively(
    initial_draft: Mapping[str, str],
    *,
    input_fn: Callable[[str], str] | None = None,
    output: TextIO | None = None,
) -> dict[str, str]:
    """Edit and explicitly approve generated title and description text."""
    reader = input_fn or _terminal_input
    stream = output or sys.stderr
    edits = {field_name: initial_draft.get(field_name, "") for field_name in DRAFT_LABELS}
    fields_to_prompt = list(DRAFT_LABELS)

    print("Review the generated listing text; Enter keeps it and q cancels.", file=stream)
    while True:
        for field_name in fields_to_prompt:
            response = reader(f"{DRAFT_LABELS[field_name]} [{edits[field_name]}]: ").strip()
            if response.casefold() in {"q", "quit"}:
                raise ReviewCancelled("Listing review cancelled before approval.")
            if response:
                edits[field_name] = response

        draft, errors = validate_listing_draft(edits)
        if draft is not None:
            approval = reader("Approve this title and description? [y/N]: ").strip().casefold()
            if approval in {"y", "yes"}:
                return draft.to_dict()
            if approval in {"q", "quit"}:
                raise ReviewCancelled("Listing review cancelled before approval.")
            print("Approval not confirmed; review the listing text again.", file=stream)
            fields_to_prompt = list(DRAFT_LABELS)
            continue

        print("Please correct the listing text:", file=stream)
        invalid_fields = {error["field"] for error in errors}
        for error in errors:
            print(f"- {DRAFT_LABELS[error['field']]}: {error['message']}", file=stream)
        fields_to_prompt = [field_name for field_name in DRAFT_LABELS if field_name in invalid_fields]
