# Listing Field Contract

Status: editable. The destination vocabularies below were confirmed from Depop
bulk-listing template version 6. Python structures now enforce the universal
provenance and uncertainty rules described below. The hosted-model boundary
constrains candidate output to the documented schema, and the candidate
validation layer applies the readable-tag gate and exact destination mapping.
Complete-listing readiness decisions remain unresolved and are not enforced.

The hosted integration is implemented and covered by offline fixtures and
mocked networking. Its optional live smoke tests use user-supplied photos and
are skipped by default; they verify this contract but do not change it.

The implemented vision-model integration uses hosted `gpt-5.6-luna`, but model
selection does not change this contract: model output is candidate evidence,
not a validated listing value. Python must continue to enforce provenance,
unknown values, conflicts, the readable-tag gate, and exact destination
mapping. See `MODEL_INTEGRATION_PLAN.md` for the implementation boundary.

This document maps the supplied upload-template columns to the first backend
milestone. It is the reference for deciding what the classifier extracts, what
the user supplies, and what stays out of scope.

## Requirement labels

- **Required**: needed before a listing draft can be considered complete.
- **Recommended**: useful when supported by evidence, but may be omitted.
- **Optional**: include only when clearly available and useful.
- **Deferred**: belongs to a later system phase rather than the current
  classifier milestone.
- **Excluded**: intentionally outside the first milestone.
- **Unresolved**: meaning or destination requirements must be clarified.

## Template-field decisions

| Template field | First milestone | Allowed source | Reason or rule |
| --- | --- | --- | --- |
| Description | Required | Listing generator using validated facts only | Must be succinct and reviewed by the user. |
| Category | Required | Vision model, then exact Depop mapping and user review | Must map to one of the 319 template values, including its canonical identifier. |
| Price | Deferred | Future pricing system using validated facts and market-comparable data | Recommend a reasonable selling price in a later phase and require user review; do not guess a price during classification. |
| Brand | Required | Readable tag, or explicit user correction | Never guess a brand from weak visual evidence. |
| Condition | Required | Visible garment evidence, then exact Depop mapping and user review | Must use one of the five confirmed values; state only visible condition and do not infer hidden defects. |
| Size | Required | Readable tag, or explicit user correction | Map jeans labels such as `W36 L34`, `32x34`, or `Waist × Length 32 × 34 inch` by waist only after Category resolves; during review, a bare number such as `32` means waist inches and is stored as `32"`. Retain the parsed inseam for description wording. |
| Inseam (internal) | Optional | Readable tag, or explicit user correction | Retained tag evidence such as `34"`; it is not a Depop upload field and will be used only by a future listing-description step. |
| Color 1 | Required | Garment photos, then exact Depop mapping and user review | Primary visible color mapped to one of the 19 confirmed values. |
| Color 2 | Recommended | Garment photos, then exact Depop mapping and user review | Include only when a meaningful secondary color maps to a confirmed value. |
| Source 1 | Recommended | Item/tag evidence or user input, then review | First applicable Depop source value from the confirmed vocabulary below. |
| Source 2 | Optional | Item/tag evidence or user input, then review | Second applicable Depop source value; omit when only one applies. |
| Age | Recommended | Explicit tag/item evidence or user input, then exact Depop mapping | Leave blank when review-flagged; never infer an era from styling or construction. |
| Style 1 | Recommended | Garment photos, then exact Depop mapping | Primary style tag from the 32 confirmed values; an exact non-conflicting value may be retained despite low confidence. |
| Style 2 | Optional | Garment photos, then exact Depop mapping | Additional confirmed style tag; an exact non-conflicting value may be retained despite low confidence. |
| Style 3 | Optional | Garment photos, then exact Depop mapping | Additional confirmed style tag; an exact non-conflicting value may be retained despite low confidence. |
| Location | Deferred | User or future inventory settings | Operational inventory data selected from the 664 template values, not a classifier fact. |
| Picture Hero URL | Deferred | Future upload/storage step | The current CLI uses local item-photo paths; unordered folder mode predicts front/back/detail roles, but URL creation comes later. |
| Picture 2 URL | Deferred | Future upload/storage step | At least two local item photos are required now; explicit paths or confirmed unordered-folder roles are accepted, while URL creation comes later. |
| Picture 3 URL | Deferred | Future upload/storage step | Optional additional listing photo. |
| Picture 4 URL | Deferred | Future upload/storage step | Optional additional listing photo. |
| Picture 5 URL | Deferred | Future upload/storage step | Optional additional listing photo. |
| Picture 6 URL | Deferred | Future upload/storage step | Optional additional listing photo. |
| Picture 7 URL | Deferred | Future upload/storage step | Optional additional listing photo. |
| Picture 8 URL | Deferred | Future upload/storage step | Optional additional listing photo. |
| Domestic Shipping price | Excluded | User or future shipping settings | Shipping prices are explicitly outside the first milestone. |
| International Shipping price | Excluded | User or future shipping settings | Shipping prices are explicitly outside the first milestone. |
| SKU | Excluded | None | The user confirmed that SKU is not necessary. |

