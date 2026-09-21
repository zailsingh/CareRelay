# Phase 3 — Profile subject, timezone, and structured care events

## 1. CareProfile subject model

`CareProfile.subject_user_id` is the nullable canonical identity of the person the profile is about. It is independent of `CareMembership.role`: a subject may also be the profile administrator, a family member, a carer, or retain the legacy `cared_person` role.

An administrator assigns or clears the subject with `PATCH /api/v1/care-profiles/{care_profile_id}`. Assignment is rejected unless the target user already has a membership for that profile. CareRelay has no membership-removal API yet; a future removal flow must prevent removal of the active subject or clear/reassign the subject atomically.

Self-report creation, update, and deletion now require the authenticated user to equal `subject_user_id`. The legacy role alone grants no self-report authority. No reporter ID is accepted from the client.

The migration safely backfills a subject only when a Phase 2 profile has exactly one `cared_person` member. Zero or multiple candidates are left null rather than guessed. Existing check-ins remain untouched.

## 2. Timezone behaviour

`CareProfile.timezone` is a required IANA timezone name. The API default is `UTC`; mobile profile creation supplies the device's IANA timezone when available. Administrators may update it through the profile patch endpoint.

Wellbeing summaries no longer accept a client-selected timezone. Local date boundaries and daily grouping use the persisted profile timezone, including daylight-saving transitions. The API converts local midnight boundaries to UTC for filtering and converts occurrences back to the profile timezone for grouping.

## 3. CareEvent schema

`care_events` stores:

* profile and event UUIDs
* event type and timezone-aware occurrence timestamp
* authenticated author and server-derived source
* factual text summary
* type-validated metadata
* draft or confirmed status
* creation and update timestamps

Supported types are family observation, symptom observation, medication taken/missed, fall, activity, sleep observation, appointment, and general note.

Metadata uses JSONB on PostgreSQL and JSON during portable tests, but it is not arbitrary JSON. Each event type is validated against a strict schema that rejects unknown keys. Examples include symptom lists and severity, medication name/dose, fall flags, activity duration, sleep duration/quality, and appointment provider/location.

`audit_logs` records subject changes, timezone changes, and event creation/update/deletion with actor, target, timestamp, and bounded before/after snapshots. No normal application endpoint can update or delete audit rows.

## 4. Permissions

All endpoints first apply the existing profile membership query. Non-members receive 404 without learning whether a profile or event exists.

* Admin, family, and carer memberships can create CareEvents.
* The source is derived from the membership role; clients cannot provide or impersonate it.
* Event authors and profile administrators can update or delete events.
* Other profile members can view events.
* The profile subject creates wellbeing self reports through the separate Phase 2 resource.

The single membership role model is otherwise unchanged.

## 5. Timeline and mobile behaviour

Timeline requests wellbeing check-ins and CareEvents separately, merges them by `occurred_at`, and retains a discriminator for rendering. Self reports use green `SELF REPORT` cards with `How I feel`, symptoms, note, and reporter. Care Events use visually distinct purple observation/type cards with author and source.

Quick Add is available to admin, family, and carer roles. It offers Observation, Symptom, Fall, Activity, Sleep, Appointment, Medication taken/missed, and Note. Type-specific optional controls produce only the corresponding validated metadata. The flow explicitly states that observations do not change self-reported wellbeing.

People now lists profile members. Administrators can choose the canonical subject and edit the profile timezone; other members receive a read-only view.

## 6. Migration

`20260917_0003_subject_timezone_care_events.py` upgrades the Phase 2 schema with:

* nullable `care_profiles.subject_user_id`
* required `care_profiles.timezone`
* `care_events` and filter indexes
* immutable-through-API `audit_logs` and audit index
* conservative legacy subject backfill

Automated migration coverage creates Phase 2 users, profile, membership, and wellbeing data; upgrades to Phase 3; verifies preservation/backfill; downgrades to Phase 2; verifies the wellbeing record; then upgrades again.

## 7. Test results

* Backend pytest: 38 passed
* Containerized backend pytest: 38 passed
* Ruff locally and in Docker: passed
* SQLite upgrade, drift, downgrade, and re-upgrade: passed
* Existing PostgreSQL 17 Phase 2 → Phase 3 upgrade: passed
* PostgreSQL downgrade to Phase 2 and re-upgrade: passed
* PostgreSQL model/schema drift check: passed, no new operations detected
* Mobile Jest: 6 passed across 4 suites
* Mobile TypeScript: passed
* Expo SDK dependency compatibility check: passed
* Expo iOS production export: passed

## 8. Decisions affecting Phase 4

* Chat remains outside the formal record. A future “Add to Care Record” action should create a draft CareEvent and require review.
* Audit rows have no normal mutation API. Administrative audit viewing can be added separately if needed.
* CareEvent metadata schemas should be extended deliberately per type; do not relax them into unrestricted JSON.
* Timeline currently merges two paginated feeds client-side and requests up to 200 of each. Phase 4 may need a server-side unified cursor if chat-derived records or data volume make this insufficient.
* CareEvent update/delete UI is deferred; the authorized APIs exist.
* Medication events are factual taken/missed observations only. There is no medication schedule or prescribing model.
* No chat, AI, LLM calls, voice transcription, OCR, or external health integrations are present.
