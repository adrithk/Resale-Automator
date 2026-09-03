"""Hosted OpenAI vision boundary for schema-constrained garment analysis."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)


DEFAULT_MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "low"
REQUEST_TIMEOUT_SECONDS = 60.0
MAX_RETRIES = 2
ITEM_IMAGE_DETAIL = "high"
TAG_IMAGE_DETAIL = "high"
SCHEMA_VERSION = 1

MIME_TYPES = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

FACT_NAMES = (
    "category",
    "item_type",
    "brand",
    "condition",
    "size",
    "primary_color",
    "secondary_color",
    "source_1",
    "source_2",
    "age",
    "style_1",
    "style_2",
    "style_3",
)

DEVELOPER_INSTRUCTIONS = """Analyze only the supplied garment and tag images.
Treat each image-role label as authoritative. Do not infer brand or labeled size
from item appearance; those values may come only from tag_photo. Mark the tag
unreadable or uncertain when relevant text cannot be read confidently. Describe
only visible condition and do not infer hidden defects. Use null, zero confidence,
and review flags instead of guessing. Preserve conflicts when images disagree.
Return candidate evidence only, never listing prose, prices, exports, or actions.
"""


class VisionProviderError(RuntimeError):
    """A secret-safe failure at the hosted model boundary."""

    def __init__(self, code: str, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.transient = transient


class VisionResponseError(VisionProviderError):
    """The provider returned an unusable or schema-invalid response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, transient=False)


