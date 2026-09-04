# Development guide

## Architecture

- `web/`: Next.js 16 / React 19 / TypeScript localhost interface, port 3000.
- `api.py`: FastAPI adapter, port 8000; local uploads, analysis/review, approval,
  saving, and CSV download. No marketplace-login or upload routes.
- `pipeline_service.py`: terminal-independent orchestration. No CLI parsing,
  printing, prompting, or process exits.
- `photo_role_detection.py`, `openai_vision.py`: hosted OpenAI boundaries.
- `contracts.py`, `fact_validation.py`, `review_validation.py`, `depop_vocab.py`:
  provenance checks, readable-tag gate, review, and exact destination mapping.
- `listing_generation.py`: deterministic text from approved facts only.
- `listing_pricing.py`: separate model price suggestion, editable before approval.
- `photo_hosting.py`: sanitized Cloudinary JPEG copies and content-based cache.
- `local_persistence.py`: exclusive UUID JSON saves in `approved_listings/`.
- `depop_csv.py`: revalidated version-6 CSV, no provider or marketplace calls.
- `data/`: versioned Depop vocabularies; `tests/fixtures/`: sanitized test inputs
  and the exact CSV template snapshot.

Unordered intake makes two sequential vision calls: photo roles, then garment
analysis. Explicit CLI photo roles use one. Website draft generation adds one
pricing call. CSV download never repeats analysis, pricing, or photo hosting.
The current exact model is `gpt-5.6-luna`, Responses API, strict Structured
Outputs, low reasoning, high image detail, and `store=False`. Do not substitute
models or tune analysis behavior as part of unrelated cleanup.

Provider calls have a 60-second per-attempt timeout and at most two retries for
timeouts, connection failures, rate limits, or 5xx responses. Errors are
secret-safe. Metadata includes model/response IDs, tokens, latency, attempts,
and requested/actual service tiers. `RESALE_OPENAI_SERVICE_TIER` accepts `auto`
(default), `default`, `fast`, or `priority`; availability and pricing depend on
the provider. No automatic tier/model fallback is performed.

## Image and review rules

The browser accepts 3–8 JPEG/PNG/WebP images, each at most 10 MB, stored under
random ignored filenames. OpenCV measures resolution, blur, brightness,
contrast, and possible glare; it does not understand garments. Warnings use a
1,000-pixel minimum edge, blur below 25, brightness below 45 or above 210,
contrast below 20, and glare area at least 5%. These do not replace tag checks.

The picker accepts explicit image extensions as well as MIME types. Uploads
normalize MIME case/parameters and accept image/jpg, image/pjpeg, generic binary,
and missing labels in addition to standard types. Pillow verifies the actual
format matches the extension before saving; OpenCV still checks decodability.
JPEG-family MPO files with .jpg/.jpeg extensions are normalized at intake using
the primary frame only, EXIF orientation, and metadata-free JPEG quality 95.
Hosting also accepts older local MPO uploads. Auxiliary frames are omitted,
not treated as animations; animated PNG/WebP remain rejected by hosting.
The same 40 MP and 10 MB output bounds apply. Source uploads remain capped at
10 MB. Ordinary JPEG/PNG/WebP bytes and users' original files are unchanged.
This does not add HEIC conversion or trust MIME labels as format evidence.

The hosted model must not guess unknown facts. A readable tag is required;
brand and labeled size come from the tag or human corrections. Resolve Category
before Size. Jeans waist/inseam pairs retain the inseam for descriptions. Age
requires evidence, and Style slots are not forced. Final edits are validated
again. See [FIELD_CONTRACT.md](../FIELD_CONTRACT.md) for exact fields.

At approval, all selected photos (including the tag) are hosted in input order.
Pillow applies orientation, removes metadata, converts transparency to white,
and creates JPEGs at quality 95 without resizing (max 40 MP and 10 MB output).
Animated images are rejected. All inputs are checked before networking.
Cloudinary uses signed uploads, a 60-second timeout, content-derived IDs, and
overwrite=False. `local_uploads/hosted/` caches safe URLs; successful uploads are
reused after partial failure. Never delete hosted images before import finishes.

## CLI

The CLI uses `OPENAI_API_KEY` from its shell environment, not automatic .env
loading. Export the key locally without committing it, then run:

```bash
python classifier.py --item path/to/front.jpg --item path/to/back.jpg --tag path/to/tag.jpg --review
# Or an unordered, non-recursive folder:
python classifier.py --photo-folder path/to/clothing-photos --review
```

Interactive review supports keep/edit/clear, validates edits without repeating
vision calls, and requires fact and listing-text approval. Approved CLI JSON is
saved exclusively under a random UUID. The CLI does not price, host photos,
or export CSV; use the website for the complete CSV workflow.

Exit codes: 1 local input, 2 configuration, 3 provider, 4 tag retake, 5 save error.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
cd web
npm run build
```

Normal tests are offline, using injected test doubles only. Preserve the CSV
regression fixture: row 1 version marker, row 2 exact headers, row 3 instructions,
row 4 listing; each row has 26 columns. Quoted, multiline, and Unicode content,
positive price, location, description limits, and 3–8 photo URLs are covered.
Matching this supplied template does not prove current live Depop acceptance.

Live tests are opt-in and require explicit permission:

- `tests/test_live_smoke.py`: `RESALE_RUN_LIVE_SMOKE=1`, `OPENAI_API_KEY`,
  `RESALE_LIVE_ITEM_PHOTOS` (os.pathsep-separated paths),
  `RESALE_LIVE_READABLE_TAG_PHOTO`, and `RESALE_LIVE_UNREADABLE_TAG_PHOTO`.
  Authorizes two billed OpenAI requests.
- `tests/test_cloudinary_smoke.py`: `RESALE_RUN_CLOUDINARY_SMOKE=1` and Cloudinary
  credentials. Uploads three synthetic photos, checks public downloads, and
  deletes only those test assets. Uses certifi with TLS verification enabled.

No tests automatically write to Depop. Never log provider secrets or check
user photos, generated listings, .env, or legacy browser profiles into Git.

## Troubleshooting

- Missing API keys: edit root .env and restart FastAPI. Shell variables override
  .env; the frontend must not receive provider secrets.
- Cloudinary create/upload denied: verify that key's image-create permission
  and the cloud name. Successful authentication alone does not prove upload access.
- Missing photos in old CSVs: download a new CSV from a newly approved listing.
  Old JSON without hosted links cannot produce the current web export.
- Header mismatch: compare with Depop's current template before changing the
  version-6 fixture. Do not remove its first or third rows.
- Mac npm certificate errors: configure the trusted system CA bundle if needed;
  do not disable TLS verification.

The previous browser automation module and dependency were removed. Old
`.depop-browser/` data remains ignored and unused, not silently deleted.
