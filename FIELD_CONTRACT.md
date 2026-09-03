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
| Size | Required | Readable tag, or explicit user correction | Preserve the labeled size and map it only after Category selects the applicable size vocabulary. |
| Color 1 | Required | Garment photos, then exact Depop mapping and user review | Primary visible color mapped to one of the 19 confirmed values. |
| Color 2 | Recommended | Garment photos, then exact Depop mapping and user review | Include only when a meaningful secondary color maps to a confirmed value. |
| Source 1 | Recommended | Item/tag evidence or user input, then review | First applicable Depop source value from the confirmed vocabulary below. |
| Source 2 | Optional | Item/tag evidence or user input, then review | Second applicable Depop source value; omit when only one applies. |
| Age | Recommended | Tag/item evidence or user input, then exact Depop mapping and review | Use one of the eight confirmed values or `unknown`; never guess an era or age. |
| Style 1 | Recommended | Garment photos, then exact Depop mapping and user review | Primary style tag from the 32 confirmed values. |
| Style 2 | Optional | Garment photos, then exact Depop mapping and user review | Additional confirmed style tag only when well supported. |
| Style 3 | Optional | Garment photos, then exact Depop mapping and user review | Additional confirmed style tag only when well supported. |
| Location | Deferred | User or future inventory settings | Operational inventory data selected from the 664 template values, not a classifier fact. |
| Picture Hero URL | Deferred | Future upload/storage step | The current CLI uses a local hero-photo path; URL creation comes later. |
| Picture 2 URL | Deferred | Future upload/storage step | At least two local item photos are required now; URL creation comes later. |
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

- Draft title: `{Color 1} {Brand} {item type} — Size {Size}`
- Description: `{Brand} {item type} in {Color 1}[ and {Color 2}]. {Condition}. Labeled size {Size}.`

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
`validated_facts` null behind the tag gate and always leaves `listing_draft`
null; no integration layer generates listing prose.

## Decisions still needed

Before enforcing complete-listing readiness, confirm:

1. Whether Size is always required or can remain `unknown` after user review.
2. Where `draft_title` maps in the destination system.
