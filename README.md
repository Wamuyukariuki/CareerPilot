# CareerPilot

A human-approved job-search workspace, built incrementally. Current features include account registration/sign-in, independent career tracks, private PDF/DOCX uploads, source verification, version history, section extraction, a source-linked profile, and vacancy-specific PDF/DOCX exports. Job discovery, LLM agents, Gmail/Drive, browser automation, and application submission are not yet implemented.

See [docs/architecture.md](docs/architecture.md) for the architecture diagrams, decisions, integration limitations, and phased plan.

## Run locally with Docker

1. Copy `.env.example` to `.env`. Set `SECRET_KEY` and `POSTGRES_PASSWORD` to separate random values; run `python -c "import secrets; print(secrets.token_hex(32))"` independently for each. Keep `.env` private. Compose requires both values, keeps PostgreSQL private to its network, and binds the dashboard/API to localhost.
2. Start the services:

   ```sh
   docker compose up --build
   ```

3. Open the dashboard at <http://localhost:5173>. The API and interactive API docs are at <http://localhost:8000> and <http://localhost:8000/docs>.

The API container applies Alembic migrations before serving traffic. PostgreSQL, Redis, and uploaded CV files are stored in named Docker volumes. Compose fails before startup when either required secret is empty.

**Existing installations:** Changing `POSTGRES_PASSWORD` in `.env` does not rotate a password inside an initialized PostgreSQL volume. Rotate the database role password using a secure administrative session, then update `.env` to match and recreate the API. Changing `SECRET_KEY` invalidates existing login tokens. Do not delete database volumes to rotate credentials.

**Sensitive files:** Git and Docker build-context exclusions cover local environment files, common credential/key files, virtual environments, uploads, database dumps and backups. Only the blank `.env.example` template is tracked. These patterns are a safeguard, not a secret detector: never put credentials or CV contents in source code, fixtures or public issue reports. Ignore rules do not untrack existing files or remove Git history. Revoke/rotate any real exposed credential before arranging history cleanup; collaborators must coordinate before rewriting shared history.

## Run the API and tests without Docker

Requires Python 3.12+, PostgreSQL, and Redis. Create and activate a virtual environment, then:

```sh
python -m pip install -r requirements-dev.txt
cp .env.example .env
# Set DATABASE_URL to your local PostgreSQL instance and configure secrets.
alembic upgrade head
uvicorn app.main:app --reload
```

Run backend tests with:

```sh
pytest
```

To run the frontend separately, install Node.js 22+, then run `npm ci && npm run dev` from `frontend/`. Run dashboard interaction tests with `npm test` and the type-checked production build with `npm run build`. The Vite proxy expects the API on `api:8000` as configured for Compose; for a host-based frontend, change the proxy target to `http://localhost:8000`.

## Review and generate CVs

1. Upload one or both master CVs under **My documents**.
2. Download/check the original and expand **Review complete extracted text** and **Edit, exclude and organize source content**. Every entry links to numbered original lines. Exclude template names/contacts, irrelevant examples, duplicate passages and unsupported claims. Correct broken extraction against the original, assign canonical sections, and reorder entries within each section. Keep each employer, role, dates and associated bullets together in a multiline entry, excluding its redundant original continuation lines. Never guess missing information or reconcile conflicting education dates without evidence.
3. Give a reason/evidence note and **Save review and require fresh verification**. Original files/extraction remain unchanged; review revisions retain kept/corrected entries, exclusions and your note. Every source line must be accounted for once. **Confirm source accuracy** explicitly binds verification to the source ID, SHA-256 and exact review revision. Replacements and saved edits revoke verification.
4. Enter a position and job description under **Prepare a CV for a vacancy**. Generation considers only verified current sources, selects by distinct keyword overlap, and ranks entire sections without separating role titles/dates from their bullets. It is not a job suitability assessment.
5. Review the saved comparison, source version/review revision, keywords and wording preview, then download PDF/DOCX. Saved owner corrections/exclusions replace the raw extraction for profile evidence, selection and exports; nonprinting extraction controls removed from output are listed in comparison history. Nothing is sent to an AI service or an application portal.

Quality signals include known sample contact markers, damaged replacement characters, spaced text, duplicate lines/headings, multiple emails, future years and performance percentages. These require explicit source review before initial verification; known sample contact markers and replacement characters must be corrected/excluded even in a saved review. Checks also apply to previously verified sources and legacy downloads. Signals are heuristic, not identity/credential verification: unrecognized template names, conflicting dates and unsupported metrics may remain undetected. The owner must check every retained claim; no content is silently discarded.

