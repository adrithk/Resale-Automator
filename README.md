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

The first prototype will not include a website, database, pricing system,
spreadsheet export, or marketplace automation. Pricing is planned as a later,
separate phase that will recommend a selling price from validated facts and
market-comparable data for user review.

The provisional mapping from classifier facts to the supplied listing-template
columns is maintained in [`FIELD_CONTRACT.md`](FIELD_CONTRACT.md). It records
which fields are required, recommended, optional, deferred, excluded, or still
unresolved. Only confirmed universal validation rules are currently enforced in
Python.

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

The CLI does not populate `model_analysis` or `validated_facts` yet. Category,
condition, age, and style vocabularies and field-specific listing-readiness
requirements remain provisional and are not enforced.

## Run the current prototype

Create an isolated Python environment and install the recorded dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the input-validation command with two item photos and one tag photo:

```bash
python classifier.py \
  --item path/to/front.jpg \
  --item path/to/back.jpg \
  --tag path/to/tag.jpg
```

Run the automated tests:

```bash
python -m unittest discover -s tests -v
```

## Current image-quality prototype

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
is pictured. Those decisions will later use a pretrained vision model.

## Keeping project context current

Implementation work should update this README when it changes the architecture,
workflow, scope, dependencies, supported formats, commands, thresholds, or safety
boundaries. If an explicitly approved implementation changes an earlier decision,
the new decision and its reason should be recorded rather than leaving the code and
documentation inconsistent. `AGENTS.md` contains the durable working rules that
future coding agents must follow.
