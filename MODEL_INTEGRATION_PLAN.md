# GPT-5.6 Luna Integration Plan

Status: implemented, including unordered photo-role detection, a web-safe Python
service boundary, a thin FastAPI adapter, terminal review, listing generation,
and automatic local JSON saving. No frontend, Blob storage, authentication, or
deployment configuration exists.

This document is the implementation record for the hosted-vision milestone. It
records the decisions, boundaries, sequence, tests, and completion criteria used
to connect the Python command-line prototype to the real hosted OpenAI vision
API. The integration described here now exists and has since been extended with
review and listing generation. Pricing, destination export, a frontend, and
marketplace automation remain outside the implemented scope.

An optional unordered-folder pre-stage is implemented in
`photo_role_detection.py`. It sends each supported top-level image under a
neutral ID, uses the same exact hosted model and operational boundaries, and
returns strict front/back/detail/tag assignments with confidence and independent
tag likelihood. Python verifies exact one-time coverage of every supplied ID,
proposes one tag deterministically, and calculates conservative selected-tag
confidence as the lower of assignment confidence and tag likelihood. A result
at or above 60% proceeds automatically; only a lower result requires user
confirmation or numbered correction before garment analysis. This policy is the
future website boundary as well. The original explicit `--item`/`--tag` path
remains available.

## Confirmed decisions

- Use the hosted OpenAI API; do not run model weights locally.
- Use the exact model ID `gpt-5.6-luna`. Do not use the `gpt-5.6` alias and do
  not silently substitute another provider or model.
- Use the Responses API with image inputs and strict Structured Outputs backed
  by JSON Schema.
- Start with `reasoning.effort` set to `low`, but keep it as one clearly named
  configuration value so representative evaluation can compare `none` later.
- Set `store=False` for requests unless a later requirement explicitly needs
  stored responses.
- Runtime execution uses the real API. Tests may mock the network boundary and
  load saved JSON response fixtures; there is no fake runtime provider.
- Keep OpenCV quality analysis, raw model analysis, validated facts, Depop
  mapping, listing generation, export, and marketplace automation as separate
  stages.
- Do not add pricing, a database, CSV/spreadsheet export, a website, browser
  automation, or listing publication in this milestone.
- The first successful hosted run is retained only as a sanitized regression
  fixture. It revealed that generic category labels and free-form controlled
  fields cause review requirements despite a successful API response. The
  strict schema now enumerates controlled values, uses field-specific sent-role
  provenance, and rejects literal placeholder strings; no additional live call
  was made for this hardening work.

Official references:

