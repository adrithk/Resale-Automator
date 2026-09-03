"""Structured data contracts for proposed and validated clothing facts."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
import re
from typing import Any, Mapping, Sequence


TAG_DERIVED_FACTS = {"brand", "size", "inseam"}
TAG_DERIVED_PROVENANCE = {"tag_photo", "user_correction"}
CONDITION_USER_PROVENANCE = {"user_input", "user_correction"}
ITEM_PHOTO_DERIVED_FACTS = {
    "category",
    "item_type",
    "condition",
    "primary_color",
    "secondary_color",
    "style_1",
    "style_2",
    "style_3",
}
TAG_OR_ITEM_FACTS = {"source_1", "source_2", "age"}
TAG_OR_ITEM_USER_PROVENANCE = {"user_input", "user_correction"}
ITEM_PHOTO_PROVENANCE = re.compile(r"item_photo_[1-9][0-9]*\Z")


def _validate_confidence(confidence: float) -> None:
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise TypeError("confidence must be a number from 0 through 1")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be from 0 through 1")


def _validate_provenance(provenance: Sequence[str]) -> None:
    for source in provenance:
        if not isinstance(source, str) or not source.strip():
            raise ValueError("provenance values must be non-empty strings")


@dataclass(frozen=True)
class EvidenceClaim:
    """One conflicting value and the evidence that supports it."""

    value: str
    confidence: float
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("an evidence claim must have a non-empty value")
        _validate_confidence(self.confidence)
        _validate_provenance(self.provenance)
        if not self.provenance:
            raise ValueError("an evidence claim must have provenance")

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": self.confidence,
            "provenance": list(self.provenance),
        }


@dataclass(frozen=True)
class ClothingFact:
    """A proposed or validated fact with uncertainty and provenance."""

    value: str | None
    confidence: float
    provenance: tuple[str, ...] = ()
    needs_review: bool = False
    conflicts: tuple[EvidenceClaim, ...] = ()

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)
        _validate_provenance(self.provenance)

        if self.value is not None and (
            not isinstance(self.value, str) or not self.value.strip()
        ):
            raise ValueError("a known fact must have a non-empty string value")
        if self.value is not None and not self.provenance:
            raise ValueError("a known fact must have provenance")
        if self.value is None and self.confidence != 0:
            raise ValueError("an unknown fact must have confidence 0")
        if self.conflicts and not self.needs_review:
            raise ValueError("conflicting evidence must require review")

    @classmethod
    def unknown(cls, *, needs_review: bool = False) -> ClothingFact:
        """Represent an unknown value without inventing placeholder text."""
        return cls(value=None, confidence=0, needs_review=needs_review)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "value": self.value,
            "confidence": self.confidence,
            "provenance": list(self.provenance),
            "needs_review": self.needs_review,
        }
        if self.conflicts:
            result["conflicts"] = [conflict.to_dict() for conflict in self.conflicts]
        return result


def _validate_field_sources(field_name: str, sources: set[str]) -> None:
    if field_name in TAG_DERIVED_FACTS and not sources.issubset(
        TAG_DERIVED_PROVENANCE
    ):
        raise ValueError(f"{field_name} must come from tag_photo or user_correction")

    if field_name in ITEM_PHOTO_DERIVED_FACTS and not all(
        ITEM_PHOTO_PROVENANCE.fullmatch(source)
        or (field_name == "condition" and source in CONDITION_USER_PROVENANCE)
        for source in sources
    ):
        raise ValueError(
            f"{field_name} must come from visible item-photo evidence"
        )

    if field_name in TAG_OR_ITEM_FACTS and not all(
        ITEM_PHOTO_PROVENANCE.fullmatch(source)
        or source == "tag_photo"
        or source in TAG_OR_ITEM_USER_PROVENANCE
        for source in sources
    ):
        raise ValueError(f"{field_name} must come from item/tag evidence or explicit user input")


def validate_fact_provenance(field_name: str, fact: ClothingFact) -> None:
    """Apply universal source rules to the selected and conflicting claims."""
    if fact.value is not None:
        _validate_field_sources(field_name, set(fact.provenance))
    for conflict in fact.conflicts:
        _validate_field_sources(field_name, set(conflict.provenance))


@dataclass(frozen=True)
class ValidatedClothingFacts:
    """Candidate clothing facts kept separate from raw model analysis."""

    category: ClothingFact | None = None
    item_type: ClothingFact | None = None
    brand: ClothingFact | None = None
    condition: ClothingFact | None = None
    size: ClothingFact | None = None
    inseam: ClothingFact | None = None
    primary_color: ClothingFact | None = None
    secondary_color: ClothingFact | None = None
    source_1: ClothingFact | None = None
    source_2: ClothingFact | None = None
    age: ClothingFact | None = None
    style_1: ClothingFact | None = None
    style_2: ClothingFact | None = None
    style_3: ClothingFact | None = None

    def __post_init__(self) -> None:
        for contract_field in fields(self):
            fact = getattr(self, contract_field.name)
            if fact is not None:
                validate_fact_provenance(contract_field.name, fact)

    def to_dict(self) -> dict[str, dict[str, Any] | None]:
        return {
            contract_field.name: (
                getattr(self, contract_field.name).to_dict()
                if getattr(self, contract_field.name) is not None
                else None
            )
            for contract_field in fields(self)
        }


@dataclass(frozen=True)
class PipelineResult:
    """Keep each pipeline stage visible in serialized command output."""

    status: str
    image_analysis: Mapping[str, Any]
    warnings: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    model_analysis: Mapping[str, Any] | None = None
    model_metadata: Mapping[str, Any] | None = None
    validated_facts: ValidatedClothingFacts | None = None
    listing_draft: Mapping[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "image_analysis": dict(self.image_analysis),
            "model_analysis": (
                dict(self.model_analysis) if self.model_analysis is not None else None
            ),
            "model_metadata": (
                dict(self.model_metadata) if self.model_metadata is not None else None
            ),
            "validated_facts": (
                self.validated_facts.to_dict()
                if self.validated_facts is not None
                else None
            ),
            "listing_draft": (
                dict(self.listing_draft) if self.listing_draft is not None else None
            ),
            "warnings": [dict(warning) for warning in self.warnings],
        }
