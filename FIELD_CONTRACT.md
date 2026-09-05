# Listing Field Contract

This is the source of truth for listing-field priority, evidence, and CSV
mapping in the current localhost app. Destination vocabularies come from the
supplied Depop bulk-listing template version 6 and are stored in
[`data/depop_template_v6.json`](data/depop_template_v6.json).

The hosted model proposes candidate evidence. Python enforces provenance,
unknowns, conflicts, the readable-tag gate, and exact destination values.
Human edits pass final validation before approval. The web workflow additionally
requires an approved price and hosted photos for CSV export; the CLI ends with
an approved local JSON result. See [README.md](README.md) for setup and architecture.

## Requirement labels

- **Required**: needed before a listing draft can be considered complete.
- **Recommended**: useful when supported by evidence, but may be omitted.
- **Optional**: include only when clearly available and useful.
- **Deferred**: belongs to a later system phase rather than the current
  implementation.
- **Excluded**: intentionally outside the current scope.
- **Unresolved**: meaning or destination requirements must be clarified.

## Template-field decisions

| Template field | Requirement | Allowed source | Reason or rule |
| --- | --- | --- | --- |
| Description | Required | Listing generator using validated facts only | Must be succinct and reviewed by the user. |
| Category | Required | Vision model, then exact Depop mapping and user review | Must map to one of the 319 template values, including its canonical identifier. |
| Price | Required for CSV | Separate model price suggestion from approved facts, then user review | Estimate resale value, divide by two in Python, and round half-up to cents. Ordinary items target $10–$15; the amount remains editable. Not researched Depop average pricing. |
| Brand | Required | Readable tag, or explicit user correction | Never guess a brand from weak visual evidence. |
| Condition | Required | Visible garment evidence, then exact Depop mapping and user review | Must use one of the five confirmed values; state only visible condition and do not infer hidden defects. |
| Size | Required | Readable tag, or explicit user correction | Map jeans labels such as `W36 L34`, `32x34`, or `Waist × Length 32 × 34 inch` by waist only after Category resolves; during review, a bare number such as `32` means waist inches and is stored as `32"`. Retain the parsed inseam for description wording. |
| Inseam (internal) | Optional | Readable tag, or explicit user correction | Retained tag evidence such as `34"`; it is not a Depop upload field and is included in the generated description when present. |
| Color 1 | Required | Garment photos, then exact Depop mapping and user review | Primary visible color mapped to one of the 19 confirmed values. |
| Color 2 | Recommended | Garment photos, then exact Depop mapping and user review | Include only when a meaningful secondary color maps to a confirmed value. |
| Source 1 | Recommended | Item/tag evidence or user input, then review | First applicable Depop source value from the confirmed vocabulary below. |
| Source 2 | Optional | Item/tag evidence or user input, then review | Second applicable Depop source value; omit when only one applies. |
| Age | Recommended | Explicit tag/item evidence or user input, then exact Depop mapping | Leave blank when review-flagged; never infer an era from styling or construction. |
| Style 1 | Recommended | Garment photos, then exact Depop mapping | Primary style tag from the 32 confirmed values; an exact non-conflicting value may be retained despite low confidence. |
| Style 2 | Optional | Garment photos, then exact Depop mapping | Additional confirmed style tag; an exact non-conflicting value may be retained despite low confidence. |
| Style 3 | Optional | Garment photos, then exact Depop mapping | Additional confirmed style tag; an exact non-conflicting value may be retained despite low confidence. |
| Location | Required for CSV | Backend configuration | Default `California, United States`; optional `DEPOP_SHIPPING_LOCATION` override must exactly match a template value. Never a street address or model input. |
| Picture Hero url | Required for web CSV | Cloudinary hosting | First photo in the website's upload order, regardless of model-assigned role. |
| Picture 2 url | Required for web CSV | Cloudinary hosting | Second uploaded photo. |
| Picture 3 url | Required for web CSV | Cloudinary hosting | Third uploaded photo; tag photos are included. |
| Picture 4 url | Optional | Cloudinary hosting | Fourth uploaded photo, when supplied. |
| Picture 5 url | Optional | Cloudinary hosting | Fifth uploaded photo, when supplied. |
| Picture 6 url | Optional | Cloudinary hosting | Sixth uploaded photo, when supplied. |
| Picture 7 url | Optional | Cloudinary hosting | Seventh uploaded photo, when supplied. |
| Picture 8 url | Optional | Cloudinary hosting | Eighth uploaded photo, when supplied. |
| Domestic Shipping price | Excluded | User or future shipping settings | Shipping prices are explicitly outside the current scope. |
| International Shipping price | Excluded | User or future shipping settings | Shipping prices are explicitly outside the current scope. |
| SKU | Excluded | None | The user confirmed that SKU is not necessary. |