- [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Images and vision](https://developers.openai.com/api/docs/guides/images-vision)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

Pricing is deliberately not hard-coded into the application or tests. Provider
pricing can change; record API usage and calculate costs outside the validation
contract when needed.

## Current implementation to preserve

- `pipeline_service.py` accepts either already assigned paths or already
  discovered unordered folder paths, runs the terminal-independent OpenCV,
  role-detection, hosted-analysis, and validation stages, and returns structured
  results with injectable provider runners. Low-confidence roles return a
  resumable `photo_role_review_required` state instead of cancellation.
- `classifier.py` accepts either at least two explicitly identified item photos
  plus one tag photo, or three or more unordered top-level folder images; it is
  the thin terminal adapter for argument parsing, prompts, one JSON print, exit
  codes, and local approved-listing persistence.
- `api.py` supplies typed HTTP request boundaries for health, role detection,
  explicit and confirmed-folder classification, deterministic draft generation,
  and draft validation. It delegates to existing Python behavior and does not
  yet accept uploads, persist approved listings, or configure Vercel.
- `photo_role_detection.py` assigns neutral IDs, predicts image roles, and
  automatically accepts the selected tag at 60% conservative confidence or
  requests correction below that threshold.
- `contracts.py` separates `image_analysis`, `model_analysis`,
  `validated_facts`, and `listing_draft` in `PipelineResult`.
- `depop_vocab.py` performs deterministic matching against
  `data/depop_template_v6.json` and never fuzzy-guesses missing or ambiguous
  destination values.
- `FIELD_CONTRACT.md` defines field priority and provenance. Brand and size are
  tag-derived; condition requires visible item-photo evidence or explicit user
  input.
- `review_validation.py` exact-validates human edits, including canonical
  numeric waist and inseam handling for jeans.
- `listing_generation.py` creates deterministic editable listing text only from
  approved facts; the title excludes size and the description retains it.
- A reviewed and approved listing is saved automatically under a unique JSON
  filename in `approved_listings/`. Generated JSON files remain local and
  ignored by Git.

## Implemented end-to-end behavior

1. Parse and validate either explicit photo roles or an unordered photo folder.
2. In folder mode, make a strict role-detection request using neutral photo IDs.
   Continue automatically at 60% conservative tag confidence or ask for a tag
   correction below that threshold.
3. Run OpenCV quality checks and preserve their warnings.
4. If local input is invalid, return a structured input error without calling
   the garment-analysis API.
5. Build a multimodal request containing every resolved item photo and the tag
   photo under unambiguous sent roles.
6. Ask GPT-5.6 Luna for schema-constrained candidate analysis. The model first
   reports tag readability and preserves visible jeans waist/length pairs.
7. If the tag is `unreadable` or `uncertain`, stop with a structured
   `tag_retake_required` result. Preserve `image_analysis` and `model_analysis`,
   leave `validated_facts` and `listing_draft` as `null`, and include actionable
   retake instructions. Never guess brand or size.
8. If the tag is readable, convert candidate facts into the existing contract
   types and apply provenance validation.
9. Map destination-controlled values through `depop_vocab.py`. Resolve Category
   before Size. An unknown, ambiguous, invalid, conflicting, or unmapped value
   must require review rather than being coerced.
10. Without `--review`, return structured candidate and validated data. With
    `--review`, allow keep/edit/clear operations and exact-validate the final
    facts locally without another model call.
11. Generate and separately review a deterministic title and description, then
    require explicit approval.
12. Save each approved result automatically as a unique local JSON file. Do not
    generate a price, export destination rows, or perform marketplace actions.

Post-smoke hardening retains this order at both boundaries: the provider schema
requires an exact category upload value (or `null`), then Python maps Category
before it attempts Size. Unsupported Style descriptions remain explicit unknown
review facts; they are not reinterpreted as Style values.

For resolved jeans categories, structured tag labels such as `W36 L34`,
`32x34`, and `Waist × Length 32 × 34 inch` are parsed deterministically into
the exact Depop waist size and internal validated inseam for description
wording. The hosted prompt explicitly requests normalized `W{waist} L{length}`
output and prohibits dropping either visible measurement. Review-flagged Age stays
blank instead of inferring `Modern`; exact non-conflicting Style values may be
retained even when the model reports low confidence.

The hosted instruction asks for up to three distinct exact Style candidates
when supported by visible garment evidence. Lower confidence alone may still
produce a candidate, while unsupported descriptive traits and unused slots stay
`null`; Python remains the exact-mapping boundary.

The terminal-review stage uses `review_validation.py` as a provider-independent
final boundary. Human edits cannot become approved facts until
required values, exact dropdown/Brand mapping, Category-dependent Size, and
numeric Inseam have all passed deterministic validation.
For a resolved jeans category, a bare numeric human Size edit is treated as a
waist measurement and normalized to Depop's quoted inch value; other category
size vocabularies remain unchanged.
`classifier.py --review` provides that interactive terminal boundary. It
re-prompts invalid fields locally, requires explicit approval, and returns plain
canonical approved facts before invoking the separate listing generator.

The listing stage is implemented in `listing_generation.py`.
It revalidates approved facts and deterministically builds editable title and
description text. Size is excluded from the title but retained in the
description along with validated Inseam; blank optional facts are omitted. This
does not make another model request.
The terminal flow separately reviews and approves the non-empty generated title
and description. Every approved result is automatically saved to a random,
UUID-named JSON file in `approved_listings/`, using exclusive creation so
existing data is never overwritten.

Offline regressions cover each controlled vocabulary family, the documented
`gray` alias, generic-category rejection, tag-only Brand/Size provenance,
item-only Condition/visible-field provenance, and actual JSON `null` handling.

## Proposed model-analysis schema

Represent the response with a strict JSON Schema. All objects must set
`additionalProperties` to `false`, all declared keys must be required where the
OpenAI Structured Outputs subset requires that, and optional semantic values
must use explicit `null` unions.

Top-level fields:

- `schema_version`: initially `1`.
- `tag_readability`:
  - `status`: `readable`, `unreadable`, or `uncertain`.
  - `confidence`: number from 0 through 1.
  - `issues`: list of concise visible problems.
  - `retake_instructions`: list of actionable instructions; empty only when
    readable.
- `facts`: one object for each candidate field:
  - `category`
  - `item_type`
  - `brand`
  - `condition`
  - `size`
  - `primary_color`
  - `secondary_color`
  - `source_1`
  - `source_2`
  - `age`
  - `style_1`
  - `style_2`
  - `style_3`
- `warnings`: model-level warnings not already represented by OpenCV.

Each candidate fact should contain:

- `value`: string or `null`.
- `confidence`: number from 0 through 1; use zero when `value` is `null`.
- `provenance`: an array containing only supplied photo roles.
- `needs_review`: boolean.
- `evidence`: a concise description of what is visibly supporting the value,
  or `null` when the value is unknown.
- `conflicts`: a list of competing claims, each containing `value`,
  `confidence`, and `provenance`.

Do not put the full 14,038-brand vocabulary or all destination options in the
model prompt. Ask for literal visible facts, then use local deterministic
matching. The model may be told the small controlled lists for condition,
color, source, age, and style if doing so remains within a concise prompt;
Python is still authoritative.

## Prompt rules for the vision request

The developer instruction sent to the model must say, in substance:

- Analyze only the supplied garment and tag images.
- Treat image-role labels as authoritative.
- Do not infer brand or labeled size from item appearance; use only
  `tag_photo`.
- Mark the tag unreadable or uncertain when the relevant text cannot be read
  confidently.
- Preserve a visible jeans waist/length pair and normalize it as
  `W{waist} L{length}` rather than dropping either measurement.
- Describe only visible condition; do not infer hidden defects.
- Propose only exact supported Style values, up to three when visibly supported,
  and do not infer Age from appearance.
- Use `null`, zero confidence, and review flags instead of guessing.
- Preserve conflicts when different photos disagree.
- Return candidate evidence only, not listing prose, prices, or upload actions.

Keep prompt text and JSON Schema in testable module-level constants or builder
functions rather than embedding a large literal inside CLI control flow.

## Configuration and dependency requirements

- Add the official OpenAI Python SDK to `requirements.txt`, using a reviewed
  compatible version and following the repository's existing dependency style.
- Read the API key only from `OPENAI_API_KEY`. Never accept it as a CLI
  argument, print it, serialize it, or commit an `.env` file.
- Use a project-specific environment variable such as
  `RESALE_VISION_MODEL` only if model override is needed for controlled
  evaluation. Its default must be `gpt-5.6-luna`.
- Keep reasoning effort, timeout, and retry count as explicit constants or
  narrowly scoped configuration. Use bounded retries only for transient API
  failures; do not retry schema or validation failures indefinitely.
- Detect the MIME type from the already validated extension, encode local image
  bytes safely for the API-supported image-input form, and retain the original
  role and resolved path in local analysis.
- Give the tag image sufficient detail for text reading. Make image detail a
  named choice so token cost and accuracy can be evaluated rather than hidden.
- Capture response ID, model ID, input tokens, output tokens, total tokens, and
  latency when the SDK exposes them. Do not hard-code a dollar conversion.

## Error and status behavior

Keep machine-readable output on stdout. Errors should not emit secrets, raw
authorization headers, or an uncontrolled SDK traceback.

Recommended statuses:

- `input_error`: existing local validation failure; no API call.
- `configuration_error`: missing or unusable API configuration; no API call.
- `model_error`: timeout, exhausted transient retries, refusal, incomplete
  response, or invalid structured response.
- `tag_retake_required`: tag is unreadable or uncertain.
- `review_required`: model analysis completed but one or more facts are
  unknown, conflicting, invalidly sourced, ambiguous, or unmapped.
- `facts_validated`: all currently enforced facts passed provenance and
  destination validation.
- `review_cancelled`: the user cancelled interactive fact or listing review.
- `listing_approved`: facts and generated listing text passed review and the
  result was approved for local saving.

Do not introduce a universal fact-confidence cutoff without an explicit
documented decision. Preserve fact confidence, and require review based on
unreadability, unknown values, conflicts, invalid provenance, or failed
deterministic mapping. The separate photo-role decision uses the documented 60%
conservative tag-confidence threshold.

## Historical vision-integration chunks

Implementation progress: Chunks 1 through 4 are complete. `openai_vision.py` contains the
exact model configuration, strict schema builder, role-labeled Base64 image
inputs, defensive response parser, and provider error base types. The official
OpenAI Python SDK is pinned at `openai==3.7.0`. `fact_validation.py` applies the
readable-tag gate, converts candidates into the Python contract, enforces
provenance, and maps destination values exactly with Category before Size.
`source_1` and `source_2` are contract fields. `classifier.py` calls the real
hosted API only after local validation and quality checks, retains compatibility
aliases, captures response/model/token/latency metadata, and returns structured
configuration, provider, tag-gate, and review statuses. Transient failures use
at most two retries after the initial request. `tests/test_live_smoke.py` adds
separate readable-tag and unreadable-tag cases that are skipped by default and
require explicit opt-in, credentials, user-supplied photos, and authorization
for two billed requests.

### Chunk 1: API boundary and schema

- Add a focused module for OpenAI request construction, image encoding, schema,
  response parsing, and provider-specific errors.
- Add the OpenAI SDK dependency.
- Do not connect it to the CLI yet.
- Unit-test request construction and parsing with saved response dictionaries or
  mocked SDK objects.
- Update README and AGENTS documentation in the same chunk if actual names,
  dependencies, or configuration differ from this plan.

Verification: existing tests plus new unit tests pass without a network call or
API key.

### Chunk 2: Contract conversion and Depop mapping

- Add `source_1` and `source_2` to `ValidatedClothingFacts`.
- Convert schema-constrained candidate facts into `ClothingFact` and
  `EvidenceClaim` instances.
- Enforce the readable-tag gate before creating validated brand or size.
- Map controlled values using `depop_vocab.py`, resolving Category before Size.
- Preserve raw analysis separately from validated facts.

Verification: fixture tests cover readable, unreadable, uncertain, unknown,
conflicting, invalid-provenance, unmapped, and category-dependent-size cases.

### Chunk 3: CLI integration and operational errors

- Call the real provider after successful local quality checks.
- Preserve existing output sections and compatibility aliases.
- Add structured configuration and API error results with meaningful exit
  codes.
- Capture usage and latency metadata.
- Do not add listing generation.

Verification: all offline tests pass; missing-key and mocked timeout/rate-limit
paths are exercised without network access.

### Chunk 4: Opt-in live smoke test and documentation

- Add an explicitly opt-in live smoke test or documented manual smoke command.
- It must skip by default, require `OPENAI_API_KEY`, use user-supplied test
  photos, and make clear that it incurs API usage.
- Run it only when credentials and suitable photos are available and the user
  has authorized the charge.
- Record observed model ID, schema validity, latency, token usage, and whether
  the tag gate behaved correctly; do not commit photos or secrets.

Verification: run the full offline suite and, when authorized and available,
one live readable-tag case and one unreadable-tag case.

## Required test coverage

- No API call for invalid paths, unsupported files, undecodable files, fewer
  than two item photos, or a missing tag photo.
- Correct MIME and image-role construction for JPEG, PNG, and WebP.
- Strict structured-response parsing and rejection of malformed output.
- Unknown values remain JSON `null` with zero confidence.
- Brand and size cannot acquire item-photo provenance.
- Condition cannot acquire tag-only provenance.
- Conflicts always require review.
- Unreadable and uncertain tags prevent validated facts and listing generation.
- Exact Depop mapping succeeds for supported values and rejects ambiguity.
- Category is resolved before category-dependent Size.
- `source_1` and `source_2` accept only confirmed Source values when present.
- API key and authorization data never appear in stdout, stderr assertions, or
  serialized results.
- Existing image-quality and compatibility behavior remains covered.
- Unordered folders receive exact one-time role coverage, use neutral IDs, and
  follow the 60% automatic-tag threshold.
- Jeans labels preserve waist and inseam; bare numeric waist edits normalize to
  canonical quoted-inch sizes.
- Final fact and listing reviews reject invalid edits and require approval.
- Approved listings save automatically to unique local JSON files without
  overwriting existing files.

## Definition of done

- The ordinary CLI runtime calls real hosted `gpt-5.6-luna` after local input
  validation and image-quality checks.
- Responses use strict JSON Schema rather than asking for informal JSON.
- A missing, unreadable, or uncertain tag cannot produce validated brand, size,
  listing text, export, or publication.
- Raw model analysis and validated facts remain separate in serialized output.
- Controlled listing values are accepted only through deterministic local
  mapping.
- All automated tests pass offline and do not require an API key.
- A live smoke test is opt-in and documented.
- README, AGENTS, FIELD_CONTRACT, dependency instructions, CLI examples, and
  architecture descriptions match the behavior actually implemented.
- No pricing, database, spreadsheet export, frontend, or marketplace automation
  is added.

## Original implementation prompt (historical)

The prompt below is retained as the approved scope record. The work it requests
is complete and should not be rerun as though the integration were absent.

```text
You are working in the local project:
/Users/adrithk/Developer/Resale Automator

Implement the approved hosted GPT-5.6 Luna vision-model milestone described in
MODEL_INTEGRATION_PLAN.md.

Before editing anything:
1. Read AGENTS.md, README.md, FIELD_CONTRACT.md, and
   MODEL_INTEGRATION_PLAN.md in full.
2. Inspect classifier.py, contracts.py, depop_vocab.py, requirements.txt, the
   versioned vocabulary JSON, and all current tests.
3. Run git status and preserve all existing user changes. Do not discard,
   overwrite, or reformat unrelated work.
4. Run the existing test suite to establish a baseline.
5. Check the current official OpenAI documentation for gpt-5.6-luna, the
   Responses API, image inputs, and Structured Outputs before writing the API
   call. Do not substitute a different model or the gpt-5.6 alias.

Implementation constraints:
- Work in the four small chunks specified in MODEL_INTEGRATION_PLAN.md.
- Before each chunk, explain exactly what will change and why. After each
  chunk, explain what changed, how it works, and how it was verified before
  continuing.
- Use Python and the existing CLI architecture. Do not add a website,
  JavaScript stack, database, pricing system, CSV/spreadsheet export, listing
  publishing, or marketplace automation.
- Use the official OpenAI Python SDK and the Responses API.
- Default to model gpt-5.6-luna with low reasoning effort, store=False, image
  inputs, and strict JSON Schema Structured Outputs.
- Runtime must call the real API. Deterministic response fixtures and mocked
  network calls are allowed only in tests; do not build a fake runtime
  provider.
- Read OPENAI_API_KEY only from the environment and never print or serialize
  it.
- Do not call the API when local input validation fails.
- Require at least two item photos and one separately identified tag photo.
- Keep OpenCV quality analysis, raw model analysis, validated facts, Depop
  mapping, and listing generation separate.
- Treat model output as candidate evidence. Enforce provenance and uncertainty
  in Python and perform exact destination matching through depop_vocab.py.
- Never guess tag-derived brand or size. If tag readability is unreadable or
  uncertain, return tag_retake_required with useful retake instructions and
  leave validated_facts and listing_draft null.
- Add source_1 and source_2 to the Python fact contract before validating them.
- Do not introduce a hard confidence threshold without explicit user approval.
- Preserve existing output compatibility keys unless the user separately
  approves their removal.
- Keep README.md, AGENTS.md, FIELD_CONTRACT.md, and
  MODEL_INTEGRATION_PLAN.md synchronized with the behavior implemented in each
  chunk.

Testing requirements:
- All normal automated tests must be deterministic, offline, and free.
- Cover request construction, image roles/MIME types, structured response
  parsing, readable/unreadable/uncertain tags, unknowns, conflicts, provenance,
  Depop mapping, category-before-size, source values, missing API configuration,
  transient API errors, and secret redaction.
- Add an opt-in live smoke test or manual smoke procedure, skipped by default.
  Do not run it or incur API charges unless OPENAI_API_KEY, suitable user-supplied
  photos, and authorization are available.
- Run the complete test suite after every chunk and report the exact command and
  result.

Stop when the definition of done in MODEL_INTEGRATION_PLAN.md is satisfied.
Do not implement later listing-text, pricing, export, or marketplace phases.
```