Review saves, verification, revocation and generation are recorded in database audit records without document text or credentials. The separate private review history necessarily contains reviewed CV text and evidence notes. Revoking source verification blocks downloads derived from it. Saving a new review permanently makes older-revision snapshots ineligible for download, even after reverification; generate a new snapshot. History remains visible, and already-downloaded files cannot be retracted. Source deletion removes its reviews and generated history too. PDF/DOCX bytes are saved in PostgreSQL to reproduce the same snapshot. The dashboard shows the latest 100 generated snapshots.

**PDF fonts:** Docker installs and embeds DejaVu Sans and monochrome Symbola for Unicode text and contact icons, with bundled Vera as a fallback. The renderer chooses fonts per character without replacing visible source text, including telephone, email and link symbols. For host Python or additional scripts, set `PDF_FONT_PATHS` to a JSON list of absolute TrueType font paths in preference order. Docker defaults are `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` and `/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf`. If none covers a character, the error lists Unicode codes such as `U+E001` so an appropriate font can be installed. Nonprinting C0/C1 controls (except tab/newline/carriage return) are removed only from generated documents and recorded in the comparison. Tabs use spaces for PDF layout but are retained in DOCX. Complex-script shaping and color emoji are not guaranteed. Simple single-column layout is intended for ATS readability, not a guarantee of compatibility with every ATS.

## API

- `POST /api/auth/register` — create an account; seeds the three independent career-track preference records.
- `POST /api/auth/login` — exchange valid credentials for a short-lived bearer token.
- `GET /api/auth/me` — read the authenticated account.
- `GET /api/auth/preferences` — read that account's track preferences.
- `GET /api/profile/cvs` — list the account's CV slots and upload versions.
- `POST /api/profile/cvs/{slot}` — upload/replace slot `1` or `2` with a PDF/DOCX multipart field named `file`.
- `GET /api/profile/cvs/{slot}` — view one CV slot and its history.
- `GET /api/profile/cvs/{slot}/versions/{version}/download` — download an owned original CV version.
- `DELETE /api/profile/cvs/{slot}` — delete the slot, its stored source versions, and profile evidence.
- `GET /api/profile` — view extracted candidate information and verification flags.
- `POST /api/profile/versions/{id}/review` — save a new review (`source_sha256`, `expected_revision`, `entries: [{section, text, source_lines}]`, `excluded_source_lines`, `reason`). Source lines are 1-based original extraction lines; each must occur exactly once across included/excluded references. Sections: `contact`, `summary`, `skills`, `employment_history`, `education`, `certifications`, `projects`, `languages`, `other`. Canonical sections order contact, summary, skills, employment, education, certifications, projects, languages, other before whole-section vacancy ranking; entry order within sections is retained.
- `POST /api/profile/versions/{id}/verify` — confirm the current owned source (`confirmed: true`, `source_sha256`, `review_revision`, default `0` for unedited sources).
- `DELETE /api/profile/versions/{id}/verification` — revoke verification and block derived exports.
- `POST /api/documents/cvs` — generate a saved PDF/DOCX snapshot (`job_title`, `job_description`).
- `GET /api/documents/cvs` — list the latest 100 owned generated snapshots with comparison and preview.
- `GET /api/documents/cvs/{id}/download/{pdf|docx}` — download a generated snapshot.
- `GET /health` — verify API and database connectivity.

New passwords must be at least 12 characters. Registration and login are rate limited. Authentication uses Argon2 password hashing and a 30-minute JWT by default. Change the development secret before deployment; `APP_ENV=production` rejects the built-in development key, SQLite, and in-memory rate-limit storage.

Uploads are limited to 10 MB by default (configurable up to 25 MB), must be actual PDF/DOCX documents, and are stored outside the web root using generated names. PDF documents are limited to 100 pages and password-protected/scanned PDFs are not processed. DOCX archives are checked for entry count and expanded size. Text and clearly labeled sections are extracted without AI rewriting; profile entries keep their source CV slot/version and indicate whether they have a verified source. Exact matching entries across the current CVs are grouped; other differences are not reconciled automatically. Replacements retain previous document versions until the slot is deleted.

## Current limitations

CV parsing is heuristic and can scramble multi-column PDFs. The review editor provides source-linked text correction, exclusion, section assignment and ordering, not normalized employment/education/project entities or automatic layout reconstruction. Verification records owner review, not independent credential verification. Reviewed entries initially use **Additional Information**; assign their actual sections before saving. Keep original heading lines only if intended; canonical headings are added by assigned section. Generation does not use AI to rewrite summaries/skills, invent keywords, infer proficiency, or score eligibility. Scanned-PDF OCR, LLM-assisted rewriting, job discovery, Google integrations, and application submission remain future work. No job listings or application confirmations are seeded. Further boundaries are documented in the architecture guide.