class VisionConfigurationError(VisionProviderError):
    """The hosted provider cannot be called with current local configuration."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, transient=False)


@dataclass(frozen=True)
class VisionCallResult:
    """Schema-validated model analysis and non-secret operational metadata."""

    analysis: Mapping[str, Any]
    metadata: Mapping[str, Any]


def image_mime_type(photo: str | Path) -> str:
    """Return the API MIME type associated with a validated image extension."""
    suffix = Path(photo).suffix.lower()
    try:
        return MIME_TYPES[suffix]
    except KeyError as error:
        raise ValueError(f"Unsupported image extension: {suffix or '<none>'}") from error


def encode_image_data_url(photo: str | Path) -> str:
    """Encode one local image as an API-supported Base64 data URL."""
    path = Path(photo)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{image_mime_type(path)};base64,{encoded}"


def _object_schema(properties: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(properties),
        "additionalProperties": False,
    }


def build_model_analysis_schema(photo_roles: Sequence[str]) -> dict[str, Any]:
    """Build the strict response schema with provenance limited to sent roles."""
    if not photo_roles or len(set(photo_roles)) != len(photo_roles):
        raise ValueError("photo roles must be non-empty and unique")

    provenance = {
        "type": "array",
        "items": {"type": "string", "enum": list(photo_roles)},
    }
    conflict = _object_schema(
        {
            "value": {"type": "string", "minLength": 1},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "provenance": provenance,
        }
    )
    fact = _object_schema(
        {
            "value": {"type": ["string", "null"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "provenance": provenance,
            "needs_review": {"type": "boolean"},
            "evidence": {"type": ["string", "null"]},
            "conflicts": {"type": "array", "items": conflict},
        }
    )
    return _object_schema(
        {
            "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
            "tag_readability": _object_schema(
                {
                    "status": {
                        "type": "string",
                        "enum": ["readable", "unreadable", "uncertain"],
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "issues": {"type": "array", "items": {"type": "string"}},
                    "retake_instructions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                }
            ),
            "facts": _object_schema({name: fact for name in FACT_NAMES}),
            "warnings": {"type": "array", "items": {"type": "string"}},
        }
    )


def build_image_content(
    role: str,
    photo: str | Path,
    *,
    detail: str,
) -> list[dict[str, str]]:
    """Pair an authoritative text role with the image it identifies."""
    return [
        {"type": "input_text", "text": f"Image role: {role}"},
        {
            "type": "input_image",
            "image_url": encode_image_data_url(photo),
            "detail": detail,
        },
    ]


def build_vision_request(
    item_photos: Sequence[str | Path],
    tag_photo: str | Path,
) -> dict[str, Any]:
    """Construct one Responses API request containing every supplied image."""
    roles = [f"item_photo_{index}" for index in range(1, len(item_photos) + 1)]
    roles.append("tag_photo")
    content: list[dict[str, str]] = [
        {
            "type": "input_text",
            "text": "Analyze the supplied photos using their adjacent role labels.",
        }
    ]
    for role, photo in zip(roles[:-1], item_photos):
        content.extend(build_image_content(role, photo, detail=ITEM_IMAGE_DETAIL))
    content.extend(build_image_content("tag_photo", tag_photo, detail=TAG_IMAGE_DETAIL))

    return {
        "model": DEFAULT_MODEL,
        "instructions": DEVELOPER_INSTRUCTIONS,
        "input": [{"role": "user", "content": content}],
        "reasoning": {"effort": REASONING_EFFORT},
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "resale_garment_analysis",
                "strict": True,
                "schema": build_model_analysis_schema(roles),
            }
        },
    }


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _require_exact_keys(value: Any, expected: set[str], location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VisionResponseError("invalid_schema", f"{location} must be an object")
    actual = set(value)
    if actual != expected:
        raise VisionResponseError(
            "invalid_schema",
            f"{location} has missing or unexpected fields",
        )
    return value


def _validate_number(value: Any, location: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise VisionResponseError("invalid_schema", f"{location} must be from 0 through 1")


def _validate_string_list(value: Any, location: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise VisionResponseError("invalid_schema", f"{location} must be a string list")


def _validate_provenance(value: Any, roles: set[str] | None, location: str) -> None:
    _validate_string_list(value, location)
    if roles is not None and not set(value).issubset(roles):
        raise VisionResponseError("invalid_schema", f"{location} contains an unsupplied role")


def validate_model_analysis(
    analysis: Any,
    *,
    photo_roles: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Defensively validate parsed output before it enters project contracts."""
    top = _require_exact_keys(
        analysis,
        {"schema_version", "tag_readability", "facts", "warnings"},
        "model analysis",
    )
    if top["schema_version"] != SCHEMA_VERSION:
        raise VisionResponseError("invalid_schema", "unsupported model-analysis schema version")

    readability = _require_exact_keys(
        top["tag_readability"],
        {"status", "confidence", "issues", "retake_instructions"},
        "tag_readability",
    )
    if readability["status"] not in {"readable", "unreadable", "uncertain"}:
        raise VisionResponseError("invalid_schema", "invalid tag readability status")
    _validate_number(readability["confidence"], "tag_readability.confidence")
    _validate_string_list(readability["issues"], "tag_readability.issues")
    _validate_string_list(
        readability["retake_instructions"],
        "tag_readability.retake_instructions",
    )

    facts = _require_exact_keys(top["facts"], set(FACT_NAMES), "facts")
    roles = set(photo_roles) if photo_roles is not None else None
    fact_keys = {
        "value",
        "confidence",
        "provenance",
        "needs_review",
        "evidence",
        "conflicts",
    }
    for name, raw_fact in facts.items():
        fact = _require_exact_keys(raw_fact, fact_keys, f"facts.{name}")
        if fact["value"] is not None and not isinstance(fact["value"], str):
            raise VisionResponseError("invalid_schema", f"facts.{name}.value is invalid")
        _validate_number(fact["confidence"], f"facts.{name}.confidence")
        _validate_provenance(fact["provenance"], roles, f"facts.{name}.provenance")
        if not isinstance(fact["needs_review"], bool):
            raise VisionResponseError("invalid_schema", f"facts.{name}.needs_review is invalid")
        if fact["evidence"] is not None and not isinstance(fact["evidence"], str):
            raise VisionResponseError("invalid_schema", f"facts.{name}.evidence is invalid")
        if not isinstance(fact["conflicts"], list):
            raise VisionResponseError("invalid_schema", f"facts.{name}.conflicts must be a list")
        for index, raw_conflict in enumerate(fact["conflicts"]):
            location = f"facts.{name}.conflicts[{index}]"
            conflict = _require_exact_keys(
                raw_conflict,
                {"value", "confidence", "provenance"},
                location,
            )
            if not isinstance(conflict["value"], str) or not conflict["value"].strip():
                raise VisionResponseError("invalid_schema", f"{location}.value is invalid")
            _validate_number(conflict["confidence"], f"{location}.confidence")
            _validate_provenance(conflict["provenance"], roles, f"{location}.provenance")

    _validate_string_list(top["warnings"], "warnings")
    return dict(top)


