# Relist — Resale Listing Assistant

**Turn clothing photos into a reviewed, photo-ready Depop listing CSV.**

Relist helps secondhand sellers turn a batch of garment and tag photos into
structured listing facts, editable text, and a suggested price. It combines a
Next.js interface with a Python pipeline that validates model output before
anything becomes a listing. After approval, it hosts the photos on Cloudinary
and exports a CSV for manual import into Depop's Selling Hub.

**Stack:** Python · FastAPI · OpenCV · OpenAI Responses API · Next.js · TypeScript · Cloudinary

## What makes it interesting

- **Evidence-aware extraction.** The vision model proposes facts with confidence
  and photo provenance. Python checks that evidence, blocks unreadable tags,
  and preserves unknowns and conflicts for review.
- **Deterministic marketplace mapping.** Category is resolved before size.
  Versioned vocabularies map fields to exact Depop values, including jeans
  waist/inseam parsing and explicit brand aliases.
- **Separate responsibilities.** Image analysis, fact validation, deterministic
  listing text, and model-assisted pricing are distinct steps. Human edits pass
  validation again before approval.
- **Controlled external calls.** Provider requests use strict Structured Outputs,
  bounded retries, and secret-safe errors. Results record token usage, latency,
  model identifiers, and attempt counts.
- **Repeatable export.** Photo hosting uses content-derived IDs and a local cache.
  CSV downloads reuse hosted photos and the approved price, preserving all three
  leading rows of Depop's version-6 template.

## Workflow

1. Select **3–8 JPEG, PNG, or WebP photos**, including at least two garment views
   and one readable tag. Selection order becomes listing order; the first is the cover.
2. Analyze the photos, then review and edit category, brand, size, condition,
   colors, and optional attributes.
3. Review the generated title, description, and editable **Price (USD)**.
4. Choose **Approve and save locally**. All selected photos, including the tag,
   are hosted on Cloudinary and the approved result is saved as local JSON.
5. Choose **Download Depop CSV**, import it in Depop's Selling Hub, and review
   photos and shipping details before publishing manually.

Example generated text for validated Levi's blue jeans with a 32-inch waist
and 34-inch inseam:

```text
Title: Levi's Blue jeans
Description: Levi's Blue jeans. Size: 32" with a 34" inseam.
```

Condition, style, age, and secondary color remain separate fields in the data
and CSV. Both title and description are editable before approval.

## Run locally

### 1. Install dependencies

Use Python 3.12+ and Node.js 20.9+ with npm. Development currently uses Python
3.14. The web workflow requires an OpenAI API account with access to the
configured model and a Cloudinary account with image upload/create permission.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd web
npm ci
cd ..
# Keep an existing .env if you already configured one.
[ -f .env ] || cp .env.example .env
```

### 2. Configure the backend

Edit the root `.env`, beside `api.py`:

```dotenv
OPENAI_API_KEY=your_openai_api_key
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_cloudinary_api_key
CLOUDINARY_API_SECRET=your_cloudinary_api_secret
DEPOP_SHIPPING_LOCATION=California, United States
```

Location must exactly match a template value; use a state/country, never a street
address. Credentials stay in the backend. The API loads `.env` at startup;
existing shell variables take precedence. Restart it after configuration changes.

Optional `RESALE_OPENAI_SERVICE_TIER` defaults to `auto` (provider defaults).
`default` requests standard processing; `fast` or `priority` opts into premium
Priority processing. This changes only the requested service tier, not the model,
images, or validation. No measured speedup is claimed.

### 3. Start the app

Backend, from the repository root:

```bash
source .venv/bin/activate
uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Frontend, in a second terminal:

```bash
cd web
npm run dev
```

Open [localhost:3000](http://localhost:3000). Interactive API documentation is at
[localhost:8000/docs](http://localhost:8000/docs). Keep both terminals running;
this unauthenticated demo is intended for local use only.

## Demo

[**Watch the one-minute demo →**](https://github.com/adrithk/Resale-Automator/releases/download/demo-2026-09-03/relist-demo.mp4)

The demo follows photo intake, review, and CSV export. The app runs on localhost;
Depop import and publishing are manual. No credentials or setup are needed to
watch the recording.

## Verification

The project was checked with automated offline tests covering photo handling,
fact validation, pricing, saving, and CSV export, with simulated provider
responses to check success and failure cases. All 150 offline tests passed,
and the frontend production build completed successfully. Three optional live
provider tests were skipped; these checks do not measure live model accuracy
or speed.

## Scope and tradeoffs

- **Local app, hosted processing.** Analysis photos go to OpenAI; approved listing
  photos go to Cloudinary. Public photo copies have EXIF/GPS metadata removed,
  but anyone with their URLs can view them. Keep them hosted until import completes.
- **Review remains essential.** A readable tag is required. Prices are model
  suggestions, not researched Depop averages: Python halves the estimated resale
  value and rounds half-up to cents, usually targeting $10–$15 for ordinary items
  without a hard clamp.
- **Bounded photo support.** Files are limited to 10 MB each. Genuine phone JPEGs,
  including MPO auxiliary-image variants, are supported. Hosting prepares
  orientation-correct, metadata-free JPEGs without resizing, with a 40 MP limit.
  HEIC is not supported; export it as JPEG instead of renaming it.
- **Deliberately limited infrastructure.** No database, authentication, public
  deployment, or automatic publishing. API usage and hosting may incur charges.
  `.env`, local uploads, caches, and approved listing JSON are ignored by Git.
- **Marketplace integration stops at CSV.** Selling API access is not available
  to this project; autonomous selling remains pending approved access. No
  application or approval is claimed. The earlier browser automation experiment
  was removed; manual import is the supported workflow.

This is an independent project, not affiliated with Depop. The interface uses
locally bundled Montserrat under its [SIL Open Font License](web/app/fonts/OFL.txt).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing API credentials | Edit root `.env` and restart FastAPI. Shell values take precedence; never place secrets in the frontend. |
| Cloudinary denies uploads | Check image-create permission and credentials, then restart the backend. |
| Old saved listing has no photos | Create and approve a new listing; image-less JSON cannot make the current CSV export. |
| Depop reports a template mismatch | Compare its template with the version-6 fixture. Preserve the first three rows. |
| Phone photo is rejected | Export a real JPEG, PNG, or WebP under 10 MB; changing a HEIC filename is insufficient. |
| npm certificate error on macOS | Configure a trusted CA bundle; do not disable TLS verification. |
