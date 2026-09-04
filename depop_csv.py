"""Create a deterministic Depop bulk-listing CSV from approved data."""

from __future__ import annotations

import csv
import os
from io import StringIO
from typing import Any, Mapping, Sequence

from listing_generation import validate_listing_draft
from listing_pricing import normalize_price
from depop_vocab import DepopVocabulary
from review_validation import validate_final_edits
from photo_hosting import PhotoHostingError, validate_picture_urls


# Backend default; other sellers can override DEPOP_SHIPPING_LOCATION locally.
# Use a template dropdown value, never a street/return address.
DEFAULT_SHIPPING_LOCATION = "California, United States"

DEPOP_CSV_COLUMNS = (
    "Description",
    "Category",
    "Price",
    "Brand",
    "Condition",
    "Size",
    "Color 1",
    "Color 2",
    "Source 1",
    "Source 2",
    "Age",
    "Style 1",
    "Style 2",
    "Style 3",
    "Location",
    "Picture Hero url",
    "Picture 2 url",
    "Picture 3 url",
    "Picture 4 url",
    "Picture 5 url",
    "Picture 6 url",
    "Picture 7 url",
    "Picture 8 url",
    "Domestic Shipping price",
    "International Shipping price",
    "SKU",
)

# The upload sheet has three non-listing rows, not just a header. Preserve
# A1:Z3 from the supplied version-6 "Use This Template" sheet verbatim.
DEPOP_CSV_VERSION_ROW = ("Template version: 6",) + ("",) * 25
DEPOP_CSV_INSTRUCTIONS = (
    "Must be no more than 1,000 characters. Max. 5 hashtags.",
    "Select a category from the dropdown menu. You can type to search as well.",
    "Enter a price without a currency symbol. We'll use the currency you usually list in.",
    "Select a brand from the dropdown menu",
    "Select a condition from the dropdown menu",
    "Select a size from the dropdown menu",
    "Select a color from the dropdown menu",
    "Select a color from the dropdown menu",
    "Select a source from the dropdown menu",
    "Select a source from the dropdown menu",
    "Select an age from the dropdown menu",
    "Select a style from the dropdown menu",
    "Select a style from the dropdown menu",
    "Select a style from the dropdown menu",
    "Select the location you're shipping from",
    "Enter the url for the picture that will appear first",
    "Enter the url for the picture that will appear second",
    "Enter the url for the picture that will appear third",
    "Enter the url for the picture that will appear fourth",
    "Enter the url for the picture that will appear fifth",
    "Enter the url for the picture that will appear sixth",
    "Enter the url for the picture that will appear seventh",
    "Enter the url for the picture that will appear eighth",
    "Enter a shipping price without a currency symbol",
    "Enter a shipping price without a currency symbol",
    "Enter the SKU",
)

FACT_TO_CSV_COLUMN = {
    "category": "Category",
    "brand": "Brand",
    "condition": "Condition",
    "size": "Size",
    "primary_color": "Color 1",
    "secondary_color": "Color 2",
    "source_1": "Source 1",
    "source_2": "Source 2",
    "age": "Age",
    "style_1": "Style 1",
    "style_2": "Style 2",
    "style_3": "Style 3",
}


class DepopCsvError(ValueError):
    """Approved facts or listing text failed validation before export."""


def shipping_location() -> str:
    value = os.environ.get("DEPOP_SHIPPING_LOCATION", DEFAULT_SHIPPING_LOCATION).strip()
    if value not in DepopVocabulary().values("location"):
        raise DepopCsvError("Set DEPOP_SHIPPING_LOCATION to an exact template dropdown location, not a street address.")
    return value


def generate_depop_csv(
    approved_facts: Mapping[str, Any],
    listing_draft: Mapping[str, Any],
    *,
    price: Any = None,
    picture_urls: Sequence[str] = (),
) -> str:
    """Return the three template rows followed by one validated listing row."""
    facts = validate_final_edits(approved_facts)
    draft, draft_errors = validate_listing_draft(listing_draft)
    if not facts.is_valid or facts.approved_facts is None or draft is None:
        invalid_fields = [error["field"] for error in facts.errors]
        invalid_fields.extend(error["field"] for error in draft_errors)
        raise DepopCsvError(
            "Approved listing data is invalid: " + ", ".join(invalid_fields)
        )

    row = dict.fromkeys(DEPOP_CSV_COLUMNS, "")
    try:
        row["Price"] = normalize_price(price)
    except ValueError as error:
        raise DepopCsvError(str(error)) from error
    row["Location"] = shipping_location()
    row["Description"] = draft.description
    for fact_name, column_name in FACT_TO_CSV_COLUMN.items():
        row[column_name] = facts.approved_facts[fact_name] or ""
    try:
        urls = validate_picture_urls(picture_urls)
    except PhotoHostingError as error:
        raise DepopCsvError(str(error)) from error
    for column, url in zip(DEPOP_CSV_COLUMNS[15:23], urls):
        row[column] = url

    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(DEPOP_CSV_VERSION_ROW)
    writer.writerow(DEPOP_CSV_COLUMNS)
    writer.writerow(DEPOP_CSV_INSTRUCTIONS)
    writer.writerow([row[column] for column in DEPOP_CSV_COLUMNS])
    return output.getvalue()
