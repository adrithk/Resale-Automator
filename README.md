# AI-Powered Resale Listing Assistant

An open-source project that will turn clothing photos and a required tag photo into an editable resale listing.

The planned workflow is:

1. Upload item and tag photos.
2. Verify that the tag is readable.
3. Generate validated listing facts, listing text, and photo-quality guidance.
4. Review and edit every field.
5. Approve the listing.
6. Export it or publish it through a marketplace adapter.

## Current implementation

The project is in the Python backend prototype stage. The implemented workflow
runs from the command line, with its reusable Python pipeline now separated
from the terminal adapter; a website and HTTP API remain separately authorized
future milestones.

The current backend milestone provides one Python command that accepts either
explicitly labeled photo paths or an unordered folder containing clothing
photos and a tag photo, then returns structured clothing information and draft
listing text or explains how to retake an unreadable tag photo.

The implemented pipeline is:

1. Validate the image files and require at least two item photos plus one tag photo. Folder mode discovers supported top-level images and identifies their roles first.
2. Use OpenCV for basic image-quality checks such as resolution, blur, darkness, brightness, and glare warnings.
3. Use a pretrained vision model to classify the garment and extract visible attributes and tag details. Training a custom clothing model is not part of the first milestone.
4. Stop when the tag is missing or unreadable instead of guessing tag-derived details.
5. Validate the extracted facts in Python, preserve uncertainty, and generate listing text only from the validated facts.
6. Store internal analysis results as JSON so lists, warnings, confidence, and provenance remain structured.
7. Add CSV only later as an export format for reviewed and approved listings.

## Selected vision model and backend status

The selected first production model is the hosted OpenAI API model
`gpt-5.6-luna`. The choice prioritizes low usage cost while retaining image
input and Structured Outputs. This is a hosted API decision: the project will
not run model weights locally. The exact model ID must be used rather than the
`gpt-5.6` alias, because that alias targets a different model tier.

The integration is **operational in the CLI**. `photo_role_detection.py`
provides the optional unordered-folder stage: neutral photo IDs prevent random
filenames from becoming role hints, and strict output predicts
front/back/detail/tag roles. It proceeds automatically when the selected tag's
conservative confidence is at least 60% and requests confirmation only below
that threshold. `openai_vision.py`
implements the provider boundary: it encodes JPEG, PNG, and WebP files as data URLs, labels
every item photo and the tag photo by role, builds a strict JSON Schema request
for `gpt-5.6-luna` with low reasoning effort and `store=False`, and defensively
parses structured responses. `fact_validation.py` converts readable-tag
candidates into project contracts, enforces provenance and unknown/conflict
rules, and performs exact Depop mapping with Category before Size. Labeled jeans
sizes such as `W36 L34` and `Waist × Length 32 × 34 inch` map by waist while
retaining the tag inseam as validated internal evidence for the description.
The hosted prompt asks the model to preserve both measurements in normalized
`W{waist} L{length}` form, while Python defensively accepts common `x` and `×`
tag formats. After local
validation and OpenCV checks succeed, `pipeline_service.py` calls the real
hosted API, captures non-secret request metadata, validates the candidates, and
returns the combined stage-separated result. `classifier.py` is a thin CLI
adapter that parses arguments, invokes this service, runs terminal-only reviews,
prints one JSON result, maps statuses to exit codes, and saves approved CLI
listings. In interactive review mode, listing-text generation remains a separate
step that runs only after final fact approval.

