# Phase 7 — Care Reports / Prepare for Appointment

## 1. Architecture

`app.services.reports.build_care_report` is the single authoritative report builder. Both preview
and PDF endpoints call it, so calculation rules cannot diverge. It resolves the requested date
range in the CareProfile's persisted IANA timezone and queries only that profile.

The Phase 7 stash was inspected without being popped. Its `ReportRequest`/`CareReport` schema was
reused after compatibility review, along with `report_preview_generated` and
`report_pdf_generated` audit actions. No stale file overwrote Phase 5 or Phase 6 code.

## 2. Periods and deterministic metrics

Reports support the last 7, 30, or 90 local calendar days and custom inclusive ranges up to 367
days. Responses always expose start date, end date, timezone, and a human description.

Backend calculations include:

* wellbeing count, average, minimum, maximum, daily averages, and first-to-latest recorded trend;
* normalized self-reported symptoms plus confirmed symptom-observation CareEvents;
* confirmed falls, activity, sleep, general observations, appointments, and notes;
* authoritative scheduled medication occurrences and explicit taken, missed, skipped, or
  `not_recorded` state.

`not_recorded` is derived from the absence of a human-entered dose result. It is never converted to
missed. Raw ChatMessage rows are never queried. A chat-derived item is included only after explicit
confirmation creates a CareEvent.

## 3. AI narrative boundary

The deterministic service first constructs the complete report and a safe fallback narrative.
`AIProvider` may turn a reduced verified-facts object into concise prose. The response is rejected
if it contains a number absent from the verified facts. Provider transport, schema, or validation
failure leaves the full deterministic report and fallback narrative available.

The provider receives no database connection, raw chat, credential, audit record, or unrestricted
query capability. It cannot change metrics, evidence, periods, or points to discuss.

## 4. Evidence

Wellbeing and symptom claims reference WellbeingCheckin records, confirmed observations reference
CareEvents, recorded dose outcomes reference MedicationDoseRecords, and expected doses without an
outcome reference their Medication plan. Evidence includes a concise label and occurrence time so
the mobile sheet is understandable without displaying bare IDs. Medication evidence can open the
existing exact-record view.

## 5. API and permissions

Profile members use:

* `POST /api/v1/care-profiles/{id}/reports/preview`
* `POST /api/v1/care-profiles/{id}/reports/pdf`

Both routes use the existing membership dependency. Non-members receive the non-enumerating 404
boundary. There are no public report URLs.

Preview and export append minimal AuditLog rows containing actor, profile, action, timestamp, and
period metadata. Complete reports, prompts, provider diagnostics, and PDF content are not audited.

## 6. Mobile flow and visualizations

Overview links to **Prepare for appointment** without adding a bottom tab. The screen retains the
global profile selector, offers standard/custom periods, and renders expandable sections for the
narrative, wellbeing, symptoms, events, medication, appointments, and factual points to discuss.

Visuals use backend values only: an **Average self-reported wellbeing** donut, daily wellbeing line,
symptom-frequency bars, and medication status tiles. Empty sections use explicit sparse-data text
and do not fabricate trends.

## 7. PDF, privacy, and sharing

The API renders a clinician-readable PDF directly in memory from the same `CareReport` model used by
preview. It includes CareRelay branding, subject, period, generation time, narrative, wellbeing,
symptoms, events, medication counts, appointments, factual discussion points, disclaimer, and page
numbers. It excludes database IDs, raw chat, provider diagnostics, prompts, credentials, audit data,
and chain-of-thought. Responses use `Cache-Control: private, no-store`.

Mobile downloads the authenticated PDF into the app cache, opens the native share sheet, and deletes
the file in a `finally` block on success or failure. There is no server-side email or persistent PDF
storage.

## 8. Safety

Reports describe only recorded information. Wording distinguishes “recorded” from occurrence and
never diagnoses, prescribes, recommends medication changes, infers causes, or turns missing dose
records into missed doses. Every report carries the CareRelay non-diagnostic disclaimer.

## 9. Validation

Backend coverage includes standard/custom timezone periods, metrics, symptoms, confirmed events,
falls, appointments, chat exclusion and confirmed conversion, medication status separation,
evidence, sparse/no data, provider fallback, invented-number rejection, membership isolation, PDF
content/privacy, and audit metadata. Mobile coverage includes the Overview entry point, period and
custom-date selection, loading/errors, report sections, visuals, symptoms, medication summary,
evidence, sparse data, sharing, and temporary-file cleanup.

## 10. Known limitations and Phase 8 considerations

PDF charts are represented as concise values and trend text rather than embedded vector charts.
Evidence deep links currently reuse existing medication details; dedicated wellbeing and CareEvent
detail screens remain future work. Reports are generated on demand and are not stored or versioned.

Phase 8 should focus on shared realtime infrastructure and deeper evidence navigation, or on report
accessibility/usability feedback from real appointment workflows. Tasks, reminders, push delivery,
voice, OCR, document ingestion, clinical inference, and external health integrations remain outside
this phase.
