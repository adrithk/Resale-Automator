# Roadmap

## Complete — local CSV workflow

- [x] Local Python CLI and FastAPI backend.
- [x] Next.js/React/TypeScript photo intake and review UI.
- [x] Automatic photo-role detection and readable-tag checks.
- [x] OpenAI clothing analysis with strict structured output.
- [x] Deterministic Depop vocabulary validation and editable listing text.
- [x] Editable model-suggested USD pricing and configured shipping location.
- [x] Automatic Cloudinary hosting of all approved photos, including the tag.
- [x] Approved JSON persistence and template-version-6 CSV download.
- [x] Offline regression coverage for CSV headers, rows, validation, and photos.

## Next — public demo

- [ ] Record photo intake → analysis → review → CSV download → manual Depop import.
- [ ] Add the recording to the [README demo section](README.md#demo).
- [ ] Verify the imported pictures and remaining shipping fields in Depop.

## In progress — pursuing Selling API access

We are working toward access to Depop's private Selling API. Access has not been
granted; this roadmap does not claim an application has already been submitted.
Supported autonomous selling is blocked until approved API access is available.

- [ ] Contact Depop about access for this project and confirm eligibility.
- [ ] Obtain testing credentials and document permitted integration behavior.
- [ ] Verify draft-versus-published behavior before designing the adapter.
- [ ] Map approved facts, prices, and hosted photos into the official API.
- [ ] Add explicit approval boundaries, duplicate prevention, and error recovery.
- [ ] Test in the approved environment before enabling a live integration.

[Official API access information](https://partnerapi.depop.com/api-docs/getting-started/your-first-listing/).

## Not part of the current release

Browser automation was removed because login security restrictions made that
approach unsuitable. We will not bypass login/CAPTCHA controls or use private
browser endpoints as a substitute for approved API access. The current app
exports CSVs; users import and publish manually in their normal browser.

Public hosting, multi-user accounts, custom model training, live price research,
and a database are outside this localhost demo's scope.
