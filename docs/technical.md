# 1177.pdhc — Technical specification

1177.pdhc is the platform's **patient-facing form host**: it ingests a FHIR
questionnaire targeted at a patient (pushed by `request.pdhc`), renders it in
a 1177-style web UI, collects the answers, produces a FHIR R5
**QuestionnaireResponse**, and dispatches it to `gateway.pdhc`. Internal DB
name `forms_1177`; branding "1177 Forms".

- Stack: Flask 3.1 + Flask-SQLAlchemy + psycopg, PostgreSQL 16, gunicorn
  (2 workers), Flask-CORS. Web UI in Jinja2; shared `pdhc_keyauth` module for
  login.
- Ports: **9036** app (`127.0.0.1`, behind nginx TLS at `1177.pdhc.se`),
  **9037** Postgres (`forms_1177_db`). App runs bare-metal under gunicorn
  (only the DB is containerised).

## 1. Data flow

```
plan.pdhc (Questionnaire) → request.pdhc (ServiceRequest Bundle)
        │  POST /api/webhook/inbound  (X-API-Key)
        ▼
   Assignment (one per Questionnaire, status=pending)
        │  operator/patient fills + submits (UI or API)
        ▼
   QuestionnaireResponse (FHIR R5, stored)  ──►  gateway.pdhc
        POST {GATEWAY_URL}/api/v1/provider/report/<request_guid>
        headers: X-Provider-Token; body {patient_guid, grant_token,
                 status:"completed", report_payload:<QuestionnaireResponse>}
```

## 2. HTTP API

**Health** (`routes/health.py`) — `GET /api/health`, no auth; runs `SELECT 1`,
returns `{status, database}`; CORS `Access-Control-Allow-Origin:
https://www.pdhc.se` (so services.html can read it).

**Webhook** (`routes/webhook.py`, `@require_api_key`) —
`POST /api/webhook/inbound`: parse the FHIR Bundle, read delivery `meta.tag`
(system `https://pdhc.se/delivery`: `grant_token`, `contract_guid`,
`organisation_guid`, `expires_at`), unwrap the `ServiceRequest` + contained
`Patient` + each `Questionnaire`, strip the `questionnaire-` id prefix, and
create **one Assignment per Questionnaire** (`pending`). 201 with the created
assignments; 400 if no Questionnaire is inlined (request.pdhc must resolve it
from plan.pdhc first).

**Assignments REST** (`routes/assignments.py`, `@require_api_key`):

| Method | Path | Notes |
|---|---|---|
| GET | `/api/assignments?patient_guid=&status=&limit=&offset=` | paginated summaries (`patient_guid` required) |
| GET | `/api/assignments/<guid>` | full assignment |
| POST | `/api/assignments/<guid>/submit` | body `{items:[{linkId,text,answer:[…]}]}` → builds QR, dispatches; 409 if already completed/cancelled/expired |
| POST | `/api/assignments/<guid>/cancel` | pending/opened → cancelled |

**Admin web UI** (`routes/admin.py`, `@login_required`): `/dashboard`,
`/assignments` (paginated, archive-aware), `/assignments/<guid>` (renders the
form; auto pending→opened; read-only once terminal), `/assignments/<guid>/submit`,
`/assignments/<guid>/archive`, `/settings`, `/settings/api-keys*`,
`/settings/cleanup*` (bulk delete guarded by `confirm=DELETE`). Login/keys via
`pdhc_keyauth` (`/login`, `/logout`, `/keyauth/*`).

*Not live:* `routes/inbound.py` (`/inbound/push`) exists but its blueprint is
**not registered** — dead code, ignore.

## 3. Data model (`app/models/`)

| Table | Purpose | Key columns |
|---|---|---|
| `assignments` | one questionnaire assigned to a patient | `assignment_guid`, `patient_guid`, `form_guid`, `form_version`, `questionnaire_fhir` (JSON, verbatim), `request_guid`, `grant_token`, `contract_guid`, `organisation_guid`, `grant_expires_at`, `status` (pending\|opened\|completed\|expired\|cancelled), `response_guid`, `archived` |
| `questionnaire_responses` | submitted answers | `response_guid`, `form_guid`, `form_version`, `patient_guid`, `assignment_guid`, `fhir_json` (JSON QR), `submitted_at` |
| `api_keys` | service/webhook keys (sha256, scoped, revocable) | `key_hash`, `name`, `scope`, `is_active`, `expires_at` |

