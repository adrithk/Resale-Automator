# AI-Powered Resale Listing Assistant

An open-source project that will turn clothing photos and a required tag photo into an editable resale listing.

The planned workflow is:

1. Upload item and tag photos.
2. Verify that the tag is readable.
3. Generate listing details and photo recommendations.
4. Review and edit every field.
5. Approve the listing.
6. Export it or publish it through a marketplace adapter.

## Initial implementation direction

The project is in the early Python backend prototype stage. The current
implementation runs from the command line in VS Code; a website will come
later.

The first milestone is one Python command that accepts multiple clothing photos and a separately identified tag photo, then either returns structured clothing information and draft listing text or explains how to retake an unreadable tag photo.

The initial pipeline will be:

1. Validate the image files and require at least two item photos plus one tag photo.
2. Use OpenCV for basic image-quality checks such as resolution, blur, darkness, brightness, and glare warnings.
3. Use a pretrained vision model to classify the garment and extract visible attributes and tag details. Training a custom clothing model is not part of the first milestone.
4. Stop when the tag is missing or unreadable instead of guessing tag-derived details.
5. Validate the extracted facts in Python, preserve uncertainty, and generate listing text only from the validated facts.
6. Store internal analysis results as JSON so lists, warnings, confidence, and provenance remain structured.
7. Add CSV only later as an export format for reviewed and approved listings.

## Selected vision model and next milestone

The selected first production model is the hosted OpenAI API model
`gpt-5.6-luna`. The choice prioritizes low usage cost while retaining image
input and Structured Outputs. This is a hosted API decision: the project will
not run model weights locally. The exact model ID must be used rather than the
`gpt-5.6` alias, because that alias targets a different model tier.

The integration is **operational in the CLI**. `openai_vision.py` implements the
provider boundary: it encodes JPEG, PNG, and WebP files as data URLs, labels
every item photo and the tag photo by role, builds a strict JSON Schema request
for `gpt-5.6-luna` with low reasoning effort and `store=False`, and defensively
parses structured responses. `fact_validation.py` converts readable-tag
candidates into project contracts, enforces provenance and unknown/conflict
rules, and performs exact Depop mapping with Category before Size. After local
validation and OpenCV checks succeed, `classifier.py` calls the real hosted API,
captures non-secret request metadata, validates the candidates, and returns the
combined stage-separated result. Listing-text generation remains a later,
separate step.

