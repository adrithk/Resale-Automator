"""Validate user-edited facts before they become an approved result."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from depop_vocab import DepopVocabulary


FINAL_FACT_NAMES = (
    "category",
    "item_type",
    "brand",
    "condition",
    "size",
    "inseam",
    "primary_color",
    "secondary_color",
    "source_1",
    "source_2",
    "age",
    "style_1",
    "style_2",
    "style_3",
)
REQUIRED_FINAL_FACTS = {
    "category",
    "item_type",
    "brand",
    "condition",
    "size",
    "primary_color",
}
DESTINATION_FIELDS = {
    "category",
    "brand",
    "condition",
    "primary_color",
    "secondary_color",
    "source_1",
    "source_2",
    "age",
    "style_1",
    "style_2",
    "style_3",
}
PLACEHOLDER_VALUES = {"null", "unknown", "n/a", "none"}
INSEAM_PATTERN = re.compile(r'^([1-9][0-9]?)\s*(?:"|in|inches)?$', re.IGNORECASE)


@dataclass(frozen=True)
class FinalReviewOutcome:
    """Either canonical approved facts or field-specific validation errors."""

    approved_facts: Mapping[str, str | None] | None
    errors: tuple[Mapping[str, str], ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.approved_facts is not None and not self.errors


def _error(code: str, field_name: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field_name, "message": message}


def _clean_value(field_name: str, value: Any) -> tuple[str | None, dict[str, str] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, _error("invalid_type", field_name, "Value must be text or blank.")
    cleaned = value.strip()
    if not cleaned:
        return None, None
    if cleaned.casefold() in PLACEHOLDER_VALUES:
        return None, _error(
            "invalid_placeholder",
            field_name,
            "Use a blank value instead of a placeholder.",
        )
    return cleaned, None


def validate_final_edits(
    edits: Mapping[str, Any],
    *,
    vocabulary: DepopVocabulary | None = None,
) -> FinalReviewOutcome:
    """Validate and canonicalize final user edits with Category before Size."""
    destination = vocabulary or DepopVocabulary()
    errors: list[Mapping[str, str]] = []
    cleaned: dict[str, str | None] = {}

    unexpected = set(edits) - set(FINAL_FACT_NAMES)
    for field_name in sorted(unexpected):
        errors.append(_error("unexpected_field", field_name, "Field is not editable."))

    for field_name in FINAL_FACT_NAMES:
        value, error = _clean_value(field_name, edits.get(field_name))
        cleaned[field_name] = value
        if error is not None:
            errors.append(error)
        elif field_name in REQUIRED_FINAL_FACTS and value is None:
            errors.append(_error("required_value", field_name, "A value is required."))

    approved: dict[str, str | None] = dict(cleaned)

    category = cleaned["category"]
    if category is not None:
        match = destination.match("category", category)
        if match is None:
            errors.append(
                _error("unsupported_value", "category", "Choose an exact Depop category.")
            )
            approved["category"] = None
        else:
            approved["category"] = match.upload_value

    for field_name in DESTINATION_FIELDS - {"category"}:
        value = cleaned[field_name]
        if value is None:
            continue
        match = destination.match(field_name, value)
        if match is None:
            errors.append(
                _error(
                    "unsupported_value",
                    field_name,
                    f"Choose an exact Depop {field_name} value.",
                )
            )
            approved[field_name] = None
        else:
            approved[field_name] = match.upload_value

    size = cleaned["size"]
    if size is not None:
        if approved["category"] is None:
            errors.append(
                _error("size_requires_category", "size", "Choose a valid Category first.")
            )
            approved["size"] = None
        else:
            mapped_size = destination.match_size(approved["category"], size)
            if mapped_size is None:
                errors.append(
                    _error(
                        "unsupported_size",
                        "size",
                        "Choose an exact size allowed for the selected Category.",
                    )
                )
                approved["size"] = None
            else:
                approved["size"] = mapped_size

    inseam = cleaned["inseam"]
    if inseam is not None:
        match = INSEAM_PATTERN.fullmatch(inseam)
        if match is None:
            errors.append(
                _error("invalid_measurement", "inseam", "Use inches, for example 34 or 34\".")
            )
            approved["inseam"] = None
        else:
            approved["inseam"] = f'{match.group(1)}"'

    item_type = cleaned["item_type"]
    if item_type is not None:
        approved["item_type"] = item_type

    if errors:
        return FinalReviewOutcome(approved_facts=None, errors=tuple(errors))
    return FinalReviewOutcome(approved_facts=approved)