Plus the shared `pdhc_keyauth` tables: `keyauth_users`, `keyauth_keys`,
`keyauth_access_log` (patient-data access audit). Schema via
`app/scripts/init_db.py` (`db.create_all()`); ad-hoc migrations:
`flask migrate-assignments`, `flask migrate-archived`.

## 4. FHIR

- **Consumes** a `Bundle` → `ServiceRequest` with contained `Patient` +
  `Questionnaire` (R5). Item extensions parsed for rendering:
  `questionnaire-unit`, `minValue`/`maxValue`,
  `questionnaire-sliderStepValue`, `questionnaire-itemControl` (slider),
  item `code[]` (LOINC/SNOMED), `repeats`.
- **Produces** a FHIR R5 `QuestionnaireResponse`: `questionnaire=form_guid`,
  `status=completed`, `subject`/`author = Patient/<patient_guid>`, `authored`,
  `item[]`, and `basedOn=[ServiceRequest/<request_guid>]` when present. Answer
  typing: choice→`valueCoding`, string/text→`valueString`,
  integer→`valueInteger`, decimal→`valueDecimal`, boolean→`valueBoolean`,
  date→`valueDate`, dateTime→`valueDateTime`; empty optional items omitted.
- The Questionnaire's FHIR `id` (minus the `questionnaire-` prefix) is the
  Assignment `form_guid`, tracing back to the `plan.pdhc` form.

## 5. Auth

- **Web UI** — key-based login via the shared **`pdhc_keyauth`** module
  (username + access key; roles; per-user keys; access log). **Not** OIDC/SSO.
  First admin bootstrapped from `BOOTSTRAP_ADMIN_USER` /
  `BOOTSTRAP_ADMIN_PASSWORD`.
- **Service-to-service** (webhook + REST) — `X-API-Key`, checked against the
  config `API_KEY` then hashed `api_keys` records (scoped, revocable).
- **Outbound to gateway** — `X-Provider-Token` (PAT) + the carried
  `grant_token`. Org/contract are no longer sent on the report; the gateway
  derives org from the PAT and contract from the grant.
- **Expiry** — `grant_expires_at`; expired grants rejected downstream, status
  can move to `expired`.

## 6. Config & deployment

`.env` (see `.env.example` — but note the app reads **`GATEWAY_URL`**
(default `https://gateway.pdhc.se`) and **`GATEWAY_PROVIDER_TOKEN`**, whereas
the example file still lists stale `GATEKEEPER_*` names):

```
DATABASE_URL=postgresql+psycopg://forms_user:…@localhost:9037/forms_1177
API_KEY=<service webhook key>
SECRET_KEY / ALLOWED_ORIGINS
GATEWAY_URL=https://gateway.pdhc.se   GATEWAY_PROVIDER_TOKEN=<PAT>
BOOTSTRAP_ADMIN_USER / BOOTSTRAP_ADMIN_PASSWORD
```

Deploy: `docker-compose.yml` runs Postgres 16 only (`forms_1177_db`, volume
`forms_1177_data`, `127.0.0.1:9037`). App runs under gunicorn via `start.sh` /
`safe_restart.sh` (bind `127.0.0.1:9036`, 2 workers, timeout 30, daemon, PID
file, `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` for macOS). `safe_restart.sh`
`pg_dumpall`s to `db_backups/` (keeps last 10) before restarting and runs a
5-attempt `/api/health` check. nginx (`server_configs/…_ssl`) terminates TLS
on `1177.pdhc.se` and proxies to `127.0.0.1:9036`.

## 7. Tests

`tests/test_{webhook,routes,models,assignment_form}.py` (~52 passing) —
webhook bundle parsing, REST + admin routes, models, and the type-aware form
rendering/submission.

## Port Allocation

All ports bind to `127.0.0.1` (loopback only); external traffic arrives
via the reverse proxy.

| Port | Service |
|------|---------|
| 9036 | Flask application (Gunicorn) |
| 9037 | PostgreSQL database |
