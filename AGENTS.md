# AGENTS.md

- This project is in the early Python backend prototype stage; implement new
  features only when the user explicitly authorizes them.
- Read `README.md` before making changes.
- Do not implement features unless the user explicitly asks.
- When the user authorizes coding, implement it in small, reviewable chunks. Before each chunk, explain what will change and why; after each chunk, explain what changed, how it works, and how it was verified before continuing.
- Keep `README.md` and `AGENTS.md` synchronized with implemented behavior. In the same small chunk, document changes to architecture, workflow, scope, dependencies, supported formats, commands, thresholds, or safety boundaries so future agents inherit accurate context.
- Do not silently deviate from the documented direction. When an explicitly authorized implementation changes an earlier decision, record the new decision and its reason in the appropriate project documentation. This documentation permission does not authorize unrequested feature or scope expansion.
- Start with a Python command-line backend prototype; do not introduce a website or JavaScript stack unless the user explicitly asks.
- For the first milestone, accept at least two item photos and one separately identified tag photo.
- Use OpenCV only for measurable image-quality checks such as resolution, blur, lighting, and possible glare. Use a pretrained vision model for garment understanding and tag extraction; do not plan custom model training for the first milestone.
- The selected first vision provider is the hosted OpenAI API using `gpt-5.6-luna`; do not substitute a local model, a different hosted model, or the `gpt-5.6` alias without explicit user approval. Use the Responses API, image inputs, and strict Structured Outputs. The integration is planned but not yet implemented.
- Treat `MODEL_INTEGRATION_PLAN.md` as the implementation handoff for the next milestone. Keep the real API in the runtime path; deterministic saved response fixtures or mocked network calls are permitted only in tests and are not a fake runtime provider.
- Keep image analysis, validated clothing facts, and listing-text generation as separate steps. Generate listing text only from validated facts.
- Treat `FIELD_CONTRACT.md` as the editable source of truth for listing-field priority, provenance, and deferred upload fields. Do not enforce unresolved fields in code until the user confirms their meaning or allowed values.
- Keep Depop destination mapping deterministic and separate from model output. Use the versioned vocabulary data, resolve Category before Size, and require review instead of fuzzy-guessing missing or ambiguous values.
- Use JSON for internal structured results, including warnings, uncertainty, confidence, and provenance. Treat CSV as a later export format for reviewed and approved listings.
- Keep listing generation separate from marketplace browser automation.
- Require a readable tag photo before generating a listing. Never guess tag-derived facts when the tag is missing or unreadable; return useful retake instructions instead.
- Require explicit user approval before exporting or publishing a listing.
- Do not create or modify the external test marketplace.
- Do not add a database, pricing, spreadsheet export, or marketplace automation to the first backend milestone.
- Keep changes small and avoid adding unnecessary files or dependencies.
