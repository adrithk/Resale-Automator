"""Generate deterministic listing text from approved facts only."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from depop_vocab import DepopValue
from review_validation import validate_final_edits


class ListingGenerationError(ValueError):
    """Approved facts failed the final validation boundary."""


@dataclass(frozen=True)
class ListingDraft:
    """Editable title and description generated from approved facts."""

    draft_title: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "draft_title": self.draft_title,
            "description": self.description,
        }


def validate_listing_draft(
    draft: Mapping[str, Any],
) -> tuple[ListingDraft | None, tuple[Mapping[str, str], ...]]:
    """Require text and enforce the supplied version-6 description limits."""
    errors: list[Mapping[str, str]] = []
    values: dict[str, str] = {}
    for field_name in ("draft_title", "description"):
        value = draft.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(
                {
                    "code": "required_text",
                    "field": field_name,
                    "message": "Enter non-empty text.",
                }
            )
        else:
            values[field_name] = value.strip()
    description = values.get("description", "")
    if len(description) > 1000:
        errors.append({
            "code": "description_too_long",
            "field": "description",
            "message": "Depop descriptions must be no more than 1,000 characters.",
        })
    if len(re.findall(r"(?<!\w)#\w+", description)) > 5:
        errors.append({
            "code": "too_many_hashtags",
            "field": "description",
            "message": "Depop descriptions may contain at most 5 hashtags.",
        })
    if errors:
        return None, tuple(errors)
    return ListingDraft(**values), ()


def _label(value: str) -> str:
    return DepopValue.from_upload_value(value).label


def generate_listing_draft(approved_facts: Mapping[str, Any]) -> ListingDraft:
    """Build listing prose only after every final fact passes validation again."""
    validation = validate_final_edits(approved_facts)
    if not validation.is_valid or validation.approved_facts is None:
        fields = ", ".join(error["field"] for error in validation.errors)
        raise ListingGenerationError(f"Approved facts are invalid: {fields}")

    facts = validation.approved_facts
    brand = _label(facts["brand"])
    item_type = facts["item_type"]
    color = _label(facts["primary_color"])
    size = facts["size"]

    title = f"{brand} {color} {item_type}"
    description_parts = [title + "."]

    size_sentence = f"Size: {size}"
    if facts["inseam"] is not None:
        size_sentence += f" with a {facts['inseam']} inseam"
    description_parts.append(size_sentence + ".")

    return ListingDraft(
        draft_title=title,
        description=" ".join(description_parts),
    )