[`MODEL_INTEGRATION_PLAN.md`](MODEL_INTEGRATION_PLAN.md) contains the detailed
implementation sequence, acceptance criteria, and a prompt intended for a new
LLM context window. Official API references used by that plan are the
[GPT-5.6 Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[Images and vision guide](https://developers.openai.com/api/docs/guides/images-vision),
and [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).

The first prototype will not include a website, database, pricing system,
spreadsheet export, or marketplace automation. Pricing is planned as a later,
separate phase that will recommend a selling price from validated facts and
market-comparable data for user review.

The mapping from classifier facts to the supplied listing-template
columns is maintained in [`FIELD_CONTRACT.md`](FIELD_CONTRACT.md). It records
which fields are required, recommended, optional, deferred, excluded, or still
unresolved. Confirmed Depop template vocabularies are maintained separately
from image analysis and listing generation.

## Current structured-data contract

Phase III adds standard-library Python contracts without calling a vision model
or generating listing text. Command results now keep the pipeline stages
separate:

```json
{
  "status": "quality_checks_complete",
  "image_analysis": {},
  "model_analysis": null,
  "validated_facts": null,
  "listing_draft": null,
  "warnings": []
}
```

For compatibility with the Phase I/II command output, successful results also
retain `item_photos` and `tag_photo` as top-level aliases of the values inside
`image_analysis`.

`contracts.py` can represent the candidate clothing facts, their confidence,
provenance, review state, explicit unknown values, and conflicting evidence. It
currently enforces only confirmed universal rules:

- Confidence is between 0 and 1.
- Known values have provenance; unknown values use JSON `null` rather than a
  guessed placeholder.
- Brand and labeled size come from `tag_photo` or `user_correction`.
- Condition comes from visible item-photo evidence or explicit user input.
- Conflicting evidence requires review.
- `source_1` and `source_2` are represented independently.

`fact_validation.py` applies these rules to model candidates. Unreadable or
uncertain tags stop before validated facts and produce retake instructions.
Readable candidates are mapped exactly for Category, Brand, Condition, Color,
Source, Age, Style, and category-dependent Size; invalid or unmapped evidence
becomes an explicit review issue while raw analysis remains unchanged. The CLI
populates `model_analysis` and operational `model_metadata`; it populates
`validated_facts` only after a readable tag passes the gate. `listing_draft`
remains `null`.

## Hosted vision boundary

The project pins the official OpenAI Python SDK in `requirements.txt`. Runtime
credentials are read only from `OPENAI_API_KEY`; the key is not a command
argument or part of result JSON. `openai_vision.py` keeps the model ID,
reasoning effort, timeout, retry limit, image detail, developer instruction,
schema, image encoding, response parser, and transient-only retry loop explicit
and testable. Ordinary tests use injected SDK/runner doubles without network
access. Successful results record response ID, returned model ID, input/output/
total tokens, latency, and attempt count; no API prices are hard-coded.

## Depop destination vocabulary

`depop_vocab.py` provides deterministic matching against a versioned snapshot
of Depop bulk-listing template version 6. The snapshot includes 319 categories,
14,038 brands, five conditions, 19 colors, eight sources, eight ages, 32 styles,
664 locations, and the template's category-dependent size groups.

The mapper keeps a human-readable label separate from its canonical identifier
and exact upload value. It accepts labels, identifiers, exact upload values, and
explicitly documented aliases such as `gray` to `Grey`. It does not use fuzzy
matching: missing or ambiguous values require review instead of being guessed.
Size validation requires a resolved Category first.

This mapping layer is available to later pipeline stages but is not yet called
by the current image-quality CLI. It uses only Python's standard library; the
runtime does not read the source spreadsheet.

## Run the current prototype

Create an isolated Python environment and install the recorded dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the input-validation command with two item photos and one tag photo:

```bash
export OPENAI_API_KEY="your-api-key"
python classifier.py \
  --item path/to/front.jpg \
  --item path/to/back.jpg \
  --tag path/to/tag.jpg
```

Do not place the key in source files or pass it as a CLI argument. Local input
errors exit with code 1 and never call the provider. Missing/rejected API
configuration exits 2, model/provider errors exit 3, and a tag-retake result
exits 4. `review_required` and `facts_validated` are successful command results.

Run the automated tests:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Ordinary tests are deterministic, offline, and free. The two live smoke tests
are skipped unless explicitly enabled. To authorize those two billed calls,
provide at least two item photos plus separate readable and intentionally
unreadable tag photos, then run:

```bash
export OPENAI_API_KEY="your-api-key"
export RESALE_RUN_LIVE_SMOKE=1
export RESALE_LIVE_ITEM_PHOTOS="/absolute/front.jpg:/absolute/back.jpg"
export RESALE_LIVE_READABLE_TAG_PHOTO="/absolute/readable-tag.jpg"
export RESALE_LIVE_UNREADABLE_TAG_PHOTO="/absolute/unreadable-tag.jpg"
.venv/bin/python -m unittest tests.test_live_smoke -v
```

On macOS and Linux, separate additional item-photo paths with `:`. The live
test first runs the same local validation as the CLI, then asserts the returned
model ID, schema validity, latency, token usage, and tag-gate behavior. It does
not print or store the API key and does not commit photos or responses.

## Local image-quality stage

The command currently accepts JPEG, PNG, and WebP files. For each item and tag
photo it reports:

- Width, height, and megapixels
- Resolution status
- Laplacian-variance blur score and blur status
- Average grayscale brightness and lighting status
- Grayscale contrast score and contrast status
- Percentage of extremely bright, low-saturation pixels and possible-glare status

The initial warning thresholds are deliberately visible and provisional:

- Shortest image edge below 1,000 pixels: low-resolution warning
- Blur score below 25: possible-blur warning
- Brightness below 45: too-dark warning
- Brightness above 210: too-bright warning
- Contrast below 20: low-contrast warning
- Possible-glare area at or above 5%: possible-glare warning

These measurements are heuristics. They produce review warnings and retake
instructions; they do not determine whether a tag is readable or what garment
is pictured. The hosted vision stage makes candidate observations, after which
Python remains authoritative for tag gating, provenance, and mapping.

## Keeping project context current

Implementation work should update this README when it changes the architecture,
workflow, scope, dependencies, supported formats, commands, thresholds, or safety
boundaries. If an explicitly approved implementation changes an earlier decision,
the new decision and its reason should be recorded rather than leaving the code and
documentation inconsistent. `AGENTS.md` contains the durable working rules that
future coding agents must follow.
