# Phase 5 — Ask CareRelay

## 1. AI architecture

Ask CareRelay is a profile-scoped evidence summarizer, not a general chatbot. `POST /api/v1/care-profiles/{id}/ask` first applies normal membership authorization, interprets the requested local-date period using the persisted CareProfile timezone, and invokes a bounded set of deterministic care-data tools. Python and SQLAlchemy calculate all counts, averages, comparisons, and frequencies.

Only after the factual payload exists is it passed to the configured AI provider with a deterministic draft and safety instruction. Provider text is schema-validated, and any number absent from the verified facts/period is rejected. The response exposes the answer, backend metrics, record-level evidence, interpreted period, optional visualization, and non-secret provider/model diagnostics. It never exposes prompts, credentials, or chain-of-thought.

## 2. Provider abstraction

`AIProvider` defines the asynchronous generation boundary. `MockAIProvider` returns the deterministic answer and is used for tests and local development. `OpenRouterAIProvider` calls OpenRouter's chat-completions API with an explicit configured model and JSON response schema.

OpenRouter errors, malformed output, or invented numeric values produce a controlled 502 response. There is no automatic/random model routing and automated acceptance does not require network access.

## 3. Controlled tools

The LLM receives no database handle, SQL, or unrestricted query interface. `CareDataTools` provides:

* `get_wellbeing_summary`
* `compare_wellbeing_periods`
* `get_symptom_frequency`
* `get_care_events`
* `get_event_frequency`
* `get_activity_summary`
* `get_medication_event_summary`
* `get_recent_changes`

Every tool is constructed with one authorized CareProfile ID and timezone. Queries repeat that profile constraint and include confirmed CareEvents only. The default maximum is four calls per question and configuration is bounded to 1–10.

## 4. Evidence model

Evidence references contain only a record type, record UUID, occurrence timestamp, and concise label. Self-report conclusions link to `WellbeingCheckin` rows; observation conclusions link to confirmed `CareEvent` rows. Mobile's **Show evidence** sheet visually distinguishes both kinds and opens the supporting-record list.

Ordinary ChatMessages are never queried by AI. A chat-derived observation becomes eligible only after explicit user confirmation creates a CareEvent. Draft CareEvents remain excluded.

## 5. Visualization payload

Wellbeing-summary responses may include:

```json
{
  "type": "wellbeing_summary",
  "average": 66.0,
  "checkin_count": 2,
  "daily_averages": [
    {"date": "2026-09-17", "checkin_count": 1, "average_score": 60.0},
    {"date": "2026-09-18", "checkin_count": 1, "average_score": 72.0}
  ]
}
```

These values are copied from deterministic backend calculations. Mobile renders a large donut, `66 / 100`, the label **Average self-reported wellbeing**, a small daily trend, and the explicit statement that this is subjective and not a clinical health score.

## 6. Safety and data boundaries

Ask CareRelay may summarize recorded information, compare periods, identify recorded changes, and suggest sharing facts with a clinician. It does not diagnose, prescribe, recommend medication changes, claim clinical significance, invent missing facts, or create CareEvents. Insufficient data produces an explicit insufficiency response without calling the provider.

Minimal `ask_audits` rows store actor/profile IDs, a SHA-256 question hash, provider/model, tool names, evidence count, status, error code, and timestamp. Raw questions, answers, prompts, provider credentials, and chain-of-thought are not persisted.

## 7. WebSocket authentication change

Long-lived JWT query parameters were removed. An authenticated member now calls `POST /api/v1/care-profiles/{id}/chat/ws-ticket`. The server creates a cryptographically random in-memory ticket scoped to that user/profile, expiring after 45 seconds. The WebSocket connects with `?ticket=…`; the ticket is atomically consumed once before membership is checked again.

Invalid, expired, reused, or wrong-profile tickets close with 4401. Non-members cannot issue tickets and continue receiving 404. Ticket storage intentionally remains in-process with the existing single-instance realtime design.

## 8. Configuration

```text
AI_PROVIDER=mock|openrouter
AI_MODEL=explicit-provider-model-id
OPENROUTER_API_KEY=
AI_MAX_TOOL_CALLS=4
```

Local/default configuration uses `mock` and `mock-care-relay-v1`. OpenRouter configuration requires both an API key and explicit model ID at startup. Provider secrets exist only in the API environment.

## 9. Test results

* Backend pytest: 55 passed
* Containerized backend pytest: 55 passed
* Ruff: passed for app, tests, and migrations
* SQLite Phase 4 → Phase 5 upgrade, drift check, downgrade, and re-upgrade: passed
* PostgreSQL 17 Phase 4 → Phase 5 upgrade, drift check, downgrade, and re-upgrade: passed
* Runtime mock-provider Ask request and structured response: passed
* Mobile Jest: 11 passed across 6 suites
* Mobile TypeScript: passed
* Expo dependency validation: passed
* Expo iOS production export: passed
* Live OpenRouter request: not run because no credentials were configured

Coverage includes isolation/non-member behavior, deterministic calculations, timezone-bound periods, comparison, symptoms, confirmed-only evidence, chat exclusion, insufficient data, invented metrics, tool limits, malformed output, provider failure, and WebSocket ticket expiry/reuse/profile scope.

## 10. Limitations before Phase 6

* Supported question routing is deliberately narrow and optimized for the documented core questions.
* Evidence drill-down opens an in-app supporting-record sheet; dedicated deep-linked record detail routes can be added later.
* AI does not analyze raw chat, attachments, voice, documents, or images.
* In-memory WebSocket tickets and fan-out require shared infrastructure before multi-instance deployment.
* There is no streaming answer UI, semantic retrieval, long-term AI conversation history, or storage of raw AI conversations.
* Any future AI-generated care-record draft must preserve explicit human review and confirmation.