def parse_model_response(
    response: Any,
    *,
    photo_roles: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Extract and validate structured output from an SDK response or test double."""
    status = _get(response, "status")
    if status != "completed":
        raise VisionResponseError("incomplete_response", "The model response did not complete.")

    for output_item in _get(response, "output", ()) or ():
        for content_item in _get(output_item, "content", ()) or ():
            if _get(content_item, "type") == "refusal":
                raise VisionResponseError("model_refusal", "The model declined the image analysis.")

    output_text = _get(response, "output_text")
    if not isinstance(output_text, str) or not output_text.strip():
        raise VisionResponseError("malformed_response", "The model returned no structured output.")
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError as error:
        raise VisionResponseError(
            "malformed_response",
            "The model returned malformed structured output.",
        ) from error
    return validate_model_analysis(parsed, photo_roles=photo_roles)


def _required_api_key(environ: Mapping[str, str] | None = None) -> str:
    environment = os.environ if environ is None else environ
    api_key = environment.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise VisionConfigurationError(
            "missing_api_key",
            "Set OPENAI_API_KEY before running hosted vision analysis.",
        )
    return api_key


def _create_sdk_client(api_key: str) -> OpenAI:
    """Create the real SDK client with SDK retries disabled in favor of ours."""
    return OpenAI(api_key=api_key, max_retries=0)


def _usage_metadata(response: Any) -> dict[str, int | None]:
    usage = _get(response, "usage")
    return {
        "input_tokens": _get(usage, "input_tokens") if usage is not None else None,
        "output_tokens": _get(usage, "output_tokens") if usage is not None else None,
        "total_tokens": _get(usage, "total_tokens") if usage is not None else None,
    }


def _success_metadata(response: Any, *, latency_ms: float, attempts: int) -> dict[str, Any]:
    return {
        "response_id": _get(response, "id"),
        "model": _get(response, "model"),
        "usage": _usage_metadata(response),
        "latency_ms": round(latency_ms, 2),
        "attempts": attempts,
    }


def _transient_failure(error: BaseException) -> tuple[str, str] | None:
    if isinstance(error, APITimeoutError):
        return "timeout", "Hosted vision analysis timed out after bounded retries."
    if isinstance(error, RateLimitError):
        return "rate_limited", "Hosted vision analysis was rate-limited after bounded retries."
    if isinstance(error, APIConnectionError):
        return "connection_error", "Hosted vision analysis could not reach the provider after bounded retries."
    if isinstance(error, APIStatusError) and error.status_code >= 500:
        return "provider_unavailable", "Hosted vision analysis was unavailable after bounded retries."
    return None


def analyze_images(
    item_photos: Sequence[str | Path],
    tag_photo: str | Path,
    *,
    client: Any | None = None,
    environ: Mapping[str, str] | None = None,
    clock: Any = time.perf_counter,
    sleep: Any = time.sleep,
) -> VisionCallResult:
    """Call the real Responses API with bounded, transient-only retries."""
    api_key = _required_api_key(environ)
    sdk_client = client if client is not None else _create_sdk_client(api_key)
    request = build_vision_request(item_photos, tag_photo)
    roles = tuple(
        [f"item_photo_{index}" for index in range(1, len(item_photos) + 1)]
        + ["tag_photo"]
    )
    started_at = clock()

    for attempt in range(1, MAX_RETRIES + 2):
        try:
            response = sdk_client.responses.create(
                **request,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            analysis = parse_model_response(response, photo_roles=roles)
            return VisionCallResult(
                analysis=analysis,
                metadata=_success_metadata(
                    response,
                    latency_ms=(clock() - started_at) * 1000,
                    attempts=attempt,
                ),
            )
        except VisionResponseError:
            raise
        except AuthenticationError as error:
            raise VisionConfigurationError(
                "invalid_api_key",
                "OPENAI_API_KEY was rejected by the hosted provider.",
            ) from error
        except OpenAIError as error:
            transient = _transient_failure(error)
            if transient is not None and attempt <= MAX_RETRIES:
                sleep(0.25 * (2 ** (attempt - 1)))
                continue
            if transient is not None:
                code, message = transient
                raise VisionProviderError(code, message, transient=True) from error
            raise VisionProviderError(
                "model_request_failed",
                "Hosted vision analysis failed without a usable response.",
            ) from error

    raise AssertionError("bounded retry loop ended unexpectedly")