The separately identified tag photo is an analysis input. It must not be placed
into a public picture URL field automatically.

The template guide permits uploading listing information without photos and
adding photos later while completing the resulting Depop drafts. The picture
URL fields therefore remain deferred and are not classifier requirements.

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
- **Location:** 664 confirmed values; selection remains a later user or
  inventory-setting responsibility.

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

The classifier may eventually propose up to two supported values, but each
proposal must retain evidence and remain subject to user review. It must not
infer a source merely to fill the optional second field.

## Deferred pricing system

Price is deferred rather than permanently excluded. A later pricing phase
should recommend a reasonable selling price using validated garment facts,
condition, and comparable market data such as relevant sold listings. Asking
prices should not be treated as proof of market value, and the user must review
and approve the recommendation. Pricing logic and market-data access are kept
out of the current classifier milestone so incomplete or unvalidated facts do
not create a misleading price.

## Internal draft fields

The requested title is not present in the supplied upload-template columns. Keep
it as a separate internal field named `draft_title` until the destination system
defines where it belongs.

The provisional succinct patterns are:

- Draft title: `{Brand} {Color 1} {item type}` (do not include Size)
- Description: `{Brand} {item type} in {Color 1}[ and {Color 2}]. {Condition}. Labeled size {Size}.`

The implemented deterministic generator follows these patterns after final fact
approval, adds a validated Inseam to the size sentence when present, and may add
confirmed Style and Age sentences. Blank optional facts are omitted. The title
and description remain editable drafts until separately approved.

The terminal flow performs that separate draft review. A non-empty title and
description must be explicitly approved before the status becomes
`listing_approved`. Every approved result is then automatically saved under a
random UUID filename in `approved_listings/`; exclusive creation prevents
overwriting an existing file.

Both strings must be generated only after their input facts have been validated.
If a required fact is missing, return a review requirement instead of inventing
text. Description wording and field priorities may be revised when the actual
upload-system requirements are confirmed.

## Implemented Phase III boundary

`contracts.py` represents each known fact with `value`, `confidence`,
`provenance`, and `needs_review`. Unknown facts use a `null` value and zero
confidence. Conflicting claims retain their own value, confidence, and
provenance and require review.

The currently implemented candidate internal fact names are `category`,
`item_type`, `brand`, `condition`, `size`, `primary_color`, `secondary_color`,
`source_1`, `source_2`, `age`, `style_1`, `style_2`, and `style_3`. These names
do not themselves enforce the template priorities above.

Brand and size currently accept only `tag_photo` or `user_correction`
provenance. Condition accepts numbered item-photo evidence, `user_input`, or
`user_correction`. Other non-empty provenance roles remain representable so the
contract can accommodate additional photo roles later.

Raw `model_analysis`, `validated_facts`, and `listing_draft` remain separate
pipeline stages. `openai_vision.py` builds, sends, and parses strict raw candidate
analysis. `fact_validation.py` then blocks unreadable or uncertain tags,
validates provenance, preserves unknown/conflicting review state, and maps
controlled values exactly through `depop_vocab.py`, resolving Category before
Size. The CLI now runs these stages after local validation. It leaves
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

## Decisions still needed

Before enforcing complete-listing readiness, confirm:

1. Whether Size is always required or can remain `unknown` after user review.
2. Where `draft_title` maps in the destination system.
