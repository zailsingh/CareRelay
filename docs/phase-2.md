# Phase 2 — Self-reported wellbeing

> Historical Phase 2 handoff. Phase 3 supersedes role-only self-report authority with `CareProfile.subject_user_id` and persists the profile timezone.

## 1. Schema changes

Migration `20260917_0002` adds:

* `wellbeing_checkins`: profile, reporter, integer score, occurrence time, optional note, reserved voice transcript, and audit timestamps.
* `wellbeing_symptoms`: one validated symptom kind per check-in, with a uniqueness constraint on `(checkin_id, kind)`.

Scores have an API constraint and a database check constraint requiring `0 <= score <= 100`. Symptoms use the closed set `dizziness`, `fatigue`, `pain`, `weakness`, `nausea`, `breathlessness`, `poor_sleep`, `low_appetite`, `feeling_good`, and `other`. Symptom lists are not JSON.

## 2. APIs

All routes are below `/api/v1/care-profiles/{care_profile_id}`:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/wellbeing-checkins` | Create a self report |
| `GET` | `/wellbeing-checkins` | List newest first; supports `start_at`, `end_at`, `limit`, and `offset` |
| `GET` | `/wellbeing-checkins/{checkin_id}` | Retrieve one check-in |
| `PATCH` | `/wellbeing-checkins/{checkin_id}` | Update the reporter's own check-in |
| `DELETE` | `/wellbeing-checkins/{checkin_id}` | Delete the reporter's own check-in |
| `GET` | `/wellbeing-checkins/summary` | Summarize inclusive local `start_date` and `end_date` |

`occurred_at` and date-time filters must include an offset. Stored occurrence times are normalized to UTC.

## 3. Permission behaviour

Every route first resolves the profile through the Phase 1 membership dependency. A user without membership receives 404, including when the profile exists.

* `cared_person`: view and create self reports; update/delete only records whose reporter is that user.
* `admin`: view only.
* `family`: view only.
* `carer`: view only.

No endpoint accepts a reporter ID from the client. Creation always assigns the authenticated cared person's user ID, so a family member or carer cannot impersonate them. Future observations must remain a separate record type.

## 4. Summary rules

The caller supplies an IANA timezone such as `Australia/Melbourne`. The API constructs local midnight boundaries for the inclusive date range and converts those boundaries to UTC for the database query. Each result is converted back into that timezone before daily grouping. UTC is never assumed to be the cared person's calendar day.

The API calculates, without AI:

* check-in count
* latest score within the selected period
* arithmetic mean rounded to one decimal
* minimum and maximum
* one daily bucket for every requested date, including empty days
* frequency of every supported symptom, including zero counts

Ranges are limited to 367 inclusive days. Empty periods return null score statistics, zero counts, and daily buckets with null averages.

## 5. Mobile UX

Overview now includes a profile selector, current `How I feel` score, a large 0–100 input, symptom toggles, optional note, save feedback, seven-day statistics, and a lightweight SVG line chart. The chart is a direct rendering of backend-calculated daily averages.

Only a `cared_person` sees the entry form. Other roles see a view-only explanation. Saving increments a shared wellbeing revision so Overview and Timeline refresh immediately. Timeline cards are labelled `Self Report` and show score, occurrence time, symptoms, note, and reporter.

Screen descriptions:

1. **Overview, viewer:** profile switcher, current score card, view-only permission notice, then seven-day average/count and chart.
2. **Overview, cared person:** the same summary plus a check-in card with 56-point step buttons, numeric input, five score presets, symptom chips, note, and save button.
3. **Timeline:** newest-first cards with a green `Self Report` badge and clear reporter attribution.

## 6. Verification

* Backend pytest: 26 passed
* Backend Ruff lint: passed
* Alembic upgrade/downgrade and model-drift validation: passed on SQLite
* Phase 1 → Phase 2 migration on PostgreSQL 17: passed
* PostgreSQL model/schema drift check: passed, no new operations detected
* Mobile Jest: 4 passed across 3 suites
* Mobile TypeScript: passed
* Expo SDK dependency compatibility check: passed
* Expo iOS production bundle export: passed

## 7. Deliberately deferred

* No clinical interpretation or score inference
* No family/carer observations or generic care events
* No medications, chat, AI, or voice transcription
* `voice_transcript` is reserved storage only; there is no recording or transcription flow
* Mobile editing/deletion is deferred; the authorized API operations are available
* Superseded in Phase 3: CareProfile now persists timezone and summaries use it automatically
* Timeline UI currently requests the newest 200 records; API pagination is available for a future infinite list