[`MODEL_INTEGRATION_PLAN.md`](MODEL_INTEGRATION_PLAN.md) contains the detailed
implementation sequence, acceptance criteria, and a prompt intended for a new
LLM context window. Official API references used by that plan are the
[GPT-5.6 Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[Images and vision guide](https://developers.openai.com/api/docs/guides/images-vision),
and [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).

The current prototype does not include a website, database, pricing system,
spreadsheet export, or marketplace automation. Pricing is planned as a later,
separate phase that will recommend a selling price from validated facts and
market-comparable data for user review.

The mapping from classifier facts to the supplied listing-template
columns is maintained in [`FIELD_CONTRACT.md`](FIELD_CONTRACT.md). It records
which fields are required, recommended, optional, deferred, excluded, or still
unresolved. Confirmed Depop template vocabularies are maintained separately
from image analysis and listing generation.

## Current structured-data contract

`PipelineResult` keeps local image analysis, raw model analysis, validated
facts, and listing generation as separate stages. Later stages remain `null`
when the command stops early; a successful reviewed run fills the applicable
stages before saving the result. A local input error has this shape:

```json
{
  "status": "input_error",
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

`pipeline_service.py` is terminal-independent: `PipelineService` accepts
ordinary explicit paths or already discovered folder-photo paths, returns plain
structured Python results, and keeps both hosted runners injectable for offline
tests. It never parses command-line arguments, prompts, prints, or exits. A
high-confidence folder-role result continues automatically; a lower-confidence
result returns `photo_role_review_required` with the strict role analysis,
metadata, confidence, and `next_step: review_photo_roles`. A future web adapter
can submit a selected `ResolvedPhotoRoles` object to classify without repeating
role detection. Fact review and listing-text review deliberately remain later,
separate interactions. `api.py` now adds a thin FastAPI adapter around this
service: health, role detection, explicit classification, corrected folder
classification, deterministic draft generation, and draft validation. Its
request models validate HTTP shape only; the existing Python service and review
validators remain the sole pipeline boundaries. There is still no frontend,
Blob storage, authentication, or Vercel deployment configuration.

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
remains `null` until final facts are approved in `--review` mode.

## Hosted vision boundary

The project pins the official OpenAI Python SDK in `requirements.txt`. Runtime
credentials are read only from `OPENAI_API_KEY`; the key is not a command
argument or part of result JSON. `openai_vision.py` keeps the model ID,
reasoning effort, timeout, retry limit, image detail, developer instruction,
schema, image encoding, response parser, and transient-only retry loop explicit
and testable. The optional role request shares those authentication, timeout,
retry, secret-safety, model, reasoning, and storage boundaries. Ordinary tests
use injected SDK/runner doubles without network
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

This mapping layer is called by the CLI after a readable tag passes the gate.
It uses only Python's standard library; the runtime does not read the source
spreadsheet.

The first successful hosted smoke run showed that generic category labels,
free-form conditions, and descriptive traits do not reliably map downstream.
The request schema now enumerates the controlled destination vocabularies
(excluding the large Brand list), restricts field provenance to the relevant
sent photo roles, and requires actual JSON `null` for unknown values. Python
still independently rejects invalid provenance, placeholder strings, and any
unsupported mapping.

Review-flagged Age values are left blank unless confirmed without a review flag;
the vision instruction prohibits appearance-based age inference. Exact mapped
Style values may be retained despite a low-confidence review flag when there is
no conflicting evidence. The model is asked to propose up to three distinct
exact Depop styles when the garment visibly supports them; it must still leave
unsupported slots blank rather than convert construction traits into styles.

`review_validation.py` is the final boundary for human-edited facts. It accepts
plain final values, resolves Category before category-dependent Size, maps every
controlled field and Brand exactly, treats a bare numeric Size in a jeans
category as waist inches (for example, `32` becomes Depop's canonical `32"`),
normalizes a numeric Inseam measurement, allows optional blanks, and rejects
invalid edits without fuzzy correction. An approved result deliberately does
not carry per-field correction provenance.

`listing_generation.py` defensively revalidates approved facts and then creates
an editable draft title and description deterministically. It uses only approved
values, excludes size from the title, includes size and a validated inseam in
the description, omits blank optional facts, and does not call a model or
perform an export or marketplace action.

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

Alternatively, place three or more unordered photos directly inside one folder
and run:

```bash
python classifier.py \
  --photo-folder "/Users/adrithk/Developer/Resale Automator/examplephotos/clothing photos" \
  --review
```

Folder mode ignores unsupported files and does not recurse into subfolders. It
sorts discovered images only to assign stable neutral IDs, then uses image
content—not filenames—to predict front, back, detail, and tag roles. If the
selected tag's conservative confidence is 60% or higher, it proceeds without a
role prompt. Below 60%, it displays the prediction and asks you to accept it or
select the correct tag photo by number. Every other folder image becomes an item
photo, with front and back predictions used only for consistent ordering. The
same backend threshold is intended for the future website. Folder mode makes two
hosted API requests: one for roles and one for garment analysis. Explicit
`--item`/`--tag` input remains a one-request path. Do not combine
`--photo-folder` with `--item` or `--tag`.

Add `--review` to continue directly into terminal editing after classification.
Each prompt accepts Enter to keep the displayed value, `-` to clear it, or a
replacement value. Invalid edits are explained and re-prompted locally without
another hosted request. For jeans, a bare waist number such as `32` is accepted
and stored canonically as `32"`. After fact approval, it generates a title and description
and asks for a second review and approval. The final result uses
`status: listing_approved`, plain canonical `approved_facts`, and an approved
`listing_draft`; `q` cancels review.

After final listing approval, the CLI automatically creates `approved_listings/`
beside `classifier.py` and saves the complete result as
`approved-listing-<random UUID>.json`. Exclusive file creation prevents an
existing file from being overwritten. The absolute path appears in `saved_to`,
and the same final JSON is also printed to the terminal. Generated listing files
remain local and are ignored by Git; only `approved_listings/.gitkeep` is
tracked so a fresh checkout contains the output directory.

Do not place the key in source files or pass it as a CLI argument. Local input
errors exit with code 1 and never call the provider. Missing/rejected API
configuration exits 2, model/provider errors exit 3, and a tag-retake result
exits 4. An automatic-save failure exits 5 with a secret-safe structured error.
`review_required` and `facts_validated` are successful command results.

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
