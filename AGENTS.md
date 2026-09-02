# AGENTS.md

- This project is currently in the planning stage.
- Read `README.md` before making changes.
- Do not implement features unless the user explicitly asks.
- When the user authorizes coding, implement it in small, reviewable chunks. Before each chunk, explain what will change and why; after each chunk, explain what changed, how it works, and how it was verified before continuing.
- Start with a Python command-line backend prototype; do not introduce a website or JavaScript stack unless the user explicitly asks.
- For the first milestone, accept at least two item photos and one separately identified tag photo.
- Use OpenCV only for measurable image-quality checks such as resolution, blur, lighting, and possible glare. Use a pretrained vision model for garment understanding and tag extraction; do not plan custom model training for the first milestone.
- Keep image analysis, validated clothing facts, and listing-text generation as separate steps. Generate listing text only from validated facts.
- Use JSON for internal structured results, including warnings, uncertainty, confidence, and provenance. Treat CSV as a later export format for reviewed and approved listings.
- Keep listing generation separate from marketplace browser automation.
- Require a readable tag photo before generating a listing. Never guess tag-derived facts when the tag is missing or unreadable; return useful retake instructions instead.
- Require explicit user approval before exporting or publishing a listing.
- Do not create or modify the external test marketplace.
- Do not add a database, pricing, spreadsheet export, or marketplace automation to the first backend milestone.
- Keep changes small and avoid adding unnecessary files or dependencies.
