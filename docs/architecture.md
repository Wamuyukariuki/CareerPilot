# Architecture and phased delivery

## Phase 1 and Phase 2 implementation

The platform foundation includes a FastAPI API, PostgreSQL persistence, Alembic migrations, Redis-backed rate limiting, email/password authentication, a React/TypeScript workspace, and per-user career preferences for three separate tracks. Phase 2 adds private PDF/DOCX uploads to two versioned source slots, text/section extraction, and a source-linked profile whose extracted entries are explicitly unverified. The dashboard identifies later phases as planned; it does not display fabricated jobs, applications, or integrations.

## System architecture

```mermaid
flowchart LR
    User[User] --> Web[React + TypeScript dashboard]
    Web -->|JWT bearer API| API[FastAPI application]
    API --> Auth[Authentication and authorization]
    API --> Domain[Application services]
    Auth --> DB[(PostgreSQL)]
    Domain --> DB
    API --> Redis[(Redis rate limits and task coordination)]
    Domain --> CV[CV parsing and unverified profile]
    CV --> Storage[(Private source-file volume)]
    Domain -. Phase 3 .-> Discovery[Compliant job source connectors]
    Domain -. Phase 4 .-> Prep[Application preparation and approvals]
    Prep -. Phase 5 .-> Browser[User-assisted Playwright workflows]
    Domain -. Phase 6 .-> Google[Gmail / Drive OAuth integrations]
    Domain -. Phase 7 .-> Analytics[Tracking and reporting]
```

### Key decisions and boundaries

- **Persistence:** SQLAlchemy 2 models use UUID primary keys and Alembic migrations. SQLite is the local Python default for lightweight tests; Docker Compose uses PostgreSQL. Production configuration rejects SQLite, in-memory rate-limit storage, and the built-in development key.
- **Authentication:** Accounts use Argon2 password hashes and short-lived HS256 bearer tokens. Tokens are held in frontend memory, not local storage. API access is protected by user identity; registration is rate limited. Shared Redis is used by Compose for rate-limit state.
- **Career tracks:** Software engineering, cybersecurity, and electrical engineering preferences are separate rows with independent target titles and search settings.
- **Trust boundary:** External job text, documents, and email will be treated as untrusted data. Later agent workflows must keep system policy separate from retrieved content and gate consequential actions in server-side approval records.
- **Application submissions:** No job-board connectors, document processing, email sending, or application submission are implemented in Phase 1. Later submission must bind approval to an immutable application version and require fresh approval after material edits.
- **Integrations:** Job-board support depends on official APIs, permitted feeds, or user-assisted/manual imports. OAuth client credentials and Google API scopes are deployment-specific and are not claimed as connected.
- **Frontend:** The React dashboard is a functional registration/sign-in shell that reads the authenticated account and its saved career preferences. Additional navigation is visibly marked as planned rather than represented as working features.
- **CV evidence:** Two per-user slots retain immutable source versions and SHA-256 hashes. PDF/DOCX MIME claims are not trusted; signatures/archive structure and upload size are checked. The parser extracts selectable text and recognized section headings without synthesizing facts. Candidate profile entries carry source version IDs and remain unverified. Duplicate lines are grouped only on normalized exact text; discrepancies are not silently resolved.
- **CV data retention:** Files live under a generated storage key outside the web root, backed by a Docker named volume. Deleting a CV slot removes its version records, stored source files, and derived candidate profile evidence. Backups and deployment-level storage encryption remain operator responsibilities.

## Database ER diagram (implemented scope)

