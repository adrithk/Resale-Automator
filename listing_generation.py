"""Generate deterministic listing text from approved facts only."""

from __future__ import annotations

from dataclasses import dataclass
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
    """Require non-empty final draft text without inventing destination limits."""
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
    condition = _label(facts["condition"])

    title = f"{brand} {color} {item_type}"
    description_parts = [f"{brand} {item_type} in {color}"]

    secondary_color = facts["secondary_color"]
    if secondary_color is not None:
        description_parts[0] += f" with {_label(secondary_color)} details"
    description_parts[0] += "."
    description_parts.append(f"Condition: {condition}.")

    size_sentence = f"Labeled waist size {size}"
    if facts["inseam"] is not None:
        size_sentence += f" with a {facts['inseam']} inseam"
    description_parts.append(size_sentence + ".")

    styles = [
        _label(facts[field_name])
        for field_name in ("style_1", "style_2", "style_3")
        if facts[field_name] is not None
    ]
    if styles:
        description_parts.append(f"Style: {', '.join(styles)}.")

    if facts["age"] is not None:
        description_parts.append(f"Age: {_label(facts['age'])}.")

    return ListingDraft(
        draft_title=title,
        description=" ".join(description_parts),
    )
