"""Exclusive local JSON persistence shared by CLI and localhost API adapters."""

from __future__ import annotations

import json
from pathlib import Path
import uuid
from typing import Any, Callable


APPROVED_LISTINGS_DIRECTORY = Path(__file__).resolve().parent / "approved_listings"


def random_output_filename() -> str:
    return f"approved-listing-{uuid.uuid4().hex}.json"


def save_approved_result(
    result: dict[str, Any],
    *,
    output_directory: str | Path = APPROVED_LISTINGS_DIRECTORY,
    filename_factory: Callable[[], str] = random_output_filename,
) -> Path:
    directory = Path(output_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        output_path = directory / filename_factory()
        result["saved_to"] = str(output_path)
        try:
            with output_path.open("x", encoding="utf-8") as output_file:
                json.dump(result, output_file, indent=2)
                output_file.write("\n")
            return output_path
        except FileExistsError:
            result.pop("saved_to", None)
    raise OSError("Could not allocate a unique approved-listing filename.")