```mermaid
erDiagram
    USERS ||--o{ CAREER_PREFERENCES : configures
    USERS ||--o{ MASTER_CVS : owns
    USERS ||--o| PROFESSIONAL_PROFILES : has
    MASTER_CVS ||--|{ CV_VERSIONS : retains
    USERS {
        uuid id PK
        string email UK
        string full_name
        string hashed_password
        string role
        datetime created_at
        datetime updated_at
    }
    CAREER_PREFERENCES {
        uuid id PK
        uuid user_id FK
        string track
        json target_titles
        boolean enabled
        json locations
        boolean remote_preferred
        datetime created_at
        datetime updated_at
    }
    MASTER_CVS {
        uuid id PK
        uuid user_id FK
        int slot
        datetime created_at
        datetime updated_at
    }
    CV_VERSIONS {
        uuid id PK
        uuid master_cv_id FK
        int version
        string original_filename
        string sha256
        string storage_key UK
        text extracted_text
        json extracted_sections
        json review_flags
        datetime uploaded_at
    }
    PROFESSIONAL_PROFILES {
        uuid user_id PK, FK
        json candidate_data
        json review_flags
        datetime updated_at
    }
```

Each candidate profile evidence entry contains its original text, source version ID(s), source CV slot(s), and `verified: false`. The profile does not currently normalize employment, education, skills, certifications, and projects into individual editable entities; that requires a reviewed extraction/verification workflow. Vacancy records and matches are introduced in Phase 3, with application/approval and communication history in subsequent phases.

## Multi-agent workflow (target design)

```mermaid
flowchart TD
    Sources[Permitted sources or manual links] --> Discovery[Discovery agent]
    Discovery --> Dedupe[Normalize, expire and deduplicate]
    Dedupe --> Match[Profile matching agent]
    CVs[Source-linked master CV profile] --> Match
    Match --> Select[CV selection and tailoring]
    Select --> Materials[Cover letter and response drafting]
    Materials --> Prepare[User-assisted application preparation]
    Prepare --> Review{Explicit approval for this exact version?}
    Review -->|Edit or reject| Prepare
    Review -->|Approve| Submit[Submit through supported portal]
    Submit -->|Portal confirms| Track[Application tracking]
    Submit -->|Blocked or uncertain| Intervention[Pause for user intervention]
    Gmail[Read-only Gmail integration] --> Track
    Track --> Analytics[Reporting and reminders]
```

Automated discovery, analysis, document preparation, and email classification are non-committing actions. Submitting, sending email, making declarations, accepting offers, or sharing sensitive documents require explicit user approval.

## Planned implementation phases

| Phase | Scope |
|---|---|
| 1 — Foundation | Project architecture, API, database/migrations, authentication, dashboard shell, environment and Docker. Implemented. |
| 2 — Profile and CV intelligence | Secure source uploads, PDF/DOCX text/section extraction, unverified source-linked profile, version history, and deletion. Implemented incrementally; human verification and tailored document generation remain future work. |
| 3 — Discovery and matching | Permitted connectors/manual import, normalization, deduplication, suitability evaluation and ranked dashboard. |
| 4 — Application preparation | Grounded letters and answers, unresolved declaration prompts, edit/preview and immutable approval records. |
| 5 — Browser automation | Supported Playwright workflows, form completion, user intervention and verified submission outcomes. |
| 6 — Google integration | Least-privilege OAuth, Gmail classification, approved replies, Drive organization; calendar optional. |
| 7 — Tracking and analytics | Application lifecycle, interviews, metrics, notifications and reports. |
| 8 — Deployment hardening | Full test coverage, security review, production deployment and operational runbooks. |

## Integration and operational limitations

- LinkedIn, Indeed, and other job services may restrict automated access. Only supported APIs, feeds, or user-assisted workflows will be used; CAPTCHA, MFA, rate limits, and access controls will not be bypassed.
- Gmail/Drive require OAuth consent configuration, redirect URLs, and Google Cloud credentials. Tokens must be encrypted at rest before persistent integration is enabled.
- Portal forms vary; automation must stop when a portal blocks it, requests unsupported verification, or presents a sensitive declaration.
- The Compose setup is for local development. Production requires managed secrets, TLS, backups, controlled origins, a durable Redis service, and an operational deployment target.
