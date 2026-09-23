# Phase 6 — Medication plans and dose tracking

## 1. Architecture

Medication plans are profile-scoped factual records. Recurring schedules express intended local wall-clock times, expected occurrences are derived only for requested date ranges, and a `MedicationDoseRecord` is persisted only when a person records an outcome. No background process marks doses missed and no future records are pre-generated.

The structured dose record is authoritative. Each recorded outcome owns one linked, confirmed CareEvent projection so Timeline and older CareEvent-based integrations remain compatible. Direct edits or deletion of that projection return 409; corrections go through the dose API and update both records transactionally.

## 2. Data model

`Medication` belongs to one CareProfile and stores user-entered name, optional strength/form/instructions/notes, `scheduled` or `as_needed`, active state, optional effective dates, creator, and timestamps. Strength and instructions are retained as entered text and receive no clinical interpretation.

`MedicationSchedule` belongs to one Medication and stores a local `TIME`, active state, and optional effective dates. `MedicationScheduleDay` normalizes its weekday set into one constrained row per weekday (`0` Monday through `6` Sunday). A medication may have multiple schedules, including multiple times each day.

`MedicationDoseRecord` stores the medication, optional schedule, UTC occurrence instant, immutable local-date/time/timezone snapshot, explicit `taken`, `missed`, or `skipped` status, actual recorder, recorded timestamp, optional note, and unique CareEvent link. A unique schedule/instant constraint prevents duplicate outcomes for one expected dose.

## 3. Schedule and timezone semantics

CareProfile timezone is authoritative. Schedule times remain local wall-clock values rather than UTC recurrence values. For each requested local date, the service evaluates medication/schedule effective dates and normalized weekdays, then resolves that date/time through `zoneinfo` to UTC.

During a DST fold, the first occurrence is selected deterministically. During a spring-forward gap, the timezone transition determines the effective UTC instant while the response and dose snapshot preserve the originally entered local time. Changing a profile timezone does not rewrite historical dose snapshots.

## 4. Dose status semantics

Only a human-entered outcome creates a dose row:

* `taken` — explicitly recorded as taken
* `missed` — explicitly recorded as missed
* `skipped` — explicitly recorded as skipped
* `not_recorded` — derived response state; never stored as a dose outcome

Elapsed and future expected doses without a record both remain `not_recorded`. The separate `due_state` explains whether that absence is `elapsed` or `upcoming`; the UI renders upcoming absence as **Not due yet**. As-needed medications generate no expected occurrences and only accept an explicitly recorded taken outcome.

The API rejects an attempt to label a future scheduled dose as missed, and the mobile UI does not show outcome controls until that occurrence is due. A future occurrence can therefore never become missed merely because its scheduled time has not arrived.

## 5. Permissions

Every route first applies the existing non-enumerating CareProfile membership dependency. All members, including the profile subject, may view plans and dose history. Admin, family, and carer roles may create, update, and deactivate medication plans and schedules. Those roles may record outcomes on behalf of the subject.

The canonical `CareProfile.subject_user_id` may record their own outcome regardless of membership role. `recorded_by_user_id` always identifies the actual authenticated recorder; CareRelay never attributes a family/carer entry to the subject.

## 6. CareEvent and Timeline relationship

Recording a dose creates one confirmed event:

* taken → `medication_taken`
* missed → `medication_missed`
* skipped → `medication_skipped`

The event records the actual entry time, actual recorder, medication/dose identifiers, and scheduled local date/time. Corrections update the linked event type and factual metadata. Medication plans and expected-but-unrecorded occurrences do not create Timeline events. Unlinked historical medication CareEvents remain valid and are included as legacy evidence by Ask CareRelay.

## 7. Ask CareRelay integration and safety

The controlled medication tool reads authoritative dose rows, derived expected occurrences, and unlinked legacy medication CareEvents. It deterministically returns taken, missed, skipped, and not-recorded counts plus factual per-occurrence status. Recorded doses produce `medication_dose` evidence; an expected occurrence without an outcome produces `medication` plan evidence.

