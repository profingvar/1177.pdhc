# 1177.pdhc — User manual

1177.pdhc is the platform's **patient-facing form host** — the place where
clinical questionnaires are rendered in a **1177 Vårdguiden style**, filled in
by (or on behalf of) a patient, and turned into structured answers that flow
back into the platform.

It is not a static form library: it receives a specific questionnaire for a
specific patient, presents it, collects the answers, and returns them as
structured FHIR data. Live at **https://1177.pdhc.se** (internal branding:
"1177 Forms").

---

## 1. Where it sits in the platform

Four services cooperate to turn a clinical idea into collected patient data:

```
plan.pdhc      designs the form (concepts → FHIR Questionnaire)
   │
request.pdhc   packages + delivers it to the provider
   │  (push)
1177.pdhc      hosts, renders, collects the answers      ← this service
   │  (dispatch)
gateway.pdhc   receives the completed response for analysis
```

- **In:** `request.pdhc` pushes an order (a FHIR Bundle containing the patient
  and one or more questionnaires).
- **The work:** 1177 creates one **assignment** per questionnaire, renders it,
  and collects answers.
- **Out:** on submit, it produces a FHIR **QuestionnaireResponse**, keeps a
  local copy, and dispatches it to `gateway.pdhc`.

---

## 2. What an operator does

Log in at `https://1177.pdhc.se/login` (username + access key). The portal:

- **Dashboard** — counts of assignments by state (pending / opened /
  completed) and total responses collected.
- **Assignments** — the list of forms waiting to be filled. Open one to see
  the rendered questionnaire. First open moves it `pending → opened`.
- **Fill & submit** — the form renders type-aware widgets automatically:
  radio buttons and checkboxes for choices, Ja/Nej for yes/no, text areas,
  **sliders** with anchor labels and a live value, number fields with the
  unit and allowed range, and native date/time pickers. Required fields are
  marked; the form won't submit until they're answered.
- **After submit** — the assignment becomes `completed`, the answers are sent
  to the gateway, and the form re-renders read-only (with a collapsible view
  of the raw FHIR if you need it).
- **Archive** — tidy the list by archiving old assignments (hidden by
  default; toggle "show all" to see them).
- **Settings** — manage API keys; **Cleanup** — bulk-delete assignments or
  responses (guarded — you must type `DELETE` to confirm).

**Assignment lifecycle:** `pending → opened → completed`
(or `expired` / `cancelled`).

---

## 3. Using the API (integrators)

Service and integration calls use the `X-API-Key` header. The essentials
(base paths `/api/assignments`, `/api/webhook`):

| Do this | Call |
|---|---|
| Check health (no auth) | `GET /api/health` → `{status, database}` |
| List a patient's assignments | `GET /api/assignments?patient_guid=<guid>` |
| Read one assignment | `GET /api/assignments/<assignment_guid>` |
| **Submit answers** | `POST /api/assignments/<assignment_guid>/submit` |
| Cancel an assignment | `POST /api/assignments/<assignment_guid>/cancel` |

Submitting answers produces the same FHIR QuestionnaireResponse and triggers
the same gateway dispatch as the web UI — the two paths are interchangeable.
`request.pdhc` delivers new forms by pushing a FHIR Bundle to
`POST /api/webhook/inbound` (also `X-API-Key`).

---

## 4. Access

- **People** log into the portal with a **username + access key** (the shared
  key-based login; the first admin is bootstrapped at deploy). Roles, per-user
  keys, and a patient-data access log are built in.
- **Services / integrators** authenticate with an **`X-API-Key`** (create and
  revoke keys under *Settings → API keys*).

*(Note: this service uses key/password login, not the platform SSO — every
access to patient data is written to the keyauth access log.)*

---

## 5. Good to know

- **One questionnaire = one assignment.** A single order carrying three
  questionnaires becomes three assignments for the patient.
- The form the patient sees is exactly the Questionnaire that `plan.pdhc`
  authored — `request.pdhc` must resolve and include it before delivering, so
  1177 always renders a complete, self-contained form.
- **Dispatch is fire-and-forget:** if the gateway is briefly unreachable, the
  completed response is still saved locally — it is never lost.
- Answers are typed correctly in FHIR automatically (choice → coding,
  number → integer/decimal, yes/no → boolean, dates → date/dateTime); empty
  optional questions are simply omitted.
- For the endpoints, the FHIR shapes, the data model, and deployment, see the
  **technical manual** (link at the top of this page — with a **Download
  (Markdown)** button).
