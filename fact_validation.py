"""Convert model candidates into provenance-checked, Depop-mapped facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from contracts import (
    ClothingFact,
    EvidenceClaim,
    ValidatedClothingFacts,
    validate_fact_provenance,
)
from depop_vocab import DepopVocabulary
from openai_vision import FACT_NAMES


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

DEFAULT_TAG_RETAKE_INSTRUCTIONS = (
    "Retake the tag close up in bright, even light with all text in focus.",
    "Keep the full tag inside the frame and change the angle to remove glare.",
)


@dataclass(frozen=True)
class FactValidationOutcome:
    """Validated facts plus machine-readable reasons that still need review."""

    validated_facts: ValidatedClothingFacts | None
    issues: tuple[Mapping[str, str], ...] = ()
    tag_retake_instructions: tuple[str, ...] = ()

    @property
    def needs_review(self) -> bool:
        return bool(self.issues)


def _issue(code: str, field_name: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field_name, "message": message}


def _unknown_review_fact() -> ClothingFact:
    return ClothingFact.unknown(needs_review=True)


def _candidate_fact(field_name: str, raw: Mapping[str, Any]) -> ClothingFact:
    """Build a contract fact while strengthening model semantic invariants."""
    value = raw["value"]
    conflicts = tuple(
        EvidenceClaim(
            value=claim["value"],
            confidence=claim["confidence"],
            provenance=tuple(claim["provenance"]),
        )
        for claim in raw["conflicts"]
    )
    if value is None:
        if raw["confidence"] != 0 or raw["provenance"] or raw["evidence"] is not None:
            raise ValueError(f"{field_name} unknown candidate has supporting-value data")
        return ClothingFact.unknown(needs_review=True)

    if not value.strip() or raw["evidence"] is None or not raw["evidence"].strip():
        raise ValueError(f"{field_name} known candidate lacks visible evidence")

    fact = ClothingFact(
        value=value,
        confidence=raw["confidence"],
        provenance=tuple(raw["provenance"]),
        needs_review=bool(raw["needs_review"] or conflicts),
        conflicts=conflicts,
    )
    validate_fact_provenance(field_name, fact)
    return fact


def _map_value(vocabulary: DepopVocabulary, field_name: str, value: str) -> str | None:
    match = vocabulary.match(field_name, value)
    return match.upload_value if match is not None else None


def _map_fact(
    vocabulary: DepopVocabulary,
    field_name: str,
    fact: ClothingFact,
    *,
    category: str | None = None,
) -> ClothingFact | None:
    if fact.value is None:
        return fact

    if field_name == "size":
        mapped_value = (
            vocabulary.match_size(category, fact.value) if category is not None else None
        )
        mapped_conflicts = tuple(
            EvidenceClaim(
                value=mapped,
                confidence=claim.confidence,
                provenance=claim.provenance,
            )
            for claim in fact.conflicts
            if (mapped := vocabulary.match_size(category, claim.value)) is not None
        ) if category is not None else ()
    elif field_name in DESTINATION_FIELDS:
        mapped_value = _map_value(vocabulary, field_name, fact.value)
        mapped_conflicts = tuple(
            EvidenceClaim(
                value=mapped,
                confidence=claim.confidence,
                provenance=claim.provenance,
            )
            for claim in fact.conflicts
            if (mapped := _map_value(vocabulary, field_name, claim.value)) is not None
        )
    else:
        mapped_value = fact.value
        mapped_conflicts = fact.conflicts

    if mapped_value is None or len(mapped_conflicts) != len(fact.conflicts):
        return None
    return ClothingFact(
        value=mapped_value,
        confidence=fact.confidence,
        provenance=fact.provenance,
        needs_review=fact.needs_review,
        conflicts=mapped_conflicts,
    )


def validate_candidate_analysis(
    analysis: Mapping[str, Any],
    *,
    vocabulary: DepopVocabulary | None = None,
) -> FactValidationOutcome:
    """Apply the tag gate, provenance rules, and exact destination mapping."""
    readability = analysis["tag_readability"]
    if readability["status"] != "readable":
        instructions = tuple(readability["retake_instructions"])
        if not instructions:
            instructions = DEFAULT_TAG_RETAKE_INSTRUCTIONS
        return FactValidationOutcome(
            validated_facts=None,
            issues=(
                _issue(
                    "tag_not_readable",
                    "tag_photo",
                    f"Tag readability is {readability['status']}.",
                ),
            ),
            tag_retake_instructions=instructions,
        )

    destination = vocabulary or DepopVocabulary()
    validated: dict[str, ClothingFact] = {}
    issues: list[Mapping[str, str]] = []

    # Category is deliberately first because Size has no universal vocabulary.
    ordered_names = ("category",) + tuple(
        name for name in FACT_NAMES if name not in {"category", "size"}
    ) + ("size",)
    for field_name in ordered_names:
        raw = analysis["facts"][field_name]
        try:
            candidate = _candidate_fact(field_name, raw)
        except (TypeError, ValueError) as error:
            validated[field_name] = _unknown_review_fact()
            issues.append(_issue("invalid_candidate", field_name, str(error)))
            continue

        if candidate.value is None:
            validated[field_name] = candidate
            issues.append(
                _issue("unknown_value", field_name, "The model did not supply a supported value.")
            )
            continue

        category = validated.get("category")
        mapped = _map_fact(
            destination,
            field_name,
            candidate,
            category=(category.value if category is not None else None),
        )
        if mapped is None:
            validated[field_name] = _unknown_review_fact()
            code = (
                "size_requires_category"
                if field_name == "size" and (category is None or category.value is None)
                else "unmapped_value"
            )
            issues.append(
                _issue(code, field_name, "The candidate cannot be mapped exactly to Depop.")
            )
            continue

        validated[field_name] = mapped
        if mapped.needs_review:
            issues.append(
                _issue(
                    "candidate_review_required",
                    field_name,
                    "The candidate contains conflicting evidence or a review flag.",
                )
            )

    return FactValidationOutcome(
        validated_facts=ValidatedClothingFacts(**validated),
        issues=tuple(issues),
    )
