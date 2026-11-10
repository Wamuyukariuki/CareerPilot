# CareerPilot

A human-approved job-search workspace, built incrementally. Phase 1 foundation and the Phase 2 CV-source/profile workflow are implemented: account registration/sign-in, independent preferences for three career tracks, private PDF/DOCX uploads, version history, deterministic section extraction, and a source-linked unverified profile. Job discovery, AI agents, Gmail/Drive, browser automation, and application submission are not yet implemented.

See [docs/architecture.md](docs/architecture.md) for the architecture diagrams, decisions, integration limitations, and phased plan.

## Run locally with Docker

1. For a quick local start, no setup is required: Compose uses a development-only database password, keeps PostgreSQL private to the Docker network, and binds the dashboard/API to localhost. For a persistent or shared setup, copy `.env.example` to `.env`, set unique `SECRET_KEY` and `POSTGRES_PASSWORD` values, and keep `.env` private. Never use the local defaults in production.
2. Start the services:

   ```sh
   docker compose up --build
   ```

3. Open the dashboard at <http://localhost:5173>. The API and interactive API docs are at <http://localhost:8000> and <http://localhost:8000/docs>.

The API container applies Alembic migrations before serving traffic. PostgreSQL, Redis, and uploaded CV files are stored in named Docker volumes. Compose refuses production startup with the built-in development key or local-only database password.

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

To run the frontend separately, install Node.js 22+, then run `npm install && npm run dev` from `frontend/`. The Vite proxy expects the API on `api:8000` as configured for Compose; for a host-based frontend, change the proxy target to `http://localhost:8000`.

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
- `GET /health` — verify API and database connectivity.

New passwords must be at least 12 characters. Registration and login are rate limited. Authentication uses Argon2 password hashing and a 30-minute JWT by default. Change the development secret before deployment; `APP_ENV=production` rejects the built-in development key, SQLite, and in-memory rate-limit storage.

Uploads are limited to 10 MB by default (configurable up to 25 MB), must be actual PDF/DOCX documents, and are stored outside the web root using generated names. PDF documents are limited to 100 pages and password-protected/scanned PDFs are not processed. DOCX archives are checked for entry count and expanded size. Text and clearly labeled sections are extracted without AI rewriting; each profile entry remains unverified and keeps its source CV slot/version. Exact matching entries across the current CVs are grouped; other differences are surfaced for review, not reconciled automatically. Replacements retain previous document versions until the slot is deleted.

## Current limitations

CV parsing is heuristic and only groups text under recognized section headings; it does not yet identify structured dates, employers, qualifications, or project types with human-level accuracy, and it does not offer a profile-edit/verification workflow. Scanned-PDF OCR, job discovery, AI content, Google integrations, and application submission remain future phases. No job listings or application confirmations are seeded. Further operational and security boundaries are documented in the architecture guide.
