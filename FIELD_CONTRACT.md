# Listing Field Contract

Status: provisional and editable. Phase III Python structures enforce only the
confirmed universal provenance and uncertainty rules described below; template
priorities and unresolved vocabularies are not enforced as listing-readiness
rules.

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
| Category | Required | Vision model, then Python validation and user review | Uses an editable category taxonomy that is still to be defined. |
| Price | Deferred | Future pricing system using validated facts and market-comparable data | Recommend a reasonable selling price in a later phase and require user review; do not guess a price during classification. |
| Brand | Required | Readable tag, or explicit user correction | Never guess a brand from weak visual evidence. |
| Condition | Required | Visible garment evidence, then user review | State only visible condition; do not infer hidden defects. |
| Size | Required | Readable tag, or explicit user correction | Preserve the exact labeled size and never guess it. |
| Color 1 | Required | Garment photos, then user review | Primary visible color. |
| Color 2 | Recommended | Garment photos, then user review | Include only when a meaningful secondary color is visible. |
| Source 1 | Recommended | Item/tag evidence or user input, then review | First applicable Depop source value from the confirmed vocabulary below. |
| Source 2 | Optional | Item/tag evidence or user input, then review | Second applicable Depop source value; omit when only one applies. |
| Age | Recommended | Tag/item evidence or user input, then review | Use `unknown` rather than guessing an era or age. |
| Style 1 | Recommended | Garment photos, then user review | Primary style tag from an editable vocabulary. |
| Style 2 | Optional | Garment photos, then user review | Additional style tag only when well supported. |
| Style 3 | Optional | Garment photos, then user review | Additional style tag only when well supported. |
| Location | Deferred | User or future inventory settings | Operational inventory data, not a classifier fact. |
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

The candidate internal fact names are `category`, `item_type`, `brand`,
`condition`, `size`, `primary_color`, `secondary_color`, `age`, `style_1`,
`style_2`, and `style_3`. These names do not themselves enforce the provisional
template priorities above.

Brand and size currently accept only `tag_photo` or `user_correction`
provenance. Condition accepts numbered item-photo evidence, `user_input`, or
`user_correction`. Other non-empty provenance roles remain representable so the
contract can accommodate additional photo roles later.

Raw `model_analysis`, `validated_facts`, and `listing_draft` remain separate
pipeline stages. The current CLI leaves all three as `null`; Phase III does not
decide tag readability or generate listing text.

## Decisions still needed

Before enforcing this contract in Python, confirm:

1. The exact allowed values for Category.
2. The exact allowed values for Condition.
3. Whether Size is always required or can be `unknown` after user review.
4. The allowed Age and Style vocabularies.
5. Which picture URL fields the destination upload system requires.
6. Where `draft_title` maps in the destination system.
