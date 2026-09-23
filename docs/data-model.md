# CareRelay data model

```text
User 1 ---- * CareMembership * ---- 1 CareProfile
  |                                      |
  +-- * UserIdentity                    +-- * CareInvitation
  +-- created profiles ------------------+
```

## User

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `email` | varchar(320), nullable | Initial/contact email when available; unique but not an identity key |
| `display_name` | varchar(120) | User-facing name |
| `apple_subject` | varchar(255), nullable | Stable Apple identity subject, unique |
| `deletion_requested_at` | timestamptz, nullable | Account access disabled; shared history retained |
| `created_at` | timestamptz | Server generated |

## CareProfile

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key and future tenancy key |
| `name` | varchar(120) | Human-friendly cared-person/profile name |
| `subject_user_id` | UUID, nullable | Canonical cared-for person; must be a member |
| `timezone` | varchar(100) | Valid persisted IANA timezone |
| `created_by_id` | UUID | Required reference to `User` |
| `created_at` | timestamptz | Server generated |

Creating a profile atomically creates an administrator membership for its creator.

## UserIdentity

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `user_id` | UUID | Cascading reference to `User` |
| `provider` | varchar(30) | Currently `apple` |
| `provider_subject` | varchar(255) | Stable provider key; unique with provider |
| `email_at_signup` | varchar(320), nullable | Initial provider email, including Apple relay addresses |
| `revoked_at` | timestamptz, nullable | Revoked identities cannot authenticate |
| `created_at` | timestamptz | Server generated |

`User.apple_subject` remains as a legacy compatibility/backfill source. New account resolution uses
`UserIdentity(provider, provider_subject)` and never email.

## CareMembership

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `care_profile_id` | UUID | Cascading reference to `CareProfile` |
| `user_id` | UUID | Cascading reference to `User` |
| `role` | string enum | `admin`, `family`, `carer`, or `cared_person` |
| `created_at` | timestamptz | Server generated |

The pair `(care_profile_id, user_id)` is unique. Both foreign-key directions are indexed for authorization lookups. Role values are constrained in the database as well as in API validation.

## CareInvitation

Care invitations store a delivery email, intended family/carer membership role, explicit subject
intent, creator, expiry/acceptance/revocation timestamps, delivery outcome, and a SHA-256 token
hash. Raw invitation tokens are never persisted. Status is derived as pending, accepted, expired,
or revoked. Acceptance records the authenticated user and conditionally links
`CareProfile.subject_user_id`; invited email is context only and is not an identity key.

## Phase 2: WellbeingCheckin

Each check-in belongs to one care profile and records the authenticated cared person's user ID, a database-constrained 0–100 score, timezone-aware occurrence time, optional note, reserved voice transcript, and creation/update timestamps. Multiple rows can occur on the same day.

## Phase 2: WellbeingSymptom

Symptoms are normalized child rows with a closed enum kind and a unique `(checkin_id, kind)` pair. Deleting a check-in cascades to its symptoms.

## Phase 3: CareEvent

Care Events are family/carer observations stored separately from wellbeing self reports. They include a validated event type, occurrence, authenticated author, server-derived source, factual summary, strict type-specific metadata, confirmation status, and audit timestamps.

Medication event types created before Phase 6 remain valid historical observations. Phase 6
adds a structured medication domain; recorded dose outcomes create linked, confirmed CareEvent
projections so the existing timeline remains compatible.

## Phase 3: AuditLog

Append-only application audit rows capture profile/admin creation, subject/timezone changes,
CareEvent changes, medication/report operations, invitations, membership changes, and account
deletion requests. Audit data has no normal mutation API and excludes credentials and raw tokens.

## Phase 4: ChatRoom and ChatMessage

Every CareProfile has one default ChatRoom. ChatMessage stores the authenticated sender, text, deterministic sent timestamp, and optional edit/delete timestamps. Sender deletion clears text but retains a tombstone. Chat is communication and remains separate from CareEvent and WellbeingCheckin.

## Phase 4: ChatReadState

One row per room/member stores a monotonic last-read message marker. Unread counts include only later, non-deleted messages from other members.

## Phase 4: ChatAttachment

Attachment metadata reserves a private opaque storage key, filename, media type, and byte size. Phase 4 has no attachment API and never exposes the storage key or a filesystem URL.

## Phase 4: chat-sourced CareEvent

`CareEvent.source_chat_message_id` is nullable provenance linking an explicitly confirmed record to its originating message. It does not merge the records. Soft-deleting a message leaves the confirmed CareEvent unchanged.

## Phase 5: AskAudit

Minimal AI audit metadata records the profile, actor, SHA-256 question hash, provider/model, tool names, evidence count, success/failure status, optional error code, and timestamp. Raw questions, model prompts, answers, credentials, and chain-of-thought are deliberately not persisted.

## Phase 6: Medication

Medication plans belong to one CareProfile and store a factual name, optional strength, form,
instructions and notes, scheduled or as-needed classification, active state, optional plan date
bounds, creator, and audit timestamps. Deactivation preserves medication history.

## Phase 6: MedicationSchedule and MedicationScheduleDay

A scheduled medication has one or more local wall-clock schedules. Each schedule stores its local
time, active state, optional date bounds, and a normalized set of weekdays. Expected occurrences
are derived for requested date ranges in the CareProfile's IANA timezone; future rows are not
pre-generated.

## Phase 6: MedicationDoseRecord

A dose record stores an explicit human-entered `taken`, `missed`, or `skipped` outcome. It snapshots
the scheduled UTC instant, local date, local time and timezone, records the actor and entry time,
and links to exactly one confirmed CareEvent projection. The pair `(schedule_id, scheduled_for)` is
unique for scheduled doses. `not_recorded` is a derived API state and is never persisted as an
outcome.

Medication plan, schedule and dose mutations append AuditLog entries. Corrections use the dose API
and update the linked CareEvent transactionally; the generic CareEvent API rejects direct mutation
of medication-managed projections.
