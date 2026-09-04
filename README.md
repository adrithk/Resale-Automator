# Relist — Resale Listing Assistant

Turn clothing photos into an editable, photo-ready Depop CSV.

Relist runs locally with a Next.js/TypeScript frontend and a Python/FastAPI
backend. It analyzes clothing and tag photos, suggests listing facts and a
price, hosts the approved photos on Cloudinary, and exports a CSV for manual
import into Depop. It does **not** log into Depop or publish listings.

## Demo

[Watch or download the demo (MP4, about 1 minute)](https://github.com/adrithk/Resale-Automator/releases/download/demo-2026-09-03/relist-demo.mp4)

Upload clothing photos, review the generated listing and price, then download
the CSV and import it into Depop as a draft with photos. Publishing stays manual.

## What works

- Upload 3–8 JPEG, PNG, or WebP photos: at least two garment views and one readable tag.
- Phone `.jpg`/`.jpeg` files are supported, including uppercase extensions and
  alternate or missing browser MIME labels. Files must be genuine images under
  the 10 MB limit. Phone JPEGs with MPO auxiliary images are automatically
  converted to a standard, correctly oriented JPEG; originals remain untouched.
  Export HEIC as JPEG rather than just renaming it.
- Automatically identify the tag and analyze clothing with OpenAI vision.
- Review and edit validated category, brand, size, condition, colors, and style.
  Exact tag-name aliases include “Levi Strauss & Co.” → “Levi’s”; unknown brands still need review.
- Generate editable listing text and a USD price suggestion.
  Descriptions contain only the generated title and size (including validated
  inseam when available). Condition and style remain separate listing fields.
- Approve the listing, host all photos, and save the result locally.
- Download a Depop template-version-6 CSV with photo URLs.
- Import the CSV in your normal logged-in Depop browser, review drafts, and publish manually.

## Autonomous selling status

**Selling API access: being pursued; integration pending access.**
We are working toward obtaining access to Depop's private Selling API. Access is
not available to this project yet, and no completed application or approval is
claimed here.

Without approved Selling API access, Relist does not support autonomous selling.
The browser-login/upload experiment was removed after login security restrictions;
there is no browser automation or workaround in the supported workflow.
Depop documents its API as private and requiring contact for access:
[official Selling API prerequisites](https://partnerapi.depop.com/api-docs/getting-started/your-first-listing/).

## Quickstart

### 1. Install prerequisites

Use Python 3.12+ and Node.js 20.9+ with npm. The current development environment
uses Python 3.14. You need an OpenAI API account with access to the configured
model and a Cloudinary account with image upload/create permission.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd web
npm ci
cd ..
cp .env.example .env
```

If you already have a populated `.env`, keep it—do not overwrite it.

### 2. Configure credentials

Edit the root `.env` (beside `api.py`, not inside `web/`):

```dotenv
OPENAI_API_KEY=your_openai_api_key
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_cloudinary_api_key
CLOUDINARY_API_SECRET=your_cloudinary_api_secret
DEPOP_SHIPPING_LOCATION=California, United States
```

Use your own exact template location value. This is a state/country setting,
not your street address. Keys stay in the backend and must never be committed.
The API loads `.env` on startup; existing shell variables take precedence.
Restart the backend after changing credentials.

### 3. Run two terminals

Backend, from the repository root:

```bash
source .venv/bin/activate
uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Frontend, in another terminal:

```bash
cd web
npm run dev
```

Open [localhost:3000](http://localhost:3000). Keep both terminals running.
Warp, VS Code's terminal, or your regular terminal all work. No public deployment
is needed. Do not expose this unauthenticated local API to the internet.

## Exporting to Depop

1. Select photos in the desired listing order; the first is the cover.
2. Analyze, review facts, then review listing text and price.
3. Choose **Approve and save locally**. All selected photos—including the tag—are
   hosted automatically; there is no separate photo approval.
4. Choose **Download Depop CSV**.
5. In your normal browser, open Depop's Selling Hub and import the CSV using its
   bulk-listing tool.
6. Check the drafts, pictures, and shipping details before manually publishing.
   Do not upload the same listing again if it is already in drafts.

The exporter matches the supplied
[Depop template](https://docs.google.com/spreadsheets/d/1xgHv0DpXlY1f5qADh-IL0iOHgnoma3T5/edit?gid=1319093190):
version marker on row 1, 26 exact headers on row 2, instructions on row 3,
and one approved listing on row 4. It uses UTF-8, standard CSV escaping, and
CRLF record endings. Price and Location are populated; 3–8 public image URLs
retain your selected order. Unused photo slots, shipping prices, and SKU are blank.

Description length, hashtag count, prices, field vocabularies, and photo URLs
are validated before export. The regression fixture checks exact template rows.
This verifies the supplied version-6 format, not a guarantee against future
Depop template changes or account-specific import requirements.
[Field contract and CSV details](FIELD_CONTRACT.md).

## Privacy and limitations

- The website and backend run locally, but analysis photos go to OpenAI and
  approved listing photos go to Cloudinary. This is not an offline-only app.
- Cloudinary copies have EXIF/GPS metadata removed. Anyone with a photo URL can
  view it; keep hosted images available until Depop has imported them.
- Original photos, generated listings, upload caches, and `.env` are ignored by
  Git. Old browser-session data is also ignored and is not used by the app.
- A readable tag is required. Unknown or conflicting facts need review rather
  than guesses; review model output before selling.
- Prices are model suggestions, not researched Depop averages. The suggested
  resale value is halved for a quick-sale price, usually targeting $10–$15 for
  ordinary items. You can edit the amount before approval.
- API usage and photo hosting may incur charges. There is no database,
  authentication system, public hosting, or automatic marketplace publishing.
- This is an independent project, not affiliated with Depop.

## Development and checks

```bash
.venv/bin/python -m unittest discover -s tests -v
cd web
npm run build
```

Ordinary tests are offline. Three live-provider tests are skipped by default;
they require explicit opt-in and may incur costs. Tests cover the pipeline,
validation, Cloudinary upload/cache behavior, and exact CSV/HTTP output.

- [Development guide](docs/DEVELOPMENT.md): architecture, CLI, configuration, testing.
- [Field contract](FIELD_CONTRACT.md): destination mapping and template rules.
- [Agent instructions](AGENTS.md): implementation boundaries for coding agents.

The frontend uses locally bundled Montserrat under its
[SIL Open Font License](web/app/fonts/OFL.txt).
