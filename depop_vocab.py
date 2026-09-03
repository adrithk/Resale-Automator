"""Deterministic mapping to values accepted by Depop template version 6."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property, lru_cache
import json
from pathlib import Path
import re
import unicodedata
from typing import Any


DEFAULT_VOCABULARY_PATH = Path(__file__).parent / "data" / "depop_template_v6.json"

FIELD_ALIASES = {
    "color_1": "color",
    "color_2": "color",
    "primary_color": "color",
    "secondary_color": "color",
    "source_1": "source",
    "source_2": "source",
    "style_1": "style",
    "style_2": "style",
    "style_3": "style",
}

VALUE_ALIASES = {
    "color": {
        "gray": "grey",
    },
}

SIZE_ALIASES = {
    "extra extra small": "xxs",
    "extra small": "xs",
    "small": "s",
    "medium": "m",
    "large": "l",
    "extra large": "xl",
    "extra extra large": "xxl",
    "one-size": "one size",
    "onesize": "one size",
}
PLAIN_WAIST_PATTERN = re.compile(r"^[1-9][0-9]?$")


class DepopVocabularyError(ValueError):
    """Base error for unsupported destination fields and values."""


class UnsupportedDepopFieldError(DepopVocabularyError):
    """Raised when a field has no versioned Depop vocabulary."""


class UnsupportedDepopValueError(DepopVocabularyError):
    """Raised when a value cannot be mapped without guessing."""


@dataclass(frozen=True)
class DepopValue:
    """A human-readable label and its canonical upload representation."""

    label: str
    code: str | None
    upload_value: str

    @classmethod
    def from_upload_value(cls, upload_value: str) -> DepopValue:
        if upload_value.endswith(")") and " (" in upload_value:
            label, code = upload_value.rsplit(" (", 1)
            return cls(label=label, code=code[:-1], upload_value=upload_value)
        return cls(label=upload_value, code=None, upload_value=upload_value)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return " ".join(re.findall(r"\w+", normalized, flags=re.UNICODE))


def _normalize_size(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@lru_cache(maxsize=4)
def _load_vocabulary_data(path: str) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as vocabulary_file:
        return json.load(vocabulary_file)


class DepopVocabulary:
    """Match proposed text to exact, versioned Depop upload values."""

    def __init__(self, path: Path = DEFAULT_VOCABULARY_PATH) -> None:
        self.path = Path(path)
        self.data = _load_vocabulary_data(str(self.path.resolve()))

    @property
    def template_version(self) -> int:
        return int(self.data["template_version"])

    @cached_property
    def fields(self) -> tuple[str, ...]:
        return tuple(self.data["vocabularies"])

    def values(self, field_name: str) -> tuple[str, ...]:
        field = self._field_name(field_name)
        return tuple(self.data["vocabularies"][field])

    @cached_property
    def _indexes(self) -> dict[str, dict[str, tuple[DepopValue, ...]]]:
        indexes: dict[str, dict[str, tuple[DepopValue, ...]]] = {}
        for field in self.fields:
            candidates: dict[str, dict[str, DepopValue]] = {}
            for upload_value in self.values(field):
                value = DepopValue.from_upload_value(upload_value)
                keys = {_normalize(value.upload_value), _normalize(value.label)}
                if value.code:
                    keys.add(_normalize(value.code))
                for key in keys:
                    candidates.setdefault(key, {})[value.upload_value] = value
            indexes[field] = {
                key: tuple(matches.values()) for key, matches in candidates.items()
            }
        return indexes

    def match(self, field_name: str, proposed_value: str) -> DepopValue | None:
        """Return one unambiguous match, otherwise require later review."""
        field = self._field_name(field_name)
        if not isinstance(proposed_value, str):
            raise TypeError("proposed_value must be a string")

        key = _normalize(proposed_value)
        if not key:
            return None
        key = VALUE_ALIASES.get(field, {}).get(key, key)
        matches = self._indexes[field].get(key, ())
        return matches[0] if len(matches) == 1 else None

    def require_match(self, field_name: str, proposed_value: str) -> DepopValue:
        """Return an exact destination match or reject the proposed value."""
        match = self.match(field_name, proposed_value)
        if match is None:
            raise UnsupportedDepopValueError(
                f"{proposed_value!r} is not an unambiguous Depop {field_name} value"
            )
        return match

    def valid_sizes(self, category: str) -> tuple[str, ...]:
        """Return only the size values allowed for the resolved category."""
        category_match = self.require_match("category", category)
        group = self.data["category_size_groups"].get(category_match.upload_value)
        if group is None:
            return ()
        return tuple(self.data["size_groups"][group])

    def match_size(self, category: str, proposed_size: str) -> str | None:
        """Match a labeled size within its category-specific size group."""
        if not isinstance(proposed_size, str):
            raise TypeError("proposed_size must be a string")

        key = _normalize_size(proposed_size)
        if not key:
            return None
        key = SIZE_ALIASES.get(key, key)
        category_match = self.require_match("category", category)
        valid_sizes = self.valid_sizes(category_match.upload_value)

        # For jeans, a bare number entered during review means waist inches.
        # Canonical output still uses Depop's quoted value, such as 32".
        if (
            category_match.code is not None
            and category_match.code.endswith(", bottoms, jeans")
            and PLAIN_WAIST_PATTERN.fullmatch(key)
        ):
            waist_value = f'{key}"'
            if waist_value in valid_sizes:
                return waist_value

        matches = [
            size for size in valid_sizes if _normalize_size(size) == key
        ]
        return matches[0] if len(matches) == 1 else None

    def require_size(self, category: str, proposed_size: str) -> str:
        """Return a permitted size or reject a category/size mismatch."""
        match = self.match_size(category, proposed_size)
        if match is None:
            raise UnsupportedDepopValueError(
                f"{proposed_size!r} is not a supported size for {category!r}"
            )
        return match

    def _field_name(self, field_name: str) -> str:
        field = FIELD_ALIASES.get(field_name, field_name)
        if field not in self.data["vocabularies"]:
            raise UnsupportedDepopFieldError(
                f"{field_name!r} has no Depop dropdown vocabulary"
            )
        return field