All medication answers use the deterministic response path, preventing a provider from changing a status or collapsing no-record into missed. Questions requesting diagnosis, treatment, dose changes, catch-up/replacement doses, stopping/starting medication, or similar advice bypass the provider and direct the user to a qualified clinician/pharmacist or approved medication instructions.

## 8. Evidence navigation

Evidence types now include `wellbeing_checkin`, `care_event`, `medication`, and `medication_dose`. Medication evidence cards provide **Open exact record**, which routes to the Medications screen and retrieves the authorized medication or dose detail rather than displaying an opaque UUID.

## 9. Audit behavior

Audit actions cover medication create/update/deactivate, schedule create/update/remove, dose record, and dose correction. Payloads contain state needed to explain the change—IDs, active/schedule state, dates, time, status, and linked event—without duplicating instructions, notes, questions, or answers.

## 10. API routes

```text
GET    /api/v1/care-profiles/{id}/medications
POST   /api/v1/care-profiles/{id}/medications
GET    /api/v1/care-profiles/{id}/medications/{medication_id}
PATCH  /api/v1/care-profiles/{id}/medications/{medication_id}
DELETE /api/v1/care-profiles/{id}/medications/{medication_id}       # deactivate

POST   /api/v1/care-profiles/{id}/medications/{medication_id}/schedules
PATCH  /api/v1/care-profiles/{id}/medications/{medication_id}/schedules/{schedule_id}
DELETE /api/v1/care-profiles/{id}/medications/{medication_id}/schedules/{schedule_id}

GET    /api/v1/care-profiles/{id}/medication-doses?start=YYYY-MM-DD&end=YYYY-MM-DD
POST   /api/v1/care-profiles/{id}/medication-doses
GET    /api/v1/care-profiles/{id}/medication-doses/{dose_id}
PATCH  /api/v1/care-profiles/{id}/medication-doses/{dose_id}
```

Schedule removal and medication deletion are soft deactivations so historical dose evidence stays resolvable.

## 11. Mobile UI

Overview links to a dedicated Medications stack screen without adding a sixth tab. The screen shows today's local schedule, future/not-recorded/recorded states, recorder identity and entry time, outcome controls with an optional factual note, active/inactive medication plans, entered instructions, plan editing/deactivation, and schedule add/edit/remove with weekday selection. Timeline continues to distinguish CareEvents and shows medication scheduling/recorder context.

## 12. Validation

* Backend pytest: 74 passed
* Ruff lint and formatting: passed
* SQLite upgrade, schema drift, downgrade, re-upgrade, and second drift check: passed
* Mobile Jest: 21 passed across 10 suites
* TypeScript: passed
* Expo Doctor: 21/21 checks passed
* Expo iOS production export: passed
* `git diff --check`: passed
* Live OpenRouter: not required and not run
* Docker/PostgreSQL 17 checks: not run because Docker is unavailable on this machine
* Live Simulator-to-backend request: not run because of the separately documented M5 networking issue

Coverage includes profile isolation, permissions, subject access, recorder attribution, multi-time and weekday schedules, timezone/DST behavior, expected occurrence generation, future and elapsed no-record semantics, all explicit statuses, duplicate prevention, as-needed behavior, CareEvent consistency, correction/audit behavior, medication Ask metrics/evidence, safety refusal, and the Phase 5 regression suite.

## 13. Limitations and Phase 7 considerations

Phase 6 intentionally has no reminders, notifications, escalation, prescribing, dose calculation, interaction checking, pharmacy integration, barcode/OCR/voice input, or external health integration. Expected occurrences are computed on request and the current UI covers one selected profile and today's actions.

A later phase may add reminder delivery, shared realtime medication refresh, richer historical calendar views, or deep links for existing wellbeing/CareEvent evidence. Those changes must preserve explicit human outcomes, subject attribution, deterministic local-time semantics, and the authoritative dose-to-CareEvent relationship.
