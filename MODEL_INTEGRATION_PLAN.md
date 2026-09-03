# GPT-5.6 Luna Integration Plan

Status: approved direction, not implemented.

This document is the handoff for the next implementation milestone. It records
the decisions, boundaries, sequence, tests, and completion criteria needed to
connect the existing Python command-line prototype to the real hosted OpenAI
vision API. It does not claim that the integration currently exists.

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

Official references:

- [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Images and vision](https://developers.openai.com/api/docs/guides/images-vision)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

Pricing is deliberately not hard-coded into the application or tests. Provider
pricing can change; record API usage and calculate costs outside the validation
contract when needed.

## Existing implementation to preserve

- `classifier.py` validates at least two item photos plus one separately
  identified tag photo and performs OpenCV quality measurements.
- `contracts.py` separates `image_analysis`, `model_analysis`,
  `validated_facts`, and `listing_draft` in `PipelineResult`.
- `depop_vocab.py` performs deterministic matching against
  `data/depop_template_v6.json` and never fuzzy-guesses missing or ambiguous
  destination values.
- `FIELD_CONTRACT.md` defines field priority and provenance. Brand and size are
  tag-derived; condition requires visible item-photo evidence or explicit user
  input.
- The CLI currently leaves `model_analysis`, `validated_facts`, and
  `listing_draft` as `null`. Existing compatibility keys should remain until a
  separately approved cleanup removes them.

## Intended end-to-end behavior

1. Parse and validate CLI inputs exactly as today.
2. Run the existing OpenCV quality checks and preserve their warnings.
3. If an input is invalid, return the existing structured input error without
   calling the API.
4. Build one multimodal request containing every item photo and the separately
   labeled tag photo. The prompt must give each image an unambiguous role such
   as `item_photo_1`, `item_photo_2`, and `tag_photo`.
5. Ask GPT-5.6 Luna for schema-constrained candidate analysis. The model must
   identify tag readability before proposing tag-derived facts.
6. If the tag is `unreadable` or `uncertain`, stop with a structured
   `tag_retake_required` result. Preserve `image_analysis` and `model_analysis`,
   leave `validated_facts` and `listing_draft` as `null`, and include actionable
   retake instructions. Never guess brand or size.
7. If the tag is readable, convert candidate facts into the existing contract
   types and apply provenance validation.
8. Map destination-controlled values through `depop_vocab.py`. Resolve Category
   before Size. An unknown, ambiguous, invalid, conflicting, or unmapped value
   must require review rather than being coerced.
9. Return structured candidate and validated data. Do not generate description,
   title, price, CSV, spreadsheet rows, or marketplace actions yet.

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
- Describe only visible condition; do not infer hidden defects.
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

Do not introduce a universal confidence cutoff without an explicit documented
decision. Preserve confidence, and require review based on unreadability,
unknown values, conflicts, invalid provenance, or failed deterministic mapping.

## Small implementation chunks

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
- No pricing, database, spreadsheet export, website, listing prose, or
  marketplace automation is added.

## Copy-paste prompt for a new LLM context

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