Every photo uploaded through the website, including the tag, is hosted on
listing approval without a separate photo confirmation. Public copies have
metadata removed; original source files remain untouched. Upload order is
retained; over-eight batches are rejected rather than truncated. These hosting
requirements apply to web export, not the CLI.

## Implemented CSV export

After explicit listing approval, `depop_csv.py` revalidates the canonical facts
and listing draft, then preserves the three leading rows from the supplied
[Google Sheet](https://docs.google.com/spreadsheets/d/1xgHv0DpXlY1f5qADh-IL0iOHgnoma3T5/edit?gid=1319093190#gid=1319093190),
`Use This Template!A1:Z3`: `Template version: 6` (with 25 empty cells),
the 26 exact headers, and the 26 instruction cells. The listing starts on row 4.
Picture headers use lowercase `url`. The generated Description and approved
destination facts populate their matching columns. `draft_title` and internal Inseam are not
template columns; the description already carries relevant inseam wording.

Price and Location are required by Depop import and are now populated: the
approved editable price and the configured backend location. All supplied photo
URLs fill the picture slots in order; unused slots, Domestic Shipping price,
International Shipping price, and SKU remain empty. This is a
conservative draft export, not a claim that the listing is publication-ready.
The user finishes those operational details and verifies photos in Depop. CSV
generation never uploads, publishes, or calls an external marketplace.

The template's Description instruction confirms a maximum of 1,000 characters
and five hashtags. Draft approval and CSV export now enforce both limits and
reject invalid descriptions instead of silently truncating them. CSV uses UTF-8
text, comma delimiters, CRLF record endings, and standard CSV escaping for
commas, quotes, and multiline descriptions; spreadsheet colors/fonts are not
part of CSV.

## Confirmed destination vocabularies

The version 6 template contains exact display values followed by canonical
identifiers in parentheses. Destination mapping must preserve both parts for
upload. A future model may propose ordinary human-readable text, but Python
must perform the final deterministic match.

- **Category:** 319 values across Everything else, Kids, Men, and Women.
- **Brand:** 14,038 searchable values.
- **Condition:** `Brand new`, `Like new`, `Used - Excellent`, `Used - Fair`,
  and `Used - Good`.
- **Color:** `Black`, `Blue`, `Brown`, `Burgundy`, `Cream`, `Gold`, `Green`,
  `Grey`, `Khaki`, `Multi`, `Navy`, `Orange`, `Pink`, `Purple`, `Red`,
  `Silver`, `Tan`, `White`, and `Yellow`.
- **Age:** `00s`, `50s`, `60s`, `70s`, `80s`, `90s`, `Antique`, and
  `Modern`.
- **Style:** 32 confirmed values maintained in the versioned vocabulary data.
- **Location:** 664 confirmed values; selected by backend configuration, with
  `California, United States` as the user-authorized default.

Size is dependent on Category. The template maps 216 categories to 13 size
groups, covering general letter sizes, numbered clothing sizes, waist sizes,
bra sizes, adult footwear, children’s ages, children’s footwear, `One size`,
and `Other`. Category must be resolved before Size can be validated. A labeled
size that does not map cleanly must require review rather than being coerced.

## Confirmed Source vocabulary

`Source 1` and `Source 2` use the Depop Source attribute. The confirmed values
are:

- `Vintage`
- `Preloved`
- `Reworked / Upcycled`
- `Custom`
- `Handmade`
- `Deadstock`
- `Designer`
- `Repaired`

The classifier may propose up to two supported values, but each
proposal must retain evidence and remain subject to user review. It must not
infer a source merely to fill the optional second field.

## Implemented price suggestion

`listing_pricing.py` accepts only validated facts,
asks the existing hosted model for an estimated resale value in USD, and divides
that value by two in Python with half-up cent rounding. The prompt targets
$10–$15 for most ordinary items without a hard clamp. This is not measured
Depop average or sold-comparable data. The browser calls it after fact
validation, displays an editable Price field, and requires final approval.
Approval and CSV export revalidate positive decimal prices (up to two decimal
places) without another model call. Errors do not silently generate a fallback.
The CLI and garment-analysis schema are unchanged. Market-data research remains
out of scope; no address or location is included in the pricing model input.

## Internal draft fields

The requested title is not present in the supplied upload-template columns. Keep
it as a separate internal field named `draft_title` until the destination system
defines where it belongs.

The deterministic generator uses these patterns after final fact approval:

- Draft title: `{Brand} {Color 1} {item type}` (without Size).
- Description: `{draft_title}. Size: {Size}[ with a {Inseam} inseam].`

For example: `Levi's Blue jeans. Size: 32" with a 34" inseam.` Omit the inseam
clause when absent. Condition, Style, Age, and Color 2 remain separate facts and
CSV fields; they are not added to generated prose. Never use `Labeled waist size`.
These generation rules do not rewrite existing approved descriptions or human
edits. Title and description remain editable until separately approved.

The terminal flow performs that separate draft review. A non-empty title and
description must be explicitly approved before the status becomes
`listing_approved`. Every approved result is then automatically saved under a
random UUID filename in `approved_listings/`; exclusive creation prevents
overwriting an existing file.

Both strings must be generated only after their input facts have been validated.
If a required fact is missing, return a review requirement instead of inventing
text. Changes to generated wording or field priorities require an explicit project
decision; destination rules remain tied to the versioned template.

## Implemented backend boundary

`contracts.py` represents each known fact with `value`, `confidence`,
`provenance`, and `needs_review`. Unknown facts use a `null` value and zero
confidence. Conflicting claims retain their own value, confidence, and
provenance and require review.

The provider candidate fact names are `category`,
`item_type`, `brand`, `condition`, `size`, `primary_color`, `secondary_color`,
`source_1`, `source_2`, `age`, `style_1`, `style_2`, and `style_3`. These names
do not themselves enforce the template priorities above. A validated `inseam`
may additionally be derived from a structured jeans size label or supplied
during review.

Brand and size currently accept only `tag_photo` or `user_correction`
provenance. Condition accepts numbered item-photo evidence, `user_input`, or
`user_correction`. Other non-empty provenance roles remain representable so the
contract can accommodate additional photo roles later.

Raw `model_analysis`, `validated_facts`, and `listing_draft` remain separate
pipeline stages. `openai_vision.py` builds, sends, and parses strict raw candidate
analysis. `pipeline_service.py` orchestrates local checks, optional folder-role
detection, provider calls, and candidate validation without terminal I/O. A
tag role selection always uses the deterministic best model match. Conservative
confidence remains recorded, but low confidence no longer pauses for a user
confirmation in either CLI or localhost web mode.
`fact_validation.py` then blocks unreadable or uncertain tags,
validates provenance, preserves unknown/conflicting review state, and maps
controlled values exactly through `depop_vocab.py`, resolving Category before
Size. The CLI adapter runs these stages after local validation. It leaves
`validated_facts` and `listing_draft` null behind the tag gate. In `--review`
mode, it generates listing prose only after final fact approval and keeps the
draft separate for another explicit review.

The first successful hosted run confirmed that free-form candidate vocabulary is
not sufficient: a generic category such as `bottoms`, prose condition text, and
descriptive traits such as `five-pocket` cannot be uploaded as exact destination
values. The strict request schema therefore enumerates controlled Category,
Condition, Color, Source, Age, and Style values (with the documented `gray`
color alias), while Brand remains separately exact-mapped in Python. It also
limits Brand and Size to `tag_photo`, Condition and visible garment fields to
numbered item photos, and Source/Age to sent item or tag photos. Unknown model
values must be JSON `null`; literal placeholder strings are rejected before
validation.

For Style 1–3, the model should propose as many distinct exact confirmed styles
as the visible garment reasonably supports, up to three. Lower confidence alone
does not require an otherwise valid non-conflicting style to be blank, but the
model must not force unsupported descriptive traits into empty Style slots.

Human-edited facts must pass `review_validation.py` before approval. Required
final fields are Category, Item Type, Brand, Condition, Size, and Color 1.
Controlled fields are exact-mapped again, Size is checked only after Category,
Inseam accepts a numeric inch measurement, and optional fields may remain blank.
Approved facts are plain final values without per-field correction provenance.
The CLI exposes this boundary with `classifier.py --review`; it retries invalid
fields locally and requires explicit confirmation before returning an approved
result.

## Decision still needed

- Where `draft_title` maps in the destination system.
